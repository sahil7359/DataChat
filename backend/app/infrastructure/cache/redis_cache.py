"""Redis-backed Cache adapter (Upstash in prod).

Implements the ``Cache`` port. ``incr`` sets the TTL on first write so rate-limit
and quota counters expire without a second round-trip.
"""

from __future__ import annotations

import redis.asyncio as redis


class RedisCache:
    def __init__(self, client: redis.Redis[bytes]) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisCache:
        client: redis.Redis[bytes] = redis.from_url(url)
        return cls(client)

    async def get(self, key: str) -> bytes | None:
        value = await self._client.get(key)
        return value if value is None else bytes(value)

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        await self._client.set(key, value, ex=ttl_s)

    async def incr(self, key: str, ttl_s: int) -> int:
        count = int(await self._client.incr(key))
        if count == 1:
            await self._client.expire(key, ttl_s)
        return count
