from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.integration.test_supplier_discovery_pipeline import (
    SYSTEM_USER_ID,
    FakeSupplierSearchService,
    RecordingSupplierQueue,
    configure_dependencies,
    create_approved_catalog,
)

from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.services.supplier_normalization import SupplierCandidateNormalizer
from app.application.services.supplier_query_builder import SupplierQueryBuilder
from app.application.use_cases.supplier_discovery_v2 import ProcessSupplierDiscoveryRunV2
from app.infrastructure.db.models.supplier import SupplierSourceModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.search.inline_contact_discovery import InlineContactDiscoveryService
from app.main import app


def _process(run_id: UUID, search_service: FakeSupplierSearchService) -> None:
    ProcessSupplierDiscoveryRunV2(
        SqlAlchemyUnitOfWork,
        search_service,
        SupplierQueryBuilder(),
        SupplierCandidateNormalizer(),
        SupplierDeduplicationService(),
        InlineContactDiscoveryService(),
        SupplierMatchingService(),
    ).execute(run_id)


def test_iteration10_supplier_flow_is_traceable_refreshable_and_review_gated() -> None:
    queue = RecordingSupplierQueue()
    search_service = FakeSupplierSearchService()
    configure_dependencies(queue, search_service)
    client = TestClient(app)
    try:
        tender_id = create_approved_catalog(client)
        catalog = client.get(f"/api/v1/tenders/{tender_id}/catalog").json()
        product_id = catalog["products"][0]["id"]

        requested = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/discover",
            json={
                "requested_by_user_id": SYSTEM_USER_ID,
                "correlation_id": "iteration-10-contract",
            },
        )
        assert requested.status_code == 202, requested.text
        first_body = requested.json()
        assert first_body["queued"] is True
        assert first_body["run"]["correlation_id"] == "iteration-10-contract"
        assert first_body["run"]["query_version"] == "1.0.0"
        first_run = queue.run_ids[-1]
        _process(first_run, search_service)

        candidates = client.get(f"/api/v1/tenders/{tender_id}/supplier-candidates")
        assert candidates.status_code == 200, candidates.text
        candidate_rows = candidates.json()["candidates"]
        assert len(candidate_rows) == 3
        assert {row["duplicate_status"] for row in candidate_rows} <= {
            "duplicate",
            "possible_duplicate",
            "unique",
        }
        assert all(row["query"] for row in candidate_rows)
        assert all(row["search_provider"] == "test-directory" for row in candidate_rows)
        assert all(row["normalized"] for row in candidate_rows)
        assert all(row["match_reasons"] for row in candidate_rows)

        repeated = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/discover",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert repeated.status_code == 202
        assert repeated.json()["queued"] is False
        assert repeated.json()["reused"] is True
        assert queue.run_ids == [first_run]

        refreshed = client.post(
            f"/api/v1/tenders/{tender_id}/suppliers/discover",
            json={
                "requested_by_user_id": SYSTEM_USER_ID,
                "refresh": True,
                "correlation_id": "iteration-10-refresh",
            },
        )
        assert refreshed.status_code == 202, refreshed.text
        assert refreshed.json()["queued"] is True
        assert refreshed.json()["run"]["refresh_sequence"] == 2
        assert refreshed.json()["run"]["refresh_of_run_id"] == str(first_run)
        second_run = queue.run_ids[-1]
        assert second_run != first_run
        _process(second_run, search_service)

        historical = client.get(
            f"/api/v1/tenders/{tender_id}/supplier-candidates"
        ).json()["candidates"]
        assert {row["run_id"] for row in historical} == {str(first_run), str(second_run)}
        with SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(SupplierSourceModel)) == 6
            sources = list(session.scalars(select(SupplierSourceModel)))
        assert all(source.discovery_run_id is not None for source in sources)
        assert all(source.product_id is not None for source in sources)
        assert all(source.query for source in sources)

        suppliers = client.get(f"/api/v1/tenders/{tender_id}/suppliers").json()["suppliers"]
        conductor = next(
            item for item in suppliers if item["normalized_domain"] == "conductores.example.mx"
        )
        other = next(item for item in suppliers if item["id"] != conductor["id"])

        blocked = client.post(
            f"/api/v1/products/{product_id}/suppliers/{conductor['id']}/match",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert blocked.status_code == 409

        approved = client.post(
            f"/api/v1/suppliers/{conductor['id']}/approve",
            json={"reviewer_user_id": SYSTEM_USER_ID},
        )
        assert approved.status_code == 200
        matched = client.post(
            f"/api/v1/products/{product_id}/suppliers/{conductor['id']}/match",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert matched.status_code == 200, matched.text
        confirmed = next(
            row
            for row in matched.json()["suppliers"]
            if row["tender_supplier_id"] == conductor["id"]
        )
        assert confirmed["match_status"] == "confirmed"
        assert confirmed["match_score"] > 0
        assert confirmed["reason"]

        rejected = client.post(
            f"/api/v1/suppliers/{other['id']}/reject",
            json={
                "reviewer_user_id": SYSTEM_USER_ID,
                "reason": "No cumple criterios de compra",
            },
        )
        assert rejected.status_code == 200
        rejected_match = client.post(
            f"/api/v1/products/{product_id}/suppliers/{other['id']}/match",
            json={"requested_by_user_id": SYSTEM_USER_ID},
        )
        assert rejected_match.status_code == 409
    finally:
        app.dependency_overrides.clear()
