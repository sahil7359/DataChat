"""Per-provider circuit breaker with state shared in Redis.

State lives in the cache (not process memory) so it survives the free-tier
scale-to-zero restarts and is coordinated if more than one instance ever runs.
The classic three states:

    CLOSED  --failures>=threshold-->  OPEN
    OPEN    --cooldown elapsed------>  HALF_OPEN   (allow one probe)
    HALF_OPEN --probe ok----------->  CLOSED
    HALF_OPEN --probe fails-------->  OPEN

This is what turns a flaky free API into a dependable one: once a provider starts
failing we stop hammering it (fail fast, fall over) and periodically re-check.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from enum import StrEnum
from typing import TypedDict, cast

from app.domain.ports.cache import Cache


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerRecord(TypedDict):
    state: str
    failures: int
    opened_at: float


class CircuitBreaker:
    def __init__(
        self,
        cache: Cache,
        *,
        fail_threshold: int,
        cooldown_s: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._cache = cache
        self._threshold = fail_threshold
        self._cooldown = cooldown_s
        self._clock = clock
        self._ttl = max(cooldown_s * 4, 300)

    async def allow(self, provider: str) -> bool:
        record = await self._load(provider)
        state = BreakerState(record["state"])
        if state is BreakerState.CLOSED:
            return True
        if state is BreakerState.HALF_OPEN:
            return True
        # OPEN: allow a single probe once the cooldown has elapsed.
        if self._clock() - record["opened_at"] >= self._cooldown:
            record["state"] = BreakerState.HALF_OPEN.value
            await self._save(provider, record)
            return True
        return False

    async def record_success(self, provider: str) -> None:
        await self._save(
            provider, {"state": BreakerState.CLOSED.value, "failures": 0, "opened_at": 0.0}
        )

    async def record_failure(self, provider: str) -> None:
        record = await self._load(provider)
        state = BreakerState(record["state"])
        failures = record["failures"] + 1
        if state is BreakerState.HALF_OPEN or failures >= self._threshold:
            await self._save(
                provider,
                {
                    "state": BreakerState.OPEN.value,
                    "failures": failures,
                    "opened_at": self._clock(),
                },
            )
        else:
            await self._save(
                provider,
                {"state": BreakerState.CLOSED.value, "failures": failures, "opened_at": 0.0},
            )

    async def state(self, provider: str) -> BreakerState:
        return BreakerState((await self._load(provider))["state"])

    async def _load(self, provider: str) -> BreakerRecord:
        raw = await self._cache.get(_key(provider))
        if raw is None:
            return BreakerRecord(state=BreakerState.CLOSED.value, failures=0, opened_at=0.0)
        return cast(BreakerRecord, json.loads(raw))

    async def _save(self, provider: str, record: BreakerRecord) -> None:
        await self._cache.set(_key(provider), json.dumps(record).encode("utf-8"), self._ttl)


def _key(provider: str) -> str:
    return f"breaker:{provider}"
