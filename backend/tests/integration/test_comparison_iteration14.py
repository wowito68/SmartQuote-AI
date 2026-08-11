from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.dependencies import (
    get_attachment_provider,
    get_email_composer,
    get_file_storage,
    get_quote_analysis_queue,
    get_rfq_delivery_queue,
)
from app.application.use_cases.quotes import ProcessSupplierQuote
from app.application.use_cases.rfqs import DeliverRfq
from app.config.settings import get_settings
from app.domain.quotes.value_objects import QuoteStatus
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.comparison import (
    ComparisonItemModel,
    ComparisonModel,
    ComparisonOfferModel,
)
from app.infrastructure.db.models.quote import QuoteModel
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
from tests.integration.test_quote_comparison_pipeline import (
    FakeQuoteAIService,
    FakeQuoteTextExtractor,
    RecordingQuoteQueue,
)
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

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
FIXTURES = Path(__file__).parents[1] / "fixtures"


def _approved_quote(client: TestClient, tmp_path: Path) -> tuple[str, UUID]:
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
    rfq = next(item for item in generated.json()["generated"] if item["to_recipients"])
    assert client.post(
        f"/api/v1/rfqs/{rfq['id']}/approve",
        json={"approved_by_user_id": SYSTEM_USER_ID},
    ).status_code == 200
    assert client.post(
        f"/api/v1/rfqs/{rfq['id']}/send",
        json={"requested_by_user_id": SYSTEM_USER_ID},
    ).status_code == 202
    DeliverRfq(
        SqlAlchemyUnitOfWork,
        attachment_provider,
        RecordingEmailSender(),
    ).execute(UUID(rfq["id"]))

    quote_pdf = (FIXTURES / "sample_text.pdf").read_bytes()
    uploaded = client.post(
        f"/api/v1/tenders/{tender_id}/suppliers/{rfq['tender_supplier_id']}/quotes",
        data={"uploaded_by_user_id": SYSTEM_USER_ID},
        files={"files": ("supplier-quote.pdf", quote_pdf, "application/pdf")},
    )
    assert uploaded.status_code == 202, uploaded.text
    quote_id = UUID(uploaded.json()["id"])
    ProcessSupplierQuote(
        SqlAlchemyUnitOfWork,
        storage,
        FakeQuoteTextExtractor(),
        FakeQuoteAIService(),
        FilePromptRegistry(),
        prompt_version=settings.quote_ai_prompt_version,
        model="gpt-test-quote",
        temperature=0,
    ).execute(quote_id)
    approved = client.post(
        f"/api/v1/quotes/{quote_id}/review",
        json={"reviewer_user_id": SYSTEM_USER_ID, "action": "approve"},
    )
    assert approved.status_code == 200, approved.text
    return tender_id, quote_id


def test_comparison_v2_is_descriptive_idempotent_and_auditable(tmp_path: Path) -> None:
    client = TestClient(app)
    try:
        tender_id, quote_id = _approved_quote(client, tmp_path)
        created = client.post(
            f"/api/v1/tenders/{tender_id}/comparisons",
            json={"created_by_user_id": SYSTEM_USER_ID},
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["status"] == "ready"
        assert payload["comparison_version"] == "1.0.0"
        assert payload["items"]
        assert "recommendation" not in payload
        assert "score" not in str(payload).lower()
        assert payload["items"][0]["offers"][0]["quote_id"] == str(quote_id)
        assert payload["items"][0]["offers"][0]["evidence_id"] is not None

        repeated = client.post(
            f"/api/v1/tenders/{tender_id}/comparisons",
            json={"generated_by_user_id": SYSTEM_USER_ID},
        )
        assert repeated.status_code == 201, repeated.text
        assert repeated.json()["id"] == payload["id"]
        assert repeated.json()["comparison_key"] == payload["comparison_key"]

        latest = client.get(f"/api/v1/tenders/{tender_id}/comparisons")
        by_id = client.get(f"/api/v1/comparisons/{payload['id']}")
        assert latest.status_code == 200
        assert by_id.status_code == 200
        assert latest.json()["id"] == payload["id"]
        assert by_id.json()["quotes_version"] == payload["quotes_version"]

        with SessionLocal() as session:
            quote = session.get(QuoteModel, quote_id)
            assert quote is not None
            assert quote.status == QuoteStatus.APPROVED.value
            assert session.scalar(select(func.count()).select_from(ComparisonModel)) == 1
            assert session.scalar(select(func.count()).select_from(ComparisonItemModel)) >= 1
            assert session.scalar(select(func.count()).select_from(ComparisonOfferModel)) >= 1
            events = set(
                session.scalars(
                    select(AuditEventModel.event_type).where(
                        AuditEventModel.aggregate_type == "comparison"
                    )
                )
            )
        assert "comparison.created" in events
        assert "comparison.ready" in events
        assert "RecommendationGenerated" not in events
    finally:
        app.dependency_overrides.clear()
