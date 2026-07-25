from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.session import SessionLocal
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


def test_tender_endpoint_complete_flow() -> None:
    client = TestClient(app)
    create = client.post(
        "/api/v1/tenders",
        json={
            "title": "Transformers",
            "description": "CFE supply",
            "deadline": "2026-08-31T18:00:00-06:00",
            "created_by_user_id": SYSTEM_USER_ID,
        },
    )
    assert create.status_code == 201, create.text
    tender_id = create.json()["id"]
    UUID(tender_id)

    listed = client.get("/api/v1/tenders")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/v1/tenders/{tender_id}")
    assert fetched.status_code == 200

    update = client.put(
        f"/api/v1/tenders/{tender_id}",
        json={
            "title": "Transformers 2026",
            "description": None,
            "deadline": None,
            "status": "documents_pending",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["status"] == "documents_pending"

    archived = client.delete(f"/api/v1/tenders/{tender_id}")
    assert archived.status_code == 204
    assert client.get(f"/api/v1/tenders/{tender_id}").status_code == 404

    archived_update = client.put(
        f"/api/v1/tenders/{tender_id}",
        json={
            "title": "Cannot update",
            "description": None,
            "deadline": None,
            "status": "documents_pending",
        },
    )
    assert archived_update.status_code == 409
    assert archived_update.json()["code"] == "tender_already_archived"

    second_archive = client.delete(f"/api/v1/tenders/{tender_id}")
    assert second_archive.status_code == 409
    assert second_archive.json()["code"] == "tender_already_archived"

    with SessionLocal() as session:
        event_types = set(session.scalars(select(AuditEventModel.event_type)))
    assert event_types == {"TenderCreated", "TenderUpdated", "TenderArchived"}


def test_endpoint_validation_and_errors() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/tenders/not-a-uuid").status_code == 422

    blank = client.post(
        "/api/v1/tenders",
        json={"title": "   ", "created_by_user_id": SYSTEM_USER_ID},
    )
    assert blank.status_code == 422
    assert blank.json()["code"] == "validation_error"

    unknown_creator = client.post(
        "/api/v1/tenders",
        json={
            "title": "Valid",
            "created_by_user_id": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert unknown_creator.status_code == 422
    assert unknown_creator.json()["code"] == "tender_creator_not_found"


def test_endpoint_maps_domain_business_errors() -> None:
    client = TestClient(app)
    past_deadline = client.post(
        "/api/v1/tenders",
        json={
            "title": "Expired",
            "deadline": "2020-01-01T00:00:00Z",
            "created_by_user_id": SYSTEM_USER_ID,
        },
    )
    assert past_deadline.status_code == 422
    assert past_deadline.json()["code"] == "invalid_deadline"

    created = client.post(
        "/api/v1/tenders",
        json={"title": "Transition", "created_by_user_id": SYSTEM_USER_ID},
    )
    tender_id = created.json()["id"]
    invalid_transition = client.put(
        f"/api/v1/tenders/{tender_id}",
        json={
            "title": "Transition",
            "description": None,
            "deadline": None,
            "status": "closed",
        },
    )
    assert invalid_transition.status_code == 409
    assert invalid_transition.json()["code"] == "invalid_tender_state"

    naive_deadline = client.post(
        "/api/v1/tenders",
        json={
            "title": "Naive",
            "deadline": "2026-08-31T18:00:00",
            "created_by_user_id": SYSTEM_USER_ID,
        },
    )
    assert naive_deadline.status_code == 422
