"""Redis result-cache decorator around the executor (Schema §7).

Identical validated SQL doesn't need to hit the database twice within the TTL.
Only successful results are cached; errors are never cached so a transient
failure can't be pinned. Decorator pattern: same ``QueryExecutor`` port, one
added concern, executor untouched.
"""

from __future__ import annotations

import hashlib
import json

from app.domain.entities import ExecutionResult
from app.domain.ports.cache import Cache
from app.domain.ports.sql import QueryExecutor
from app.domain.results import ExecutionError, Ok, Result


class CachingQueryExecutor:
    def __init__(self, inner: QueryExecutor, cache: Cache, *, ttl_s: int = 900) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_s

    async def execute(self, sql: str) -> Result[ExecutionResult, ExecutionError]:
        key = _key(sql)
        cached = await self._cache.get(key)
        if cached is not None:
            return Ok(_decode(cached))
        result = await self._inner.execute(sql)
        if isinstance(result, Ok):
            await self._cache.set(key, _encode(result.value), self._ttl)
        return result


def _key(sql: str) -> str:
    return f"cache:sql:{hashlib.sha256(sql.encode('utf-8')).hexdigest()}"


def _encode(result: ExecutionResult) -> bytes:
    return json.dumps(
        {
            "columns": list(result.columns),
            "rows": [list(row) for row in result.rows],
            "row_count": result.row_count,
            "elapsed_ms": result.elapsed_ms,
            "truncated": result.truncated,
        },
        default=str,
    ).encode("utf-8")


def _decode(raw: bytes) -> ExecutionResult:
    data = json.loads(raw)
    return ExecutionResult(
        columns=tuple(data["columns"]),
        rows=tuple(tuple(row) for row in data["rows"]),
        row_count=data["row_count"],
        elapsed_ms=data["elapsed_ms"],
        truncated=data["truncated"],
    )
