"""Per-client rate limiting + a global daily quota (LLM10 bounded consumption).

Both are Redis counters via the Cache port. The per-IP fixed window protects a
single abuser; the global daily quota protects the free LLM tiers as a whole. On
breach we return 429 with ``Retry-After`` — a graceful limit, not a crash.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request, status

from app.domain.ports.cache import Cache


class RateLimiter:
    def __init__(self, cache: Cache, *, per_minute: int, daily_quota: int) -> None:
        self._cache = cache
        self._per_minute = per_minute
        self._daily_quota = daily_quota

    async def __call__(self, request: Request) -> None:
        await self._check_ip(request)
        await self._check_global_quota()

    async def _check_ip(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        window = int(datetime.now(UTC).timestamp() // 60)
        count = await self._cache.incr(f"rl:ip:{client}:{window}", 60)
        if count > self._per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
                headers={"Retry-After": "60"},
            )

    async def _check_global_quota(self) -> None:
        day = datetime.now(UTC).strftime("%Y%m%d")
        count = await self._cache.incr(f"quota:global:{day}", 86400)
        if count > self._daily_quota:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="daily quota exceeded",
                headers={"Retry-After": "3600"},
            )
