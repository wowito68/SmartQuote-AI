import time
from pathlib import Path
from uuid import UUID

from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import func, select, update

from app.api.dependencies import get_processing_queue
from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.config.settings import get_settings
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.document_processing import (
    DocumentPageModel,
    ExtractionRunModel,
)
from app.infrastructure.db.models.tender import TenderDocumentModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.tasks.celery_app import celery_app
from app.infrastructure.tasks.document_pipeline import (
    evaluate_quality,
    extract_text,
    finalize_document,
    start_pipeline,
    validate_document,
)
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
FIXTURES = Path(__file__).parents[1] / "fixtures"


class RecordingQueue(DocumentProcessingQueue):
    def __init__(self) -> None:
        self.document_ids: list[UUID] = []

    def enqueue(self, document_id: UUID) -> None:
        self.document_ids.append(document_id)


def create_tender(client: TestClient, title: str) -> str:
    response = client.post(
        "/api/v1/tenders",
        json={"title": title, "created_by_user_id": SYSTEM_USER_ID},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload_fixture(client: TestClient, tender_id: str, filename: str) -> str:
    response = client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        data={"uploaded_by_user_id": SYSTEM_USER_ID},
        files={"files": (filename, (FIXTURES / filename).read_bytes(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["status"] == "uploaded"
    return response.json()["items"][0]["id"]


def test_complete_pipeline_persists_pages_quality_and_is_idempotent() -> None:
    queue = RecordingQueue()
    app.dependency_overrides[get_processing_queue] = lambda: queue
    client = TestClient(app)
    try:
        tender_id = create_tender(client, "Text extraction tender")
        document_id = upload_fixture(client, tender_id, "sample_text.pdf")
        assert queue.document_ids == [UUID(document_id)]
        assert client.get(f"/api/v1/documents/{document_id}/status").json()["status"] == "queued"

        validate_document.run(document_id)
        extract_text.run(document_id)
        evaluate_quality.run(document_id)
        finalize_document.run(document_id)

        status_response = client.get(f"/api/v1/documents/{document_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "ready_for_ai"

        pages = client.get(f"/api/v1/documents/{document_id}/pages")
        assert pages.status_code == 200
        assert pages.json()["total"] == 2
        assert all(item["character_count"] > 0 for item in pages.json()["items"])

        quality = client.get(f"/api/v1/documents/{document_id}/quality")
        assert quality.status_code == 200
        assert quality.json()["decision"] == "ready_for_ai"
        assert quality.json()["characters_extracted"] > 200

        extraction = client.get(f"/api/v1/documents/{document_id}/extraction")
        assert extraction.status_code == 200
        assert extraction.json()["extraction_type"] == "text"
        assert extraction.json()["extractor_name"] == "pymupdf"
        assert extraction.json()["pages_processed"] == 2

        extract_text.run(document_id)
        with SessionLocal() as session:
            run_count = session.scalar(
                select(func.count()).select_from(ExtractionRunModel).where(
                    ExtractionRunModel.document_id == UUID(document_id)
                )
            )
            events = set(session.scalars(select(AuditEventModel.event_type)))
        assert run_count == 1
        assert {
            "DocumentQueued",
            "DocumentProcessingStarted",
            "TextExtractionCompleted",
            "QualityEvaluationCompleted",
            "DocumentReadyForAI",
        }.issubset(events)
    finally:
        app.dependency_overrides.clear()


def test_failed_document_can_retry_pipeline_without_duplicate_evidence() -> None:
    queue = RecordingQueue()
    app.dependency_overrides[get_processing_queue] = lambda: queue
    client = TestClient(app)
    try:
        tender_id = create_tender(client, "Retry document tender")
        document_id = upload_fixture(client, tender_id, "sample_text.pdf")
        parsed_id = UUID(document_id)

        with SessionLocal.begin() as session:
            session.execute(
                update(TenderDocumentModel)
                .where(TenderDocumentModel.id == parsed_id)
                .values(processing_status="failed", last_processing_error="transient failure")
            )

        start_pipeline.run(document_id)
        status_value = client.get(f"/api/v1/documents/{document_id}/status").json()["status"]
        assert status_value == "ready_for_ai"

        with SessionLocal() as session:
            run_count = session.scalar(
                select(func.count()).select_from(ExtractionRunModel).where(
                    ExtractionRunModel.document_id == parsed_id
                )
            )
            page_count = session.scalar(
                select(func.count()).select_from(DocumentPageModel).where(
                    DocumentPageModel.document_id == parsed_id
                )
            )
        assert run_count == 1
        assert page_count == 2
    finally:
        app.dependency_overrides.clear()


def test_real_celery_worker_processes_blank_pdf_and_marks_needs_ocr() -> None:
    settings = get_settings()
    if settings.celery_broker_url.get_secret_value().startswith("memory"):
        return
    Redis.from_url(settings.celery_broker_url.get_secret_value()).flushdb()
    Redis.from_url(settings.celery_result_backend.get_secret_value()).flushdb()
    client = TestClient(app)

    with start_worker(
        celery_app,
        pool="solo",
        perform_ping_check=False,
        queues=["document-processing"],
    ):
        tender_id = create_tender(client, "Celery blank PDF tender")
        document_id = upload_fixture(client, tender_id, "blank.pdf")
        deadline = time.monotonic() + 30
        status_value = "queued"
        while time.monotonic() < deadline:
            status_value = client.get(
                f"/api/v1/documents/{document_id}/status"
            ).json()["status"]
            if status_value in {"needs_ocr", "ready_for_ai", "failed"}:
                break
            time.sleep(0.25)

    assert status_value == "needs_ocr"
    quality = client.get(f"/api/v1/documents/{document_id}/quality").json()
    assert quality["empty_page_percentage"] == 100.0
    assert quality["decision"] == "needs_ocr"
    with SessionLocal() as session:
        model = session.get(TenderDocumentModel, UUID(document_id))
        assert model is not None
        assert model.requires_ocr is True
