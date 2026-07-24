"""Liveness and readiness. ``/health`` never touches a dependency; ``/ready``
best-effort pings Redis (and the DB when a container is attached) so a keep-warm
cron can resume the scale-to-zero services (NFR-3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app import __version__
from app.domain.ports.cache import Cache
from app.interface.api.schemas import HealthResponse, ReadyResponse
from app.interface.deps import get_cache

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request, cache: Cache = Depends(get_cache)) -> ReadyResponse:
    checks: dict[str, bool] = {"redis": await _probe_cache(cache)}
    container = getattr(request.app.state, "container", None)
    if container is not None:
        checks["database"] = await _probe_db(container)
    status = "ready" if all(checks.values()) else "degraded"
    return ReadyResponse(status=status, checks=checks)


async def _probe_cache(cache: Cache) -> bool:
    try:
        await cache.get("ready:probe")
    except Exception:
        return False
    return True


async def _probe_db(container: object) -> bool:
    from sqlalchemy import text

    engine = getattr(container, "_app_engine", None)
    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
