from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
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
from app.application.use_cases.quotes import ProcessSupplierQuote
from app.application.use_cases.rfqs import DeliverRfq
from app.config.settings import get_settings
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.quote import (
    QuoteDocumentModel,
    QuoteEvidenceReferenceModel,
    QuoteExtractionRunModel,
    QuoteItemModel,
    QuoteItemRevisionModel,
    QuoteTaskRecordModel,
)
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
    "Cotización Cable de cobre. cantidad 2000 metros, precio unitario 18.50 MXN, "
    "total 38000.00 MXN. Cumple calibre 2 AWG, aislamiento XLPE y tensión 600 V. "
    "Entrega en 7 días."
)


class RecordingQuoteQueueV2(QuoteAnalysisQueue):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue(
        self,
        quote_id: UUID,
        correlation_id: str | None = None,
        *,
        task_record_id: UUID | None = None,
        force_reprocess: bool = False,
    ) -> None:
        self.calls.append(
            {
                "quote_id": quote_id,
                "correlation_id": correlation_id,
                "task_record_id": task_record_id,
                "force_reprocess": force_reprocess,
            }
        )


class QuoteTextExtractorV2(DocumentTextExtractor):
    @property
    def name(self) -> str:
        return "quote-test-pdf"

    @property
    def version(self) -> str:
        return "2.0.0"

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
                    duration_ms=2,
                ),
            ),
            duration_ms=2,
        )


class QuoteAIServiceV2(AIExtractionService):
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, request: AIExtractionRequest) -> AIExtractionResult:
        self.calls += 1
        assert request.prompt.name == "quote_extraction"
        assert request.prompt.version == "2.0.0"
        assert request.pages[0]["locator"] == "page:1"
        return AIExtractionResult(
            payload={
                "summary": {
                    "currency": "MXN",
                    "subtotal": None,
                    "tax": None,
                    "total": 38000,
                    "delivery_days": 7,
                    "valid_until": None,
                    "commercial_terms": None,
                    "notes": None,
                    "field_statuses": {
                        "currency": "found",
                        "subtotal": "not_found",
                        "tax": "not_found",
                        "total": "found",
                        "delivery_days": "found",
                        "valid_until": "not_found",
                        "commercial_terms": "not_found",
                    },
                    "evidence": [
                        {
                            "field": "currency",
                            "locator": "page:1",
                            "fragment": "precio unitario 18.50 MXN",
                            "status": "found",
                            "confidence": 0.99,
                        },
                        {
                            "field": "total",
                            "locator": "page:1",
                            "fragment": "total 38000.00 MXN",
                            "status": "found",
                            "confidence": 0.98,
                        },
                        {
                            "field": "delivery_days",
                            "locator": "page:1",
                            "fragment": "Entrega en 7 días",
                            "status": "found",
                            "confidence": 0.97,
                        },
                    ],
                },
                "items": [
                    {
                        "product_name": "Cable de cobre",
                        "description": "Cable de cobre industrial",
                        "brand": None,
                        "model": None,
                        "quantity": 2000,
                        "unit": "metros",
                        "unit_price": 18.5,
                        "total_price": 38000,
                        "currency": "MXN",
                        "delivery_days": 7,
                        "quoted_specifications": {
                            "calibre": "2 AWG",
                            "aislamiento": "XLPE",
                            "tension": "600 V",
                        },
                        "technical_compliance": "unknown",
                        "notes": None,
                        "field_statuses": {
                            "brand": "not_found",
                            "model": "not_found",
                            "quantity": "found",
                            "unit": "found",
                            "unit_price": "found",
                            "total_price": "found",
                            "currency": "found",
                            "delivery_days": "found",
                            "technical_compliance": "found",
                        },
                        "evidence": [
                            {
                                "field": "quantity",
                                "locator": "page:1",
                                "fragment": "cantidad 2000 metros",
                                "status": "found",
                                "confidence": 0.99,
                            },
                            {
                                "field": "unit",
                                "locator": "page:1",
                                "fragment": "cantidad 2000 metros",
                                "status": "found",
                                "confidence": 0.99,
                            },
                            {
                                "field": "unit_price",
                                "locator": "page:1",
                                "fragment": "precio unitario 18.50 MXN",
                                "status": "found",
                                "confidence": 0.98,
                            },
                            {
                                "field": "total_price",
                                "locator": "page:1",
                                "fragment": "total 38000.00 MXN",
                                "status": "found",
                                "confidence": 0.98,
                            },
                            {
                                "field": "currency",
                                "locator": "page:1",
                                "fragment": "precio unitario 18.50 MXN",
                                "status": "found",
                                "confidence": 0.99,
                            },
                            {
                                "field": "delivery_days",
                                "locator": "page:1",
                                "fragment": "Entrega en 7 días",
                                "status": "found",
                                "confidence": 0.97,
                            },
                            {
                                "field": "technical_compliance",
                                "locator": "page:1",
                                "fragment": "Cumple calibre 2 AWG",
                                "status": "found",
                                "confidence": 0.90,
                            },
                        ],
                    }
                ],
            },
            model="gpt-test-quote-v2",
            provider_response_id=f"resp_quote_v2_{self.calls}",
            input_tokens=500,
            output_tokens=180,
            estimated_cost_usd=Decimal("0.000680"),
            duration_ms=40,
        )


