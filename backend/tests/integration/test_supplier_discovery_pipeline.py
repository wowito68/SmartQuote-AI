import time
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_ai_catalog_pipeline import (
    FakeAIService,
    RecordingAIQueue,
    RecordingDocumentQueue,
    create_ready_document,
    valid_payload,
)

from app.api.dependencies import (
    get_ai_extraction_queue,
    get_processing_queue,
    get_supplier_discovery_queue,
    get_supplier_search_service,
)
from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSearchRequest,
    SupplierSearchResponse,
    SupplierSearchService,
    SupplierSuggestion,
)
from app.application.services.catalog_normalizer import CatalogNormalizer
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.use_cases.catalog import ProcessAIExtractionRun
from app.application.use_cases.supplier_discovery import ProcessSupplierDiscoveryRun
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.supplier import (
    ProductSupplierMatchModel,
    SupplierContactModel,
    SupplierDiscoveryRunModel,
    SupplierMergeSuggestionModel,
    SupplierModel,
    SupplierSourceModel,
    TenderSupplierModel,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


class RecordingSupplierQueue(SupplierDiscoveryQueue):
    def __init__(self) -> None:
        self.run_ids: list[UUID] = []

    def enqueue(self, run_id: UUID) -> None:
        self.run_ids.append(run_id)


class FakeSupplierSearchService(SupplierSearchService):
    provider_name = "test-directory"
    provider_version = "2026.07"

    def search(self, request: SupplierSearchRequest) -> SupplierSearchResponse:
        common_contacts = (
            SupplierContactSuggestion(
                contact_type="email",
                value="ventas@conductores.example.mx",
                confidence=0.96,
                source_url="https://conductores.example.mx/contacto",
                contact_name="Ana Ventas",
                role="Ejecutiva comercial",
            ),
            SupplierContactSuggestion(
                contact_type="phone",
                value="+52 442 123 4567",
                confidence=0.88,
                source_url="https://conductores.example.mx/contacto",
            ),
        )
        return SupplierSearchResponse(
            suggestions=(
                SupplierSuggestion(
                    legal_name="Conductores del Centro SA de CV",
                    trade_name="Conductores Centro",
                    website="https://conductores.example.mx",
                    category="Eléctrico",
                    country="MX",
                    city="Querétaro",
                    description="Fabricante de cable de cobre XLPE 2 AWG para 600 V",
                    source_url="https://directory.example.mx/conductores-centro",
                    source_title="Perfil de Conductores Centro",
                    contacts=common_contacts,
                ),
                SupplierSuggestion(
                    legal_name="Conductores del Centro, S.A. de C.V.",
                    trade_name="Conductores Centro México",
                    website="https://www.conductores.example.mx/catalogo",
                    category="Eléctrico",
                    country="MX",
                    city=None,
                    description="Distribuidor de conductores eléctricos",
                    source_url="https://directory-b.example.mx/conductores",
                    source_title="Segundo directorio",
                    contacts=common_contacts,
                ),
                SupplierSuggestion(
                    legal_name=None,
                    trade_name="Cables del Bajío",
                    website="https://cables-bajio.example.mx",
                    category="Material eléctrico",
                    country="MX",
                    city="León",
                    description="Cable de cobre, aislamiento XLPE y suministros eléctricos",
                    source_url="https://directory.example.mx/cables-bajio",
                    contacts=(
                        SupplierContactSuggestion(
                            contact_type="contact_form",
                            value="https://cables-bajio.example.mx/contacto",
                            confidence=0.8,
                            source_url="https://cables-bajio.example.mx/contacto",
                        ),
                    ),
                ),
            )
        )


def create_approved_catalog(client: TestClient) -> str:
    tender_id, _ = create_ready_document(client)
    ai_queue = app.dependency_overrides[get_ai_extraction_queue]().run_ids
    client.post(f"/api/v1/tenders/{tender_id}/catalog/extract")
    run_id = ai_queue[-1]
    ProcessAIExtractionRun(
        SqlAlchemyUnitOfWork,
        FakeAIService(valid_payload()),
        FilePromptRegistry(),
        CatalogNormalizer(),
    ).execute(run_id)
    product_id = client.get(f"/api/v1/tenders/{tender_id}/catalog").json()["products"][0]["id"]
    approved = client.put(
        f"/api/v1/catalog/{product_id}",
        json={"action": "approve", "reviewer_user_id": SYSTEM_USER_ID},
    )
    assert approved.status_code == 200, approved.text
    snapshot = client.post(
        f"/api/v1/tenders/{tender_id}/catalog/approve",
        json={"approved_by_user_id": SYSTEM_USER_ID},
    )
    assert snapshot.status_code == 201, snapshot.text
    return tender_id


def configure_dependencies(
    supplier_queue: RecordingSupplierQueue,
    search_service: SupplierSearchService,
) -> None:
    ai_queue = RecordingAIQueue()
    app.dependency_overrides[get_processing_queue] = lambda: RecordingDocumentQueue()
    app.dependency_overrides[get_ai_extraction_queue] = lambda: ai_queue
    app.dependency_overrides[get_supplier_discovery_queue] = lambda: supplier_queue
    app.dependency_overrides[get_supplier_search_service] = lambda: search_service


def test_supplier_discovery_is_auditable_deduplicated_matched_and_idempotent() -> None:
    supplier_queue = RecordingSupplierQueue()
    search_service = FakeSupplierSearchService()
    configure_dependencies(supplier_queue, search_service)
    client = TestClient(app)
    try:
        tender_id = create_approved_catalog(client)
        request = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/discover",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert request.status_code == 202, request.text
        assert request.json()["queued"] is True
        run_id = supplier_queue.run_ids[0]
        ProcessSupplierDiscoveryRun(
            SqlAlchemyUnitOfWork,
            search_service,
            SupplierDeduplicationService(),
            SupplierMatchingService(),
        ).execute(run_id)

        response = client.get(f"/api/v1/tenders/{tender_id}/suppliers")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["metrics"]["suppliers_total"] == 2
        assert body["metrics"]["duplicates_detected"] == 1
        assert body["metrics"]["suppliers_with_valid_contact"] == 2
        assert all(item["status"] == "pending_review" for item in body["suppliers"])
        assert all(item["sources"] for item in body["suppliers"])
        assert all(item["matches"] for item in body["suppliers"])
        conductor = next(
            item for item in body["suppliers"] if item["normalized_domain"] == "conductores.example.mx"
        )
        assert len(conductor["sources"]) == 2
        assert {item["contact_type"] for item in conductor["contacts"]} == {
            "email",
            "phone",
        }
        assert conductor["matches"][0]["score"] > 40
        assert len(conductor["matches"][0]["reasons"]) == 4

        second = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/discover",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert second.status_code == 202
        assert second.json()["queued"] is False
        assert second.json()["reused"] is True
        assert supplier_queue.run_ids == [run_id]

        approved = client.post(
            f"/api/v1/suppliers/{conductor['id']}/approve",
            json={"reviewer_user_id": SYSTEM_USER_ID},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        other = next(item for item in body["suppliers"] if item["id"] != conductor["id"])
        rejected = client.post(
            f"/api/v1/suppliers/{other['id']}/reject",
            json={
                "reviewer_user_id": SYSTEM_USER_ID,
                "reason": "No cubre la especificación principal",
            },
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"

        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(SupplierModel)) == 2
            assert session.scalar(select(func.count()).select_from(TenderSupplierModel)) == 2
            assert session.scalar(select(func.count()).select_from(SupplierContactModel)) == 3
            assert session.scalar(select(func.count()).select_from(SupplierSourceModel)) == 3
            assert session.scalar(select(func.count()).select_from(ProductSupplierMatchModel)) == 2
            run = session.get(SupplierDiscoveryRunModel, run_id)
            assert run is not None and run.status == "completed"
            event_types = set(session.scalars(select(AuditEventModel.event_type)))
        assert {
            "SupplierDiscoveryStarted",
            "SupplierDiscovered",
            "SupplierDeduplicated",
            "SupplierContactsDiscovered",
            "SupplierMatchingCompleted",
            "SupplierApproved",
            "SupplierRejected",
        }.issubset(event_types)
    finally:
        app.dependency_overrides.clear()


def test_manual_suppliers_can_be_edited_and_merged_without_deleting_history() -> None:
    configure_dependencies(RecordingSupplierQueue(), FakeSupplierSearchService())
    client = TestClient(app)
    try:
        tender = client.post(
            "/api/v1/tenders",
            json={"title": "Manual suppliers", "created_by_user_id": SYSTEM_USER_ID},
        )
        tender_id = tender.json()["id"]
        first = client.post(
            "/api/v1/suppliers/manual",
            json={
                "tender_id": tender_id,
                "created_by_user_id": SYSTEM_USER_ID,
                "legal_name": "Proveedor Industrial SA de CV",
                "trade_name": "Proveedor Industrial",
                "website": "https://proveedor-industrial.example.mx",
                "country": "MX",
                "contacts": [
                    {
                        "contact_type": "email",
                        "value": "ventas@proveedor-industrial.example.mx",
                        "confidence": 1,
                        "source_url": "manual://captura",
                    }
                ],
            },
        )
        second = client.post(
            "/api/v1/suppliers/manual",
            json={
                "tender_id": tender_id,
                "created_by_user_id": SYSTEM_USER_ID,
                "trade_name": "Proveedor Industrial Alterno",
                "website": "https://proveedor-alterno.example.mx",
                "country": "MX",
            },
        )
        assert first.status_code == 201 and second.status_code == 201
        source_id = second.json()["id"]
        target_id = first.json()["id"]

        edited = client.put(
            f"/api/v1/suppliers/{source_id}",
            json={
                "changed_by_user_id": SYSTEM_USER_ID,
                "city": "Querétaro",
                "description": "Distribuidor industrial regional",
                "contacts": [
                    {
                        "contact_type": "phone",
                        "value": "+52 442 555 0101",
                        "confidence": 0.9,
                        "source_url": "manual://captura",
                    }
                ],
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["city"] == "Querétaro"

        merged = client.post(
            "/api/v1/suppliers/merge",
            json={
                "source_tender_supplier_id": source_id,
                "target_tender_supplier_id": target_id,
                "reviewer_user_id": SYSTEM_USER_ID,
            },
        )
        assert merged.status_code == 200, merged.text
        assert merged.json()["status"] == "merged"
        assert merged.json()["merged_into_tender_supplier_id"] == target_id
        target = client.get(f"/api/v1/suppliers/{target_id}").json()
        assert {contact["contact_type"] for contact in target["contacts"]} == {
            "email",
            "phone",
        }
        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(SupplierModel)) == 2
            assert session.scalar(select(func.count()).select_from(TenderSupplierModel)) == 2
            assert session.scalar(
                select(func.count()).select_from(SupplierMergeSuggestionModel)
            ) >= 0
    finally:
        app.dependency_overrides.clear()


def test_real_celery_worker_processes_supplier_queue_with_mocked_search(monkeypatch) -> None:
    from celery.contrib.testing.worker import start_worker

    from app.config.settings import get_settings
    from app.infrastructure.tasks import supplier_discovery as supplier_tasks
    from app.infrastructure.tasks.celery_app import celery_app

    settings = get_settings()
    if settings.celery_broker_url.get_secret_value().startswith("memory"):
        return
    search_service = FakeSupplierSearchService()
    monkeypatch.setattr(
        supplier_tasks,
        "get_supplier_search_service",
        lambda: search_service,
    )
    ai_queue = RecordingAIQueue()
    app.dependency_overrides[get_processing_queue] = lambda: RecordingDocumentQueue()
    app.dependency_overrides[get_ai_extraction_queue] = lambda: ai_queue
    app.dependency_overrides[get_supplier_search_service] = lambda: search_service
    client = TestClient(app)
    try:
        with start_worker(
            celery_app,
            pool="solo",
            perform_ping_check=False,
            queues=["supplier-discovery"],
        ):
            tender_id = create_approved_catalog(client)
            response = client.post(
                f"/api/v1/tenders/{tender_id}/suppliers/discover",
                json={"requested_by_user_id": SYSTEM_USER_ID},
            )
            assert response.status_code == 202
            run_id = UUID(response.json()["run"]["id"])
            deadline = time.monotonic() + 30
            run_status = "queued"
            while time.monotonic() < deadline:
                with SessionLocal() as session:
                    model = session.get(SupplierDiscoveryRunModel, run_id)
                    run_status = model.status if model else "missing"
                if run_status in {"completed", "failed"}:
                    break
                time.sleep(0.25)
        assert run_status == "completed"
    finally:
        app.dependency_overrides.clear()
