from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_ai_catalog_pipeline import PAGE_TEXT
from tests.integration.test_rfq_pipeline import (
    RecordingEmailSender,
    RecordingRfqQueue,
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
    get_file_storage,
    get_quote_analysis_queue,
    get_rfq_delivery_queue,
)
from app.application.ports.ai_extraction_service import (
    AIExtractionRequest,
    AIExtractionResult,
    AIExtractionService,
)
from app.application.ports.document_text_extractor import (
    DocumentTextExtractor,
    ExtractedPage,
    TextExtractionResult,
)
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.use_cases.quotes import ProcessSupplierQuote
from app.application.use_cases.rfqs import DeliverRfq
from app.application.use_cases.supplier_discovery import ProcessSupplierDiscoveryRun
from app.config.settings import get_settings
from app.domain.quotes.value_objects import QuoteExtractionRunStatus, QuoteStatus
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.suppliers.value_objects import SupplierStatus
from app.domain.tenders.value_objects import TenderStatus
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.quote import (
    ComparisonRunModel,
    QuoteExtractionRunModel,
    QuoteItemModel,
    QuoteModel,
)
from app.infrastructure.db.models.rfq import RfqRequestModel
from app.infrastructure.db.models.supplier import TenderSupplierModel
from app.infrastructure.db.models.tender import TenderModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.email.jinja_template_renderer import JinjaTemplateRenderer
from app.infrastructure.email.stored_document_attachment_provider import (
    StoredDocumentAttachmentProvider,
)
from app.infrastructure.email.template_email_composer import TemplateEmailComposer
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
FIXTURES = Path(__file__).parents[1] / "fixtures"
QUOTE_TEXT = (
    "Cotización: Cable de cobre, cantidad 2000 metros, precio unitario 18.50 MXN, "
    "total 37000.00 MXN. Cumple calibre 2 AWG, aislamiento XLPE y tensión 600 V. "
    "Entrega en 7 días."
)


class RecordingQuoteQueue(QuoteAnalysisQueue):
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str | None]] = []

    def enqueue(self, quote_id: UUID, correlation_id: str | None = None) -> None:
        self.calls.append((quote_id, correlation_id))


class FakeQuoteTextExtractor(DocumentTextExtractor):
    @property
    def name(self) -> str:
        return "fake-quote-text"

    @property
    def version(self) -> str:
        return "1.0.0"

    def extract(self, content: bytes) -> TextExtractionResult:
        assert content.startswith(b"%PDF-")
        return TextExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text=QUOTE_TEXT,
                    width=612,
                    height=792,
                    duration_ms=3,
                ),
            ),
            duration_ms=3,
        )


class FakeQuoteAIService(AIExtractionService):
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, request: AIExtractionRequest) -> AIExtractionResult:
        self.calls += 1
        assert request.prompt.name == "quote_extraction"
        assert request.pages[0]["page_number"] == 1
        return AIExtractionResult(
            payload={
                "items": [
                    {
                        "product_name": "Cable de cobre",
                        "brand": "Marca Test",
                        "model": "CU-2AWG",
                        "quantity": 2000,
                        "unit_price": 18.5,
                        "total_price": 37000,
                        "currency": "MXN",
                        "delivery_days": 7,
                        "technical_compliance": True,
                        "notes": "Cumple especificación indicada",
                        "evidence": {
                            "page": 1,
                            "fragment": "Cable de cobre, cantidad 2000 metros",
                            "confidence": 0.97,
                        },
                    }
                ]
            },
            model="gpt-test-quote",
            provider_response_id="resp_quote_1",
            input_tokens=420,
            output_tokens=110,
            estimated_cost_usd=Decimal("0.000530"),
            duration_ms=45,
        )


