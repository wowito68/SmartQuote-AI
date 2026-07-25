from app.main import create_app
from fastapi.testclient import TestClient


def test_health_check_returns_application_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "project_name": "SmartQuote AI",
        "version": "0.1.0",
        "environment": "local",
    }

