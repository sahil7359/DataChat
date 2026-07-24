from fastapi.testclient import TestClient

from app.infrastructure.observability.metrics import Metrics
from tests.fakes.api import build_test_app


def test_counters_and_labels() -> None:
    m = Metrics()
    m.inc("http_requests_total", method="GET", status="200")
    m.inc("http_requests_total", method="GET", status="200")
    m.inc("http_requests_total", method="POST", status="429")

    snap = m.snapshot()
    assert snap["counters"]['http_requests_total{method="GET",status="200"}'] == 2
    assert snap["counters"]['http_requests_total{method="POST",status="429"}'] == 1


def test_cache_hit_rate() -> None:
    m = Metrics()
    assert m.cache_hit_rate() == 0.0
    m.inc("cache_hits_total")
    m.inc("cache_hits_total")
    m.inc("cache_misses_total")
    assert m.cache_hit_rate() == 2 / 3


def test_render_is_prometheus_text() -> None:
    m = Metrics()
    m.set_gauge("breaker_open", 1, provider="gemini")
    text = m.render()
    assert 'breaker_open{provider="gemini"} 1' in text


def test_metrics_endpoint_counts_requests() -> None:
    with TestClient(build_test_app()) as client:
        client.get("/health")
        prom = client.get("/metrics")
        snap = client.get("/api/v1/metrics")

    assert prom.status_code == 200
    assert "http_requests_total" in prom.text
    body = snap.json()
    assert "counters" in body
    assert body["breakers"] == {"gemini": "closed", "groq": "closed"}
