from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_supplier_discovery_pipeline import (
    FakeSupplierSearchService,
    RecordingSupplierQueue,
    configure_dependencies,
    create_approved_catalog,
)

from app.api.dependencies import (
    get_attachment_provider,
    get_email_composer,
    get_rfq_delivery_queue,
)
from app.application.ports.attachment_provider import AttachmentContent
from app.application.ports.email_sender import EmailSender, EmailSendResult
from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.use_cases.rfqs import DeliverRfq
from app.application.use_cases.supplier_discovery import ProcessSupplierDiscoveryRun
from app.config.settings import get_settings
from app.domain.rfqs.entities import EmailMessage
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.rfq import (
    EmailAttachmentModel,
    EmailMessageModel,
    OutboundMessageLogModel,
    RfqRequestModel,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.email.jinja_template_renderer import JinjaTemplateRenderer
from app.infrastructure.email.stored_document_attachment_provider import (
    StoredDocumentAttachmentProvider,
)
from app.infrastructure.email.template_email_composer import TemplateEmailComposer
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


class RecordingRfqQueue(RfqDeliveryQueue):
    def __init__(self) -> None:
        self.rfq_ids: list[UUID] = []

    def enqueue(self, rfq_id: UUID) -> None:
        self.rfq_ids.append(rfq_id)


class RecordingEmailSender(EmailSender):
    provider_name = "test-smtp"
    sender_address = "compras@example.mx"

    def __init__(self) -> None:
        self.calls: list[tuple[EmailMessage, tuple[AttachmentContent, ...]]] = []

    def send(
        self,
        message: EmailMessage,
        attachments: tuple[AttachmentContent, ...],
    ) -> EmailSendResult:
        self.calls.append((message, attachments))
        return EmailSendResult(
            provider_name=self.provider_name,
            external_message_id=f"<test-{message.attempt_number}@example.mx>",
            duration_ms=37,
        )


def approve_suppliers(client: TestClient, tender_id: str) -> tuple[str, str, str]:
    response = client.post(
        f"/api/v1/tenders/{tender_id}/suppliers/discover",
        json={"requested_by_user_id": SYSTEM_USER_ID},
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run"]["id"])
    ProcessSupplierDiscoveryRun(
        SqlAlchemyUnitOfWork,
        FakeSupplierSearchService(),
        SupplierDeduplicationService(),
        SupplierMatchingService(),
    ).execute(run_id)
    suppliers = client.get(f"/api/v1/tenders/{tender_id}/suppliers").json()["suppliers"]
    discovered_ids: list[str] = []
    for supplier in suppliers:
        if supplier["status"] == "approved":
            discovered_ids.append(supplier["id"])
            continue
        if supplier["status"] not in {"candidate", "contacts_found", "pending_review"}:
            continue
        approved = client.post(
            f"/api/v1/suppliers/{supplier['id']}/approve",
            json={"reviewer_user_id": SYSTEM_USER_ID},
        )
        assert approved.status_code == 200, approved.text
        discovered_ids.append(supplier["id"])

    existing_manual = next(
        (
            supplier
            for supplier in suppliers
            if supplier.get("trade_name") == "Proveedor Manual"
            and supplier["status"] == "approved"
        ),
        None,
    )
    if existing_manual is not None:
        manual_id = existing_manual["id"]
    else:
        manual = client.post(
            "/api/v1/suppliers/manual",
            json={
                "tender_id": tender_id,
                "created_by_user_id": SYSTEM_USER_ID,
                "trade_name": "Proveedor Manual",
                "category": "Eléctrico",
                "contacts": [
                    {
                        "contact_type": "email",
                        "value": "manual@example.mx",
                        "confidence": 1.0,
                        "source_url": "manual://captura",
                        "contact_name": "María Compras",
                    }
                ],
                "source_note": "Proveedor agregado para prueba RFQ legacy",
            },
        )
        assert manual.status_code == 201, manual.text
        manual_id = manual.json()["id"]
        approved_manual = client.post(
            f"/api/v1/suppliers/{manual_id}/approve",
            json={"reviewer_user_id": SYSTEM_USER_ID},
        )
        assert approved_manual.status_code == 200, approved_manual.text
    assert len(discovered_ids) >= 2
    return discovered_ids[0], discovered_ids[1], manual_id


def test_complete_rfq_generation_send_and_audit() -> None:
    configure_dependencies(RecordingSupplierQueue(), FakeSupplierSearchService())
    rfq_queue = RecordingRfqQueue()
    settings = get_settings()
    attachment_provider = StoredDocumentAttachmentProvider(
        SqlAlchemyUnitOfWork,
        LocalFileStorage(settings.storage_root),
        settings.max_email_attachment_bytes,
    )
    app.dependency_overrides[get_rfq_delivery_queue] = lambda: rfq_queue
    app.dependency_overrides[get_attachment_provider] = lambda: attachment_provider
    app.dependency_overrides[get_email_composer] = lambda: TemplateEmailComposer(
        JinjaTemplateRenderer()
    )
    client = TestClient(app)
    try:
        tender_id = create_approved_catalog(client)
        approve_suppliers(client, tender_id)
        deadline = datetime.now(UTC) + timedelta(days=10)
        generated = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs/generate",
            json={
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": deadline.isoformat(),
                "observations": "Cotizar entrega en Querétaro",
            },
        )
        assert generated.status_code == 201, generated.text
        payload = generated.json()
        assert len(payload["generated"]) == 3
        assert len(payload["suppliers_without_email"]) == 1
        assert all(item["status"] == "pending_review" for item in payload["generated"])
        assert all(item["attachments"] for item in payload["generated"])

        idempotent = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs/generate",
            json={
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": deadline.isoformat(),
                "observations": "Cotizar entrega en Querétaro",
            },
        )
        assert idempotent.status_code == 201
        assert not idempotent.json()["generated"]
        assert len(idempotent.json()["reused"]) == 3

        with_email = next(
            item
            for item in payload["generated"]
            if item["to_recipients"]
            and item["to_recipients"][0] == "ventas@conductores.example.mx"
        )
        manual = next(
            item
            for item in payload["generated"]
            if item["to_recipients"] == ["manual@example.mx"]
        )
        without_email = next(
            item for item in payload["generated"] if not item["to_recipients"]
        )

        cannot_approve = client.post(
            f"/api/v1/rfqs/{without_email['id']}/approve",
            json={"approved_by_user_id": SYSTEM_USER_ID},
        )
        assert cannot_approve.status_code == 422
        cancelled = client.post(
            f"/api/v1/rfqs/{without_email['id']}/cancel",
            json={
                "cancelled_by_user_id": SYSTEM_USER_ID,
                "reason": "Proveedor sin correo confirmado",
            },
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        for rfq in (with_email, manual):
            approved = client.post(
                f"/api/v1/rfqs/{rfq['id']}/approve",
                json={"approved_by_user_id": SYSTEM_USER_ID},
            )
            assert approved.status_code == 200, approved.text
            queued = client.post(
                f"/api/v1/rfqs/{rfq['id']}/send",
                json={"requested_by_user_id": SYSTEM_USER_ID},
            )
            assert queued.status_code == 202, queued.text
            assert UUID(rfq["id"]) in rfq_queue.rfq_ids
            sender = RecordingEmailSender()
            DeliverRfq(SqlAlchemyUnitOfWork, attachment_provider, sender).execute(
                UUID(rfq["id"])
            )
            assert len(sender.calls) == 1
            assert sender.calls[0][1][0].content.startswith(b"%PDF-")
            assert client.get(f"/api/v1/rfqs/{rfq['id']}").json()["status"] == "sent"

        duplicate_send = client.post(
            f"/api/v1/rfqs/{with_email['id']}/send",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert duplicate_send.status_code == 409

        rfqs = client.get(f"/api/v1/tenders/{tender_id}/rfqs").json()
        assert rfqs["metrics"]["total"] == 3
        assert rfqs["metrics"]["sent"] == 2
        assert rfqs["metrics"]["cancelled"] == 1
        assert rfqs["metrics"]["success_percentage"] == pytest.approx(66.67)

        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(RfqRequestModel)) == 3
            assert session.scalar(select(func.count()).select_from(EmailAttachmentModel)) >= 3
            assert session.scalar(select(func.count()).select_from(EmailMessageModel)) == 2
            assert session.scalar(select(func.count()).select_from(OutboundMessageLogModel)) >= 4
            events = set(session.scalars(select(AuditEventModel.event_type)))
        assert {
            "RfqGenerated",
            "RfqApproved",
            "RfqCancelled",
            "RfqQueued",
            "EmailSendingStarted",
            "EmailSent",
            "AttachmentGenerated",
            "TemplateRendered",
        } <= events
    finally:
        app.dependency_overrides.clear()


def test_rfq_generation_requires_approved_catalog_and_supplier() -> None:
    app.dependency_overrides[get_rfq_delivery_queue] = lambda: RecordingRfqQueue()
    client = TestClient(app)
    try:
        tender = client.post(
            "/api/v1/tenders",
            json={"title": "Sin proveedores", "created_by_user_id": SYSTEM_USER_ID},
        )
        assert tender.status_code == 201
        response = client.post(
            f"/api/v1/tenders/{tender.json()['id']}/rfqs/generate",
            json={
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == "rfq_generation_error"
        missing = client.get(f"/api/v1/rfqs/{UUID(int=0)}")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