def test_quote_upload_extraction_review_comparison_and_retries_are_idempotent(
    tmp_path: Path,
) -> None:
    supplier_queue = RecordingSupplierQueue()
    configure_dependencies(supplier_queue, FakeSupplierSearchService())
    rfq_queue = RecordingRfqQueue()
    quote_queue = RecordingQuoteQueue()
    storage = LocalFileStorage(tmp_path / "private")
    settings = get_settings()
    attachment_provider = StoredDocumentAttachmentProvider(
        SqlAlchemyUnitOfWork,
        storage,
        settings.max_email_attachment_bytes,
    )
    app.dependency_overrides[get_file_storage] = lambda: storage
    app.dependency_overrides[get_rfq_delivery_queue] = lambda: rfq_queue
    app.dependency_overrides[get_quote_analysis_queue] = lambda: quote_queue
    app.dependency_overrides[get_attachment_provider] = lambda: attachment_provider
    app.dependency_overrides[get_email_composer] = lambda: TemplateEmailComposer(
        JinjaTemplateRenderer()
    )
    client = TestClient(app)

    try:
        tender_id = create_approved_catalog(client)
        approve_suppliers(client, tender_id)
        response_deadline = datetime.now(UTC) + timedelta(days=10)
        generated = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs/generate",
            json={
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": response_deadline.isoformat(),
            },
        )
        assert generated.status_code == 201, generated.text
        rfq = next(
            item
            for item in generated.json()["generated"]
            if item["to_recipients"]
            and item["to_recipients"][0] == "ventas@conductores.example.mx"
        )
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
        DeliverRfq(
            SqlAlchemyUnitOfWork,
            attachment_provider,
            RecordingEmailSender(),
        ).execute(UUID(rfq["id"]))
        assert client.get(f"/api/v1/rfqs/{rfq['id']}").json()["status"] == "sent"

        quote_pdf = (FIXTURES / "sample_text.pdf").read_bytes()
        uploaded = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/{rfq['tender_supplier_id']}/quotes",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("supplier-quote.pdf", quote_pdf, "application/pdf")},
            headers={"X-Correlation-ID": "iteration-9-e2e"},
        )
        assert uploaded.status_code == 202, uploaded.text
        quote_id = UUID(uploaded.json()["id"])
        assert uploaded.json()["status"] == "validating"
        assert quote_queue.calls == [(quote_id, "iteration-9-e2e")]

        duplicate = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/{rfq['tender_supplier_id']}/quotes",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("supplier-quote-copy.pdf", quote_pdf, "application/pdf")},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "duplicate_quote"

        ai_service = FakeQuoteAIService()
        processor = ProcessSupplierQuote(
            SqlAlchemyUnitOfWork,
            storage,
            FakeQuoteTextExtractor(),
            ai_service,
            FilePromptRegistry(),
            prompt_version=settings.quote_ai_prompt_version,
            model="gpt-test-quote",
            temperature=0,
        )
        assert processor.execute(quote_id) == quote_id
        assert ai_service.calls == 1
        assert processor.execute(quote_id) == quote_id
        assert ai_service.calls == 1

        extracted = client.get(f"/api/v1/quotes/{quote_id}")
        assert extracted.status_code == 200, extracted.text
        quote_payload = extracted.json()
        assert quote_payload["status"] == "pending_review"
        assert quote_payload["items"][0]["catalog_product_id"] is not None
        assert quote_payload["items"][0]["total_price"] == "37000.000000"
        assert quote_payload["items"][0]["source_page"] == 1
        assert quote_payload["items"][0]["evidence_fragment"] in QUOTE_TEXT

        listed = client.get(f"/api/v1/tenders/{tender_id}/quotes")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["supplier_id"] == rfq["supplier_id"]

        reviewed = client.post(
            f"/api/v1/quotes/{quote_id}/review",
            json={"reviewer_user_id": SYSTEM_USER_ID, "action": "approve"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "approved"

        comparison = client.post(
            f"/api/v1/tenders/{tender_id}/comparison",
            json={"generated_by_user_id": SYSTEM_USER_ID},
        )
        assert comparison.status_code == 201, comparison.text
        comparison_payload = comparison.json()
        assert comparison_payload["recommendation"]["human_review_required"] is True
        assert comparison_payload["recommendation"]["decision"] == "recommendation_only"
        assert comparison_payload["recommendation"]["recommended_supplier_id"] == rfq["supplier_id"]
        assert comparison_payload["rows"][0]["source"]["quote_id"] == str(quote_id)
        assert comparison_payload["rows"][0]["source"]["evidence_fragment"] in QUOTE_TEXT

        idempotent = client.post(
            f"/api/v1/tenders/{tender_id}/comparison",
            json={"generated_by_user_id": SYSTEM_USER_ID},
        )
        assert idempotent.status_code == 201
        assert idempotent.json()["id"] == comparison_payload["id"]
        latest = client.get(f"/api/v1/tenders/{tender_id}/comparison")
        assert latest.status_code == 200
        assert latest.json()["comparison_key"] == comparison_payload["comparison_key"]

        with SessionLocal() as session:
            quote_model = session.get(QuoteModel, quote_id)
            assert quote_model is not None
            assert quote_model.status == QuoteStatus.INCLUDED_IN_COMPARISON.value
            run = session.scalar(
                select(QuoteExtractionRunModel).where(
                    QuoteExtractionRunModel.quote_id == quote_id
                )
            )
            assert run is not None
            assert run.status == QuoteExtractionRunStatus.COMPLETED.value
            assert run.model == "gpt-test-quote"
            assert run.input_tokens == 420
            assert run.output_tokens == 110
            assert run.estimated_cost_usd == Decimal("0.000530")
            assert session.scalar(select(func.count()).select_from(QuoteItemModel)) == 1
            assert session.scalar(select(func.count()).select_from(ComparisonRunModel)) == 1
            tender_supplier = session.get(TenderSupplierModel, UUID(rfq["tender_supplier_id"]))
            assert tender_supplier is not None
            assert tender_supplier.status == SupplierStatus.RESPONDED.value
            rfq_model = session.get(RfqRequestModel, UUID(rfq["id"]))
            assert rfq_model is not None
            assert rfq_model.status == RfqStatus.RESPONDED.value
            tender = session.get(TenderModel, UUID(tender_id))
            assert tender is not None
            assert tender.status == TenderStatus.COMPARISON_READY.value
            events = set(session.scalars(select(AuditEventModel.event_type)))
        assert {
            "QuoteUploaded",
            "QuoteExtractionStarted",
            "QuoteExtractedAndNormalized",
            "QuoteApproved",
            "ComparisonGenerated",
            "RecommendationGenerated",
        } <= events
    finally:
        app.dependency_overrides.clear()


def test_quote_requires_sent_rfq_and_comparison_requires_approved_quote(tmp_path: Path) -> None:
    supplier_queue = RecordingSupplierQueue()
    configure_dependencies(supplier_queue, FakeSupplierSearchService())
    app.dependency_overrides[get_rfq_delivery_queue] = lambda: RecordingRfqQueue()
    app.dependency_overrides[get_quote_analysis_queue] = lambda: RecordingQuoteQueue()
    storage = LocalFileStorage(tmp_path / "private")
    app.dependency_overrides[get_file_storage] = lambda: storage
    client = TestClient(app)
    try:
        tender_id = create_approved_catalog(client)
        approve_suppliers(client, tender_id)
        generated = client.post(
            f"/api/v1/tenders/{tender_id}/rfqs/generate",
            json={
                "generated_by_user_id": SYSTEM_USER_ID,
                "response_deadline": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            },
        )
        rfq = next(item for item in generated.json()["generated"] if item["to_recipients"])
        quote_pdf = (FIXTURES / "sample_text.pdf").read_bytes()
        blocked = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/{rfq['tender_supplier_id']}/quotes",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("too-early.pdf", quote_pdf, "application/pdf")},
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "invalid_quote_state"

        comparison = client.post(
            f"/api/v1/tenders/{tender_id}/comparison",
            json={"generated_by_user_id": SYSTEM_USER_ID},
        )
        assert comparison.status_code == 409
        assert comparison.json()["code"] == "comparison_not_ready"
        missing = client.get(f"/api/v1/tenders/{tender_id}/comparison")
        assert missing.status_code == 404
        assert missing.json()["code"] == "comparison_not_found"
    finally:
        app.dependency_overrides.clear()
