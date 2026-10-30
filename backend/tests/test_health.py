from app.main import app
from fastapi.testclient import TestClient


def test_health_check_reports_service_status() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "KiboLens"


def test_readiness_is_honest_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.health.database_is_available", lambda: False)
    client = TestClient(app)
    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
