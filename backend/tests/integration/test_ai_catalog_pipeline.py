from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.dependencies import get_ai_extraction_queue, get_processing_queue
from app.application.ports.ai_extraction_queue import AIExtractionQueue
from app.application.ports.ai_extraction_service import AIExtractionResult, AIExtractionService
from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.application.services.catalog_normalizer import CatalogNormalizer
from app.application.use_cases.catalog import (
    ProcessAIExtractionRun,
    RequestTenderCatalogExtraction,
)
from app.domain.catalog.exceptions import AIResponseValidationError
from app.domain.catalog.value_objects import AIExtractionRunStatus
from app.domain.documents.processing import DocumentPage, ExtractionRun
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.catalog import (
    AIExtractionRunModel,
    CatalogProductModel,
    CatalogSnapshotModel,
    EvidenceReferenceModel,
    ExtractedEvidenceModel,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
FIXTURES = Path(__file__).parents[1] / "fixtures"
PAGE_TEXT = (
    "Partida 1 Cable de cobre 2 AWG, cantidad 2000 metros. "
    "Aislamiento XLPE, tensión 600 V. Entrega en almacén central."
)


class RecordingDocumentQueue(DocumentProcessingQueue):
    def enqueue(self, document_id: UUID) -> None:
        pass


class RecordingAIQueue(AIExtractionQueue):
    def __init__(self) -> None:
        self.run_ids: list[UUID] = []

    def enqueue(self, run_id: UUID) -> None:
        self.run_ids.append(run_id)


class FakeAIService(AIExtractionService):
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def extract(self, request) -> AIExtractionResult:
        self.calls += 1
        return AIExtractionResult(
            payload=self.payload,
            model="gpt-test-structured",
            provider_response_id="resp_catalog_1",
            input_tokens=900,
            output_tokens=240,
            estimated_cost_usd=Decimal("0.001620"),
            duration_ms=321,
        )


def create_ready_document(client: TestClient) -> tuple[str, str]:
    tender = client.post(
        "/api/v1/tenders",
        json={"title": "AI catalog tender", "created_by_user_id": SYSTEM_USER_ID},
    )
    assert tender.status_code == 201, tender.text
    tender_id = tender.json()["id"]
    upload = client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        data={"uploaded_by_user_id": SYSTEM_USER_ID},
        files={
            "files": (
                "sample_text.pdf",
                (FIXTURES / "sample_text.pdf").read_bytes(),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["items"][0]["id"]
    with SqlAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id(UUID(document_id))
        assert document is not None
        document.mark_queued()
        document.start_processing()
        document.mark_text_extracted()
        document.mark_ready_for_ai()
        uow.documents.update(document)
        run = uow.extractions.create_run(
            ExtractionRun(
                document_id=document.id,
                processing_key="e" * 64,
                extractor_name="pymupdf",
                extractor_version="1.26.7",
                configuration={"test": True},
            )
        )
        pages = [
            DocumentPage(
                document_id=document.id,
                extraction_run_id=run.id,
                page_number=1,
                text=PAGE_TEXT,
                width=612,
                height=792,
                duration_ms=5,
            )
        ]
        run.complete(pages, 5)
        uow.extractions.update_run(run)
        uow.extractions.replace_pages(run.id, pages)
        uow.commit()
    return tender_id, document_id


def valid_payload() -> dict:
    return {
        "products": [
            {
                "item_number": "1",
                "name": " Cable   de cobre ",
                "description": "Conductor para instalación eléctrica",
                "quantity": 2000,
                "unit": "metros",
                "suggested_category": None,
                "technical_specifications": [
                    {"name": "Calibre", "value": "2 AWG"},
                    {"name": "Aislamiento", "value": "XLPE"},
                    {"name": "Tensión", "value": "600 V"},
                ],
                "observations": "Entrega en almacén central",
                "confidence": 0.94,
                "evidence": [
                    {
                        "page": 1,
                        "fragment": "Cable de cobre 2 AWG, cantidad 2000 metros.",
                        "confidence": 0.97,
                        "coordinates": None,
                    }
                ],
            }
        ]
    }


def test_complete_ai_catalog_flow_is_auditable_reviewable_and_idempotent() -> None:
    ai_queue = RecordingAIQueue()
    app.dependency_overrides[get_processing_queue] = lambda: RecordingDocumentQueue()
    app.dependency_overrides[get_ai_extraction_queue] = lambda: ai_queue
    client = TestClient(app)
    try:
        tender_id, document_id = create_ready_document(client)
        request = client.post(f"/api/v1/tenders/{tender_id}/catalog/extract")
        assert request.status_code == 202, request.text
        assert request.json()["queued"] == 1
        run_id = ai_queue.run_ids[0]

        service = FakeAIService(valid_payload())
        ProcessAIExtractionRun(
            SqlAlchemyUnitOfWork,
            service,
            FilePromptRegistry(),
            CatalogNormalizer(),
        ).execute(run_id)
        assert service.calls == 1

        catalog = client.get(f"/api/v1/tenders/{tender_id}/catalog")
        assert catalog.status_code == 200, catalog.text
        body = catalog.json()
        assert body["metrics"]["products_total"] == 1
        assert body["metrics"]["products_pending_review"] == 1
        assert body["metrics"]["input_tokens"] == 900
        assert body["metrics"]["estimated_cost_usd"] == "0.001620"
        product = body["products"][0]
        product_id = product["id"]
        assert product["status"] == "pending_review"
        assert product["name"] == "Cable de cobre"
        assert product["unit"] == "m"
        assert product["category"] == "Eléctrico"
        assert product["evidence"][0]["document_id"] == document_id
        assert product["evidence"][0]["page_number"] == 1

        edited = client.put(
            f"/api/v1/catalog/{product_id}",
            json={
                "action": "edit",
                "reviewer_user_id": SYSTEM_USER_ID,
                "name": "Cable de cobre certificado",
                "quantity": "2500",
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["manual_edit_count"] == 1
        assert edited.json()["original_payload"]["name"].strip() == "Cable   de cobre"

        approved = client.put(
            f"/api/v1/catalog/{product_id}",
            json={"action": "approve", "reviewer_user_id": SYSTEM_USER_ID},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        snapshot = client.post(
            f"/api/v1/tenders/{tender_id}/catalog/approve",
            json={"approved_by_user_id": SYSTEM_USER_ID},
        )
        assert snapshot.status_code == 201, snapshot.text
        assert snapshot.json()["version"] == 1
        assert snapshot.json()["products"][0]["name"] == "Cable de cobre certificado"

        second = client.post(f"/api/v1/tenders/{tender_id}/catalog/extract")
        assert second.status_code == 202
        assert second.json()["queued"] == 0
        assert second.json()["reused"] == 1
        assert ai_queue.run_ids == [run_id]

        changed_model = RequestTenderCatalogExtraction(
            SqlAlchemyUnitOfWork,
            ai_queue,
            FilePromptRegistry(),
            prompt_version="1.0.0",
            model="gpt-test-next",
            temperature=0,
        ).execute(UUID(tender_id))
        assert changed_model.queued == 1
        assert len(ai_queue.run_ids) == 2

        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(CatalogProductModel)) == 1
            assert session.scalar(select(func.count()).select_from(ExtractedEvidenceModel)) == 1
            assert session.scalar(select(func.count()).select_from(EvidenceReferenceModel)) == 1
            assert session.scalar(select(func.count()).select_from(CatalogSnapshotModel)) == 1
            run = session.get(AIExtractionRunModel, run_id)
            assert run is not None
            assert run.status == AIExtractionRunStatus.COMPLETED.value
            assert run.prompt_version == "1.0.0"
            event_types = set(session.scalars(select(AuditEventModel.event_type)))
        assert {
            "AIExtractionStarted",
            "AIExtractionCompleted",
            "ProductCandidateCreated",
            "CatalogNormalized",
            "CatalogReviewStarted",
            "ProductApproved",
            "CatalogApproved",
        }.issubset(event_types)
    finally:
        app.dependency_overrides.clear()


def test_invalid_ai_evidence_rolls_back_candidates_and_records_failed_run() -> None:
    ai_queue = RecordingAIQueue()
    app.dependency_overrides[get_processing_queue] = lambda: RecordingDocumentQueue()
    app.dependency_overrides[get_ai_extraction_queue] = lambda: ai_queue
    client = TestClient(app)
    try:
        tender_id, _ = create_ready_document(client)
        response = client.post(f"/api/v1/tenders/{tender_id}/catalog/extract")
        run_id = ai_queue.run_ids[0]
        payload = valid_payload()
        payload["products"][0]["evidence"][0]["fragment"] = "invented unsupported text"
        with pytest.raises(AIResponseValidationError):
            ProcessAIExtractionRun(
                SqlAlchemyUnitOfWork,
                FakeAIService(payload),
                FilePromptRegistry(),
                CatalogNormalizer(),
            ).execute(run_id)
        with SessionLocal() as session:
            run = session.get(AIExtractionRunModel, run_id)
            assert run is not None
            assert run.status == "failed"
            assert run.invalid_json_count == 1
            assert session.scalar(select(func.count()).select_from(CatalogProductModel)) == 0
        assert response.status_code == 202
    finally:
        app.dependency_overrides.clear()


def test_product_can_be_rejected_through_review_api() -> None:
    ai_queue = RecordingAIQueue()
    app.dependency_overrides[get_processing_queue] = lambda: RecordingDocumentQueue()
    app.dependency_overrides[get_ai_extraction_queue] = lambda: ai_queue
    client = TestClient(app)
    try:
        tender_id, _ = create_ready_document(client)
        client.post(f"/api/v1/tenders/{tender_id}/catalog/extract")
        payload = valid_payload()
        payload["products"][0]["name"] = "Producto no requerido"
        ProcessAIExtractionRun(
            SqlAlchemyUnitOfWork,
            FakeAIService(payload),
            FilePromptRegistry(),
            CatalogNormalizer(),
        ).execute(ai_queue.run_ids[0])
        product_id = client.get(f"/api/v1/tenders/{tender_id}/catalog").json()["products"][0]["id"]
        rejected = client.put(
            f"/api/v1/catalog/{product_id}",
            json={
                "action": "reject",
                "reviewer_user_id": SYSTEM_USER_ID,
                "rejection_reason": "La partida no pertenece al alcance",
            },
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"
        approval = client.post(
            f"/api/v1/tenders/{tender_id}/catalog/approve",
            json={"approved_by_user_id": SYSTEM_USER_ID},
        )
        assert approval.status_code == 409
        assert approval.json()["code"] == "invalid_catalog_state"
    finally:
        app.dependency_overrides.clear()


def test_real_celery_worker_processes_ai_queue_with_mocked_openai(monkeypatch) -> None:
    import json
    import time
    from types import SimpleNamespace

    from celery.contrib.testing.worker import start_worker
    from pydantic import SecretStr

    from app.config.settings import get_settings
    from app.infrastructure.tasks import catalog_extraction as catalog_tasks
    from app.infrastructure.tasks.celery_app import celery_app

    settings = get_settings()
    if settings.celery_broker_url.get_secret_value().startswith("memory"):
        return

    class FakeHTTPClient:
        def __init__(self, **kwargs) -> None:
            self.responses = self

        def create(self, **kwargs):
            return SimpleNamespace(
                id="resp_worker",
                model="gpt-worker-test",
                output_text=json.dumps(valid_payload()),
                usage=SimpleNamespace(input_tokens=700, output_tokens=200),
            )

    worker_settings = settings.model_copy(
        update={
            "openai_api_key": SecretStr("test-key"),
            "ai_input_cost_per_million_tokens": 1.0,
            "ai_output_cost_per_million_tokens": 3.0,
        }
    )
    monkeypatch.setattr(catalog_tasks, "get_settings", lambda: worker_settings)
    monkeypatch.setattr(catalog_tasks, "OpenAIResponsesHTTPClient", FakeHTTPClient)
    app.dependency_overrides[get_processing_queue] = lambda: RecordingDocumentQueue()
    client = TestClient(app)
    try:
        with start_worker(
            celery_app,
            pool="solo",
            perform_ping_check=False,
            queues=["ai-extraction"],
        ):
            tender_id, _ = create_ready_document(client)
            response = client.post(f"/api/v1/tenders/{tender_id}/catalog/extract")
            assert response.status_code == 202
            run_id = response.json()["runs"][0]["id"]
            deadline = time.monotonic() + 30
            run_status = "queued"
            while time.monotonic() < deadline:
                with SessionLocal() as session:
                    model = session.get(AIExtractionRunModel, UUID(run_id))
                    run_status = model.status if model else "missing"
                if run_status in {"completed", "failed"}:
                    break
                time.sleep(0.25)
        assert run_status == "completed"
        catalog = client.get(f"/api/v1/tenders/{tender_id}/catalog").json()
        assert catalog["metrics"]["products_pending_review"] == 1
        assert catalog["metrics"]["input_tokens"] == 700
    finally:
        app.dependency_overrides.clear()
