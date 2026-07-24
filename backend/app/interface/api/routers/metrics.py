"""Metrics endpoints: Prometheus text for scrapers, JSON for the dashboard.

Kept minimal (counters + a few gauges) — MLflow holds the deep traces. Breaker
state is read from the shared cache at scrape time so the dashboard shows live
provider health.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from app.domain.value_objects import Provider

router = APIRouter(tags=["ops"])


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    metrics = getattr(request.app.state, "metrics", None)
    body = metrics.render() if metrics is not None else ""
    return Response(content=body, media_type="text/plain; version=0.0.4")


@router.get("/api/v1/metrics")
async def metrics_snapshot(request: Request) -> dict[str, object]:
    metrics = getattr(request.app.state, "metrics", None)
    snapshot = metrics.snapshot() if metrics is not None else {"counters": {}, "gauges": {}}
    return {
        **snapshot,
        "cache_hit_rate": metrics.cache_hit_rate() if metrics is not None else 0.0,
        "breakers": await _breaker_states(request),
    }


async def _breaker_states(request: Request) -> dict[str, str]:
    cache = getattr(request.app.state, "cache", None)
    if cache is None:
        return {}
    states: dict[str, str] = {}
    for provider in (Provider.GEMINI, Provider.GROQ):
        raw = await cache.get(f"breaker:{provider.value}")
        if raw is not None:
            try:
                states[provider.value] = str(json.loads(raw).get("state", "closed"))
            except (ValueError, TypeError):
                states[provider.value] = "unknown"
        else:
            states[provider.value] = "closed"
    return states
