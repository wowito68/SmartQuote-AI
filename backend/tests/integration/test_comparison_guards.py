from fastapi.testclient import TestClient

from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


def test_comparison_is_blocked_without_approved_catalog() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/tenders",
        json={
            "title": "Tender without approved catalog",
            "created_by_user_id": SYSTEM_USER_ID,
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/v1/tenders/{created.json()['id']}/comparison",
        json={"generated_by_user_id": SYSTEM_USER_ID},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "comparison_not_ready"
    assert "approved catalog" in response.json()["message"].lower()
