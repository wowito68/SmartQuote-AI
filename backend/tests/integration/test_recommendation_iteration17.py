from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.domain.tenders.value_objects import TenderStatus
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.recommendation import RecommendationModel
from app.infrastructure.db.models.tender import TenderModel
from app.infrastructure.db.session import SessionLocal
from app.main import app
from tests.integration.test_comparison_iteration14 import SYSTEM_USER_ID, _approved_quote


def test_recommendation_scenario_is_idempotent_auditable_and_never_awards(tmp_path: Path) -> None:
    client = TestClient(app)
    try:
        tender_id, _ = _approved_quote(client, tmp_path)
        comparison = client.post(
            f"/api/v1/tenders/{tender_id}/comparisons",
            json={"created_by_user_id": SYSTEM_USER_ID},
        )
        assert comparison.status_code == 201, comparison.text
        comparison_id = comparison.json()["id"]

        scenario = {
            "generated_by_user_id": SYSTEM_USER_ID,
            "technical_weight": "0.4",
            "price_weight": "0.4",
            "delivery_weight": "0.2",
        }
        created = client.post(
            f"/api/v1/comparisons/{comparison_id}/recommendations",
            json=scenario,
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["status"] == "withheld"
        assert payload["recommended_supplier_id"] is None
        assert payload["human_review_required"] is True
        assert payload["policy_version"] == "1.0.0"
        assert payload["candidates"]
        assert any(
            any(reason.startswith("missing_offer:") for reason in candidate["exclusion_reasons"])
            for candidate in payload["candidates"]
        )

        repeated = client.post(
            f"/api/v1/comparisons/{comparison_id}/recommendations",
            json=scenario,
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == payload["id"]
        assert repeated.json()["recommendation_key"] == payload["recommendation_key"]

        alternative = client.post(
            f"/api/v1/comparisons/{comparison_id}/recommendations",
            json={
                **scenario,
                "technical_weight": "1",
                "price_weight": "0",
                "delivery_weight": "0",
            },
        )
        assert alternative.status_code == 201, alternative.text
        assert alternative.json()["id"] != payload["id"]
        assert alternative.json()["recommendation_key"] != payload["recommendation_key"]

        latest = client.get(f"/api/v1/comparisons/{comparison_id}/recommendations")
        by_id = client.get(f"/api/v1/recommendations/{payload['id']}")
        assert latest.status_code == 200
        assert by_id.status_code == 200
        assert latest.json()["id"] == alternative.json()["id"]
        assert by_id.json()["id"] == payload["id"]

        invalid_weights = client.post(
            f"/api/v1/comparisons/{comparison_id}/recommendations",
            json={
                **scenario,
                "technical_weight": "0.5",
                "price_weight": "0.5",
                "delivery_weight": "0.5",
            },
        )
        assert invalid_weights.status_code == 422
        assert invalid_weights.json()["code"] == "validation_error"

        with SessionLocal() as session:
            tender = session.get(TenderModel, UUID(tender_id))
            assert tender is not None
            assert tender.status == TenderStatus.COMPARISON_READY.value
            assert session.scalar(select(func.count()).select_from(RecommendationModel)) == 2
            events = set(
                session.scalars(
                    select(AuditEventModel.event_type).where(
                        AuditEventModel.aggregate_type == "recommendation"
                    )
                )
            )
        assert "recommendation.created" in events
        assert "recommendation.withheld" in events
    finally:
        app.dependency_overrides.clear()
