from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_rfq_pipeline import (
    SYSTEM_USER_ID,
    approve_suppliers,
)
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
from app.application.use_cases.rfq_workflow import SendRfq
from app.config.settings import get_settings
from app.domain.rfqs.entities import EmailMessage
from app.domain.rfqs.exceptions import (
    AmbiguousEmailDeliveryError,
    RetryableEmailDeliveryError,
)
from app.infrastructure.db.models.rfq import EmailMessageModel, RfqTaskRecordModel, RfqVersionModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.email.jinja_template_renderer import JinjaTemplateRenderer
from app.infrastructure.email.simulated_email_sender import SimulatedEmailSender
from app.infrastructure.email.stored_document_attachment_provider import (
    StoredDocumentAttachmentProvider,
)
from app.infrastructure.email.template_email_composer import TemplateEmailComposer
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import app


class RecordingRfqQueueV2(RfqDeliveryQueue):
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID | None, str | None]] = []

    def enqueue(
        self,
        rfq_id: UUID,
        *,
        task_record_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.calls.append((rfq_id, task_record_id, correlation_id))


class RetryableSender(EmailSender):
    provider_name = "transient-test"
    sender_address = "compras@example.mx"

    def send(
        self,
        message: EmailMessage,
        attachments: tuple[AttachmentContent, ...],
    ) -> EmailSendResult:
        del message, attachments
        raise RetryableEmailDeliveryError("temporary provider outage")


class AmbiguousSender(EmailSender):
    provider_name = "ambiguous-test"
    sender_address = "compras@example.mx"

    def send(
        self,
        message: EmailMessage,
        attachments: tuple[AttachmentContent, ...],
    ) -> EmailSendResult:
        del message, attachments
        raise AmbiguousEmailDeliveryError("timeout after DATA; acceptance unknown")


def _setup() -> tuple[TestClient, RecordingRfqQueueV2, StoredDocumentAttachmentProvider]:
    configure_dependencies(RecordingSupplierQueue(), FakeSupplierSearchService())
    queue = RecordingRfqQueueV2()
    settings = get_settings()
    attachment_provider = StoredDocumentAttachmentProvider(
        SqlAlchemyUnitOfWork,
        LocalFileStorage(settings.storage_root),
        settings.max_email_attachment_bytes,
    )
    app.dependency_overrides[get_rfq_delivery_queue] = lambda: queue
    app.dependency_overrides[get_attachment_provider] = lambda: attachment_provider
    app.dependency_overrides[get_email_composer] = lambda: TemplateEmailComposer(
        JinjaTemplateRenderer()
    )
    return TestClient(app), queue, attachment_provider


def _selection(client: TestClient, tender_id: str) -> tuple[dict, dict, str, list[str]]:
    approve_suppliers(client, tender_id)
    suppliers = client.get(f"/api/v1/tenders/{tender_id}/suppliers").json()["suppliers"]
    supplier = next(
        item
        for item in suppliers
        if item["status"] == "approved"
        and any(contact["contact_type"] == "email" for contact in item["contacts"])
    )
    contact = next(
        contact for contact in supplier["contacts"] if contact["contact_type"] == "email"
    )
    catalog = client.get(f"/api/v1/tenders/{tender_id}/catalog").json()
    product_ids = [item["id"] for item in catalog["products"] if item["status"] == "approved"]
    document_ids = [
        item["id"]
        for item in client.get(f"/api/v1/tenders/{tender_id}/documents").json()["items"]
    ]
    return supplier, contact, product_ids[0], document_ids


def _generate(
    client: TestClient,
    tender_id: str,
    supplier: dict,
    contact: dict,
    product_id: str,
    document_ids: list[str],
) -> dict:
    response = client.post(
        f"/api/v1/tenders/{tender_id}/rfqs",
        json={
            "supplier_id": supplier["supplier_id"],
            "contact_id": contact["id"],
            "product_ids": [product_id],
            "document_ids": document_ids[:1],
            "generated_by_user_id": SYSTEM_USER_ID,
            "response_deadline": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "requested_currency": "MXN",
            "commercial_terms": "Indicar impuestos y condiciones de pago.",
            "quote_validity": "30 días",
            "response_instructions": "Responder a este correo con la cotización en PDF.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client: TestClient, rfq_id: str) -> None:
    review = client.post(
        f"/api/v1/rfqs/{rfq_id}/submit-review",
        json={"reviewed_by_user_id": SYSTEM_USER_ID},
    )
    assert review.status_code == 200, review.text
    approval = client.post(
        f"/api/v1/rfqs/{rfq_id}/approve",
        json={"approved_by_user_id": SYSTEM_USER_ID},
    )
    assert approval.status_code == 200, approval.text


def test_explicit_rfq_simulation_is_human_gated_versioned_and_idempotent() -> None:
    client, queue, attachment_provider = _setup()
    try:
        tender_id = create_approved_catalog(client)
        supplier, contact, product_id, document_ids = _selection(client, tender_id)
        rfq = _generate(client, tender_id, supplier, contact, product_id, document_ids)
        assert rfq["status"] == "draft"
        assert rfq["contact_id"] == contact["id"]
        assert rfq["to_recipients"] == [contact["value"].lower()]
        assert len(rfq["attachments"]) == 1
        assert "precio unitario" in rfq["body"]

        premature = client.post(
            f"/api/v1/rfqs/{rfq['id']}/send",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert premature.status_code == 409

        review = client.post(
            f"/api/v1/rfqs/{rfq['id']}/submit-review",
            json={"reviewed_by_user_id": SYSTEM_USER_ID},
        )
        assert review.status_code == 200
        edited = client.patch(
            f"/api/v1/rfqs/{rfq['id']}",
            json={
                "changed_by_user_id": SYSTEM_USER_ID,
                "subject": "RFQ v2 — confirmar entrega",
                "change_reason": "Aclarar alcance comercial",
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["version"] == 2
        assert edited.json()["status"] == "draft"
        versions = client.get(f"/api/v1/rfqs/{rfq['id']}/versions")
        assert versions.status_code == 200
        assert [item["version"] for item in versions.json()["versions"]] == [1, 2]
        assert versions.json()["versions"][0]["subject"] != "RFQ v2 — confirmar entrega"

        _approve(client, rfq["id"])
        queued = client.post(
            f"/api/v1/rfqs/{rfq['id']}/send",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert queued.status_code == 202, queued.text
        assert len(queue.calls) == 1
        _, task_id, correlation_id = queue.calls[0]
        assert task_id is not None and correlation_id

        sender = SimulatedEmailSender("compras@example.mx")
        first_message_id = SendRfq(
            SqlAlchemyUnitOfWork,
            attachment_provider,
            sender,
        ).execute(UUID(rfq["id"]), task_id, correlation_id)
        second_message_id = SendRfq(
            SqlAlchemyUnitOfWork,
            attachment_provider,
            sender,
        ).execute(UUID(rfq["id"]), task_id, correlation_id)
        assert first_message_id == second_message_id

        current = client.get(f"/api/v1/rfqs/{rfq['id']}").json()
        assert current["status"] == "sent"
        frozen = client.patch(
            f"/api/v1/rfqs/{rfq['id']}",
            json={"changed_by_user_id": SYSTEM_USER_ID, "subject": "No permitido"},
        )
        assert frozen.status_code == 409
        messages = client.get(f"/api/v1/rfqs/{rfq['id']}/messages").json()["messages"]
        assert len(messages) == 1
        assert messages[0]["provider_name"] == "simulation"
        assert messages[0]["external_message_id"].startswith("<simulated-")

        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(EmailMessageModel)) == 1
            assert session.scalar(select(func.count()).select_from(RfqTaskRecordModel)) == 1
            assert session.scalar(select(func.count()).select_from(RfqVersionModel)) == 2
    finally:
        app.dependency_overrides.clear()


def test_rejected_supplier_missing_contact_and_bad_attachment_are_blocked() -> None:
    client, _, _ = _setup()
    try:
        tender_id = create_approved_catalog(client)
        _, _, product_id, _ = _selection(client, tender_id)
        rejected = client.post(
            "/api/v1/suppliers/manual",
            json={
                "tender_id": tender_id,
                "created_by_user_id": SYSTEM_USER_ID,
                "trade_name": "Proveedor rechazado",
                "contacts": [
                    {
                        "contact_type": "email",
                        "value": "rechazado@example.mx",
                        "confidence": 1,
                        "source_url": "manual://test",
                    }
                ],
            },
        ).json()
        reject = client.post(
            f"/api/v1/suppliers/{rejected['id']}/reject",
            json={"reviewer_user_id": SYSTEM_USER_ID, "reason": "No elegible"},
        )
        assert reject.status_code == 200
        blocked = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs",
            json={
                "supplier_id": rejected["supplier_id"],
                "contact_id": rejected["contacts"][0]["id"],
                "product_ids": [product_id],
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
        )
        assert blocked.status_code == 409

        approved = client.post(
            "/api/v1/suppliers/manual",
            json={
                "tender_id": tender_id,
                "created_by_user_id": SYSTEM_USER_ID,
                "trade_name": "Sin contacto",
                "contacts": [],
            },
        ).json()
        client.post(
            f"/api/v1/suppliers/{approved['id']}/approve",
            json={"reviewer_user_id": SYSTEM_USER_ID},
        )
        missing_contact = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs",
            json={
                "supplier_id": approved["supplier_id"],
                "contact_id": str(uuid4()),
                "product_ids": [product_id],
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
        )
        assert missing_contact.status_code in {409, 422}

        supplier, contact, _, _ = _selection(client, tender_id)
        bad_attachment = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs",
            json={
                "supplier_id": supplier["supplier_id"],
                "contact_id": contact["id"],
                "product_ids": [product_id],
                "document_ids": [str(uuid4())],
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
        )
        assert bad_attachment.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_retryable_and_ambiguous_failures_do_not_create_duplicate_messages() -> None:
    client, queue, attachment_provider = _setup()
    try:
        tender_id = create_approved_catalog(client)
        supplier, contact, product_id, document_ids = _selection(client, tender_id)

        transient = _generate(client, tender_id, supplier, contact, product_id, document_ids)
        _approve(client, transient["id"])
        client.post(
            f"/api/v1/rfqs/{transient['id']}/send",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        task_id = queue.calls[-1][1]
        with pytest.raises(RetryableEmailDeliveryError):
            SendRfq(
                SqlAlchemyUnitOfWork,
                attachment_provider,
                RetryableSender(),
            ).execute(UUID(transient["id"]), task_id, queue.calls[-1][2])
        assert client.get(f"/api/v1/rfqs/{transient['id']}").json()["status"] == "retry_pending"
        retry = client.post(
            f"/api/v1/rfqs/{transient['id']}/retry",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert retry.status_code == 202, retry.text
        SendRfq(
            SqlAlchemyUnitOfWork,
            attachment_provider,
            SimulatedEmailSender("compras@example.mx"),
        ).execute(UUID(transient["id"]), queue.calls[-1][1], queue.calls[-1][2])
        messages = client.get(f"/api/v1/rfqs/{transient['id']}/messages").json()["messages"]
        assert len(messages) == 1
        assert messages[0]["status"] == "sent"

        ambiguous = _generate(client, tender_id, supplier, contact, product_id, [])
        _approve(client, ambiguous["id"])
        client.post(
            f"/api/v1/rfqs/{ambiguous['id']}/send",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        with pytest.raises(AmbiguousEmailDeliveryError):
            SendRfq(
                SqlAlchemyUnitOfWork,
                attachment_provider,
                AmbiguousSender(),
            ).execute(UUID(ambiguous["id"]), queue.calls[-1][1], queue.calls[-1][2])
        assert client.get(f"/api/v1/rfqs/{ambiguous['id']}").json()["status"] == "failed"
        unsafe_retry = client.post(
            f"/api/v1/rfqs/{ambiguous['id']}/retry",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert unsafe_retry.status_code == 409
        messages = client.get(f"/api/v1/rfqs/{ambiguous['id']}/messages").json()["messages"]
        assert len(messages) == 1
    finally:
        app.dependency_overrides.clear()