def _prepare_sent_rfq(client: TestClient, storage: LocalFileStorage) -> tuple[str, dict]:
    tender_id = create_approved_catalog(client)
    approve_suppliers(client, tender_id)
    generated = client.post(
        f"/api/v1/tenders/{tender_id}/rfqs/generate",
        json={
            "generated_by_user_id": SYSTEM_USER_ID,
            "response_deadline": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
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
    settings = get_settings()
    attachment_provider = StoredDocumentAttachmentProvider(
        SqlAlchemyUnitOfWork,
        storage,
        settings.max_email_attachment_bytes,
    )
    DeliverRfq(
        SqlAlchemyUnitOfWork,
        attachment_provider,
        RecordingEmailSender(),
    ).execute(UUID(rfq["id"]))
    return tender_id, rfq


def test_manual_quote_intake_reprocess_evidence_and_human_revision(tmp_path: Path) -> None:
    configure_dependencies(RecordingSupplierQueue(), FakeSupplierSearchService())
    rfq_queue = RecordingRfqQueue()
    quote_queue = RecordingQuoteQueueV2()
    storage = LocalFileStorage(tmp_path / "private")
    settings = get_settings()
    attachment_provider = StoredDocumentAttachmentProvider(
        SqlAlchemyUnitOfWork,
        storage,
        settings.max_email_attachment_bytes,
    )
    app.dependency_overrides[get_file_storage] = lambda: storage
    app.dependency_overrides[get_quote_analysis_queue] = lambda: quote_queue
    app.dependency_overrides[get_rfq_delivery_queue] = lambda: rfq_queue
    app.dependency_overrides[get_attachment_provider] = lambda: attachment_provider
    app.dependency_overrides[get_email_composer] = lambda: TemplateEmailComposer(
        JinjaTemplateRenderer()
    )
    client = TestClient(app)

    try:
        tender_id, rfq = _prepare_sent_rfq(client, storage)
        quote_pdf = (FIXTURES / "sample_text.pdf").read_bytes()
        uploaded = client.post(
            f"/api/v1/tenders/{tender_id}/quotes",
            data={
                "uploaded_by_user_id": SYSTEM_USER_ID,
                "supplier_id": rfq["supplier_id"],
                "rfq_request_id": rfq["id"],
            },
            files={"files": ("supplier-v2.pdf", quote_pdf, "application/pdf")},
            headers={"X-Correlation-ID": "iteration-12-manual"},
        )
        assert uploaded.status_code == 202, uploaded.text
        payload = uploaded.json()
        assert payload["duplicate_detected"] is False
        assert payload["queued"] is True
        quote_id = UUID(payload["quote"]["id"])
        assert payload["quote"]["status"] == "validating"
        assert quote_queue.calls[0]["correlation_id"] == "iteration-12-manual"
        assert quote_queue.calls[0]["task_record_id"] is not None

        duplicate = client.post(
            f"/api/v1/tenders/{tender_id}/quotes",
            data={
                "uploaded_by_user_id": SYSTEM_USER_ID,
                "supplier_id": rfq["supplier_id"],
                "rfq_request_id": rfq["id"],
            },
            files={"files": ("supplier-copy.pdf", quote_pdf, "application/pdf")},
        )
        assert duplicate.status_code == 202, duplicate.text
        assert duplicate.json()["duplicate_detected"] is True
        assert duplicate.json()["quote"]["id"] == str(quote_id)

        processing = client.get(f"/api/v1/quotes/{quote_id}/processing-status")
        assert processing.status_code == 200
        first_task_id = UUID(processing.json()["task_id"])

        ai_service = QuoteAIServiceV2()
        processor = ProcessSupplierQuote(
            SqlAlchemyUnitOfWork,
            storage,
            QuoteTextExtractorV2(),
            ai_service,
            FilePromptRegistry(),
            prompt_version="2.0.0",
            model="gpt-test-quote-v2",
            temperature=0,
        )
        assert processor.execute(quote_id, first_task_id) == quote_id
        assert ai_service.calls == 1

        extracted = client.get(f"/api/v1/quotes/{quote_id}").json()
        assert extracted["status"] == "pending_review"
        assert extracted["items"][0]["match_status"] == "matched"
        assert "PRICE_CALCULATION_MISMATCH" in extracted["items"][0]["warnings"]
        assert extracted["items"][0]["total_price"] == "38000.000000"

        evidence = client.get(f"/api/v1/quotes/{quote_id}/evidence")
        assert evidence.status_code == 200
        assert evidence.json()["total"] >= 7
        document_id = extracted["documents"][0]["id"]
        assert all(item["quote_document_id"] == document_id for item in evidence.json()["items"])
        assert all(item["locator"] == "page:1" for item in evidence.json()["items"])

        reprocessed = client.post(
            f"/api/v1/quotes/{quote_id}/reprocess",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert reprocessed.status_code == 202, reprocessed.text
        second_task_id = UUID(reprocessed.json()["task_id"])
        assert second_task_id != first_task_id
        assert processor.execute(quote_id, second_task_id, force_reprocess=True) == quote_id
        assert ai_service.calls == 2

        after_reprocess = client.get(f"/api/v1/quotes/{quote_id}").json()
        assert len(after_reprocess["extraction_runs"]) == 2
        assert after_reprocess["items"][0]["total_price"] == "38000.000000"
        current_item_id = after_reprocess["items"][0]["id"]

        corrected = client.patch(
            f"/api/v1/quotes/{quote_id}/items/{current_item_id}",
            json={
                "changed_by_user_id": SYSTEM_USER_ID,
                "total_price": 37000,
            },
        )
        assert corrected.status_code == 200, corrected.text
        corrected_item = corrected.json()["items"][0]
        assert corrected_item["total_price"] == "37000.000000"
        assert "PRICE_CALCULATION_MISMATCH" not in corrected_item["warnings"]
        assert corrected_item["original_extracted"]["total_price"] == 38000

        approved = client.post(
            f"/api/v1/quotes/{quote_id}/approve",
            json={"reviewer_user_id": SYSTEM_USER_ID},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        approved_run_id = approved.json()["approved_extraction_run_id"]
        assert approved_run_id == after_reprocess["extraction_runs"][-1]["id"]

        frozen = client.patch(
            f"/api/v1/quotes/{quote_id}/items/{current_item_id}",
            json={
                "changed_by_user_id": SYSTEM_USER_ID,
                "total_price": 36000,
            },
        )
        assert frozen.status_code == 409

        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(QuoteDocumentModel)) == 1
            assert session.scalar(select(func.count()).select_from(QuoteExtractionRunModel)) == 2
            assert session.scalar(select(func.count()).select_from(QuoteTaskRecordModel)) == 2
            assert session.scalar(select(func.count()).select_from(QuoteItemModel)) == 2
            assert session.scalar(
                select(func.count()).select_from(QuoteItemModel).where(QuoteItemModel.is_current.is_(True))
            ) == 1
            assert session.scalar(select(func.count()).select_from(QuoteItemRevisionModel)) == 1
            assert session.scalar(select(func.count()).select_from(QuoteEvidenceReferenceModel)) >= 14
            events = set(session.scalars(select(AuditEventModel.event_type)))
        assert {
            "QuoteReceived",
            "QuoteFileStored",
            "QuoteAnalysisStarted",
            "QuoteAnalyzed",
            "QuoteNormalized",
            "QuoteReprocessed",
            "QuoteItemCorrected",
            "QuoteApproved",
        } <= events
    finally:
        app.dependency_overrides.clear()
