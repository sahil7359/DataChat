"""Cache port (Redis-backed in production, in-memory fake in tests)."""

from __future__ import annotations

from typing import Protocol


class Cache(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, ttl_s: int) -> None: ...

    async def incr(self, key: str, ttl_s: int) -> int:
        """Atomically increment a counter, setting its TTL on first write.

        Used for rate-limit and quota counters (LLM10 bounded consumption).
        """
        ...
