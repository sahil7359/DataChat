"""In-memory Cache fake. TTLs are tracked but not expired (tests are short)."""

from __future__ import annotations


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        self._store[key] = value
        self.ttls[key] = ttl_s

    async def incr(self, key: str, ttl_s: int) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        self.ttls.setdefault(key, ttl_s)
        return self._counters[key]
