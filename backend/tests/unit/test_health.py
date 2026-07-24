from fastapi.testclient import TestClient

from tests.fakes.api import build_test_app


def test_health_reports_ok() -> None:
    with TestClient(build_test_app()) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert resp.headers.get("X-Request-ID")


def test_ready_reports_checks() -> None:
    with TestClient(build_test_app()) as client:
        resp = client.get("/ready")

    assert resp.status_code == 200
    assert resp.json()["checks"]["redis"] is True
