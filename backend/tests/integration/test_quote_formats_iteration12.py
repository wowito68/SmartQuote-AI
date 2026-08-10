from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

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
from app.application.use_cases.quote_analysis import AnalyzeQuote
from app.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.email.jinja_template_renderer import JinjaTemplateRenderer
from app.infrastructure.email.stored_document_attachment_provider import (
    StoredDocumentAttachmentProvider,
)
from app.infrastructure.email.template_email_composer import TemplateEmailComposer
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import app
from tests.fixtures.quote_files import minimal_docx_bytes, minimal_xlsx_bytes
from tests.integration.test_quote_iteration12 import (
    QuoteTextExtractorV2,
    RecordingQuoteQueueV2,
    _prepare_sent_rfq,
)
from tests.integration.test_rfq_pipeline import RecordingRfqQueue
from tests.integration.test_supplier_discovery_pipeline import (
    FakeSupplierSearchService,
    RecordingSupplierQueue,
    configure_dependencies,
)

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


class OfficeQuoteAI(AIExtractionService):
    def extract(self, request: AIExtractionRequest) -> AIExtractionResult:
        source = request.pages[0]
        locator = str(source["locator"])
        text = " ".join(str(source["text"]).split())
        fragment = text[: min(len(text), 80)]
        return AIExtractionResult(
            payload={
                "summary": {
                    "currency": "MXN",
                    "subtotal": None,
                    "tax": None,
                    "total": None,
                    "delivery_days": None,
                    "valid_until": None,
                    "commercial_terms": None,
                    "notes": None,
                    "field_statuses": {
                        "currency": "found",
                        "subtotal": "not_found",
                        "tax": "not_found",
                        "total": "not_found",
                        "delivery_days": "not_found",
                        "valid_until": "not_found",
                        "commercial_terms": "not_found",
                    },
                    "evidence": [
                        {
                            "field": "currency",
                            "locator": locator,
                            "fragment": fragment,
                            "status": "found",
                            "confidence": 0.90,
                        }
                    ],
                },
                "items": [
                    {
                        "product_name": "Sensor industrial",
                        "description": None,
                        "brand": None,
                        "model": None,
                        "quantity": 1,
                        "unit": "piece",
                        "unit_price": 1250,
                        "total_price": 1250,
                        "currency": "MXN",
                        "delivery_days": None,
                        "quoted_specifications": {},
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
                            "delivery_days": "not_found",
                        },
                        "evidence": [
                            {
                                "field": "item",
                                "locator": locator,
                                "fragment": fragment,
                                "status": "found",
                                "confidence": 0.90,
                            }
                        ],
                    }
                ],
            },
            model="gpt-test-office",
            provider_response_id="resp_office",
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=Decimal("0.000150"),
            duration_ms=5,
        )


@pytest.mark.parametrize(
    ("filename", "mime_type", "content", "locator_prefix"),
    [
        (
            "supplier.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            minimal_xlsx_bytes(),
            "sheet:Cotizacion:row:",
        ),
        (
            "supplier.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            minimal_docx_bytes(),
            "paragraph:",
        ),
    ],
)
def test_existing_office_reader_remains_compatible_with_explicit_analysis(
    tmp_path: Path,
    filename: str,
    mime_type: str,
    content: bytes,
    locator_prefix: str,
) -> None:
    configure_dependencies(RecordingSupplierQueue(), FakeSupplierSearchService())
    quote_queue = RecordingQuoteQueueV2()
    rfq_queue = RecordingRfqQueue()
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
        uploaded = client.post(
            f"/api/v1/tenders/{tender_id}/quotes",
            data={
                "uploaded_by_user_id": SYSTEM_USER_ID,
                "supplier_id": rfq["supplier_id"],
                "rfq_request_id": rfq["id"],
            },
            files={"files": (filename, content, mime_type)},
        )
        assert uploaded.status_code == 202, uploaded.text
        assert uploaded.json()["queued"] is False
        quote_id = UUID(uploaded.json()["quote"]["id"])

        queued = client.post(
            f"/api/v1/quotes/{quote_id}/analyze",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert queued.status_code == 202, queued.text
        task_id = UUID(queued.json()["task_id"])

        AnalyzeQuote(
            SqlAlchemyUnitOfWork,
            storage,
            QuoteTextExtractorV2(),
            OfficeQuoteAI(),
            FilePromptRegistry(),
            prompt_version="2.0.0",
            model="gpt-test-office",
            temperature=0,
        ).execute(quote_id, task_id)

        analysis = client.get(f"/api/v1/quotes/{quote_id}/analysis")
        assert analysis.status_code == 200, analysis.text
        payload = analysis.json()
        assert payload["quote_status"] == "pending_review"
        assert payload["artifact"] is not None
        evidence = payload["evidence"]
        assert evidence
        assert any(item["locator"].startswith(locator_prefix) for item in evidence)
    finally:
        app.dependency_overrides.clear()
