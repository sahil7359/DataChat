"""Read-only query executor.

Runs already-validated SQL on the executor engine (the ``datachat_exec`` role,
Bulkhead pattern). Results are streamed and capped at ``row_cap`` so a query can
never pull an unbounded set into memory, and a wall-clock timeout backs up the
role's own ``statement_timeout``. Failures come back as a ``Result`` so the agent
can feed the DB error into its bounded repair loop instead of crashing.
"""

from __future__ import annotations

import asyncio
import time

from asyncpg import PostgresError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.entities import ExecutionResult
from app.domain.results import Err, ExecutionError, Ok, Result

_TIMEOUT_SQLSTATE = "57014"  # query_canceled (statement_timeout)


class ReadOnlyQueryExecutor:
    def __init__(self, engine: AsyncEngine, *, row_cap: int, timeout_s: float) -> None:
        self._engine = engine
        self._row_cap = row_cap
        self._timeout = timeout_s

    async def execute(self, sql: str) -> Result[ExecutionResult, ExecutionError]:
        start = time.monotonic()
        try:
            async with self._engine.connect() as conn:
                async with asyncio.timeout(self._timeout):
                    result = await conn.stream(text(sql))
                    columns = tuple(result.keys())
                    rows: list[tuple[object, ...]] = []
                    async for row in result:
                        rows.append(tuple(row))
                        if len(rows) > self._row_cap:
                            break
        except TimeoutError:
            return Err(ExecutionError("query exceeded the time limit", code=_TIMEOUT_SQLSTATE))
        except DBAPIError as exc:
            return Err(_map_db_error(exc))
        except SQLAlchemyError:  # pragma: no cover - defensive
            return Err(ExecutionError("query failed", code="db_error"))
        except PostgresError as exc:
            # why: on the streaming path a driver error can surface while rows are
            # being buffered, *after* SQLAlchemy's wrapper has run, so it arrives
            # as a native asyncpg exception rather than a DBAPIError. The read-only
            # role rejecting a write is exactly that case — the last line of
            # defence raising instead of returning Err would turn a correctly
            # blocked write into an unhandled error.
            return Err(ExecutionError(str(exc), code=getattr(exc, "sqlstate", None) or "db_error"))

        elapsed_ms = int((time.monotonic() - start) * 1000)
        truncated = len(rows) > self._row_cap
        return Ok(
            ExecutionResult(
                columns=columns,
                rows=tuple(rows[: self._row_cap]),
                row_count=min(len(rows), self._row_cap),
                elapsed_ms=elapsed_ms,
                truncated=truncated,
            )
        )


def _map_db_error(exc: DBAPIError) -> ExecutionError:
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if sqlstate == _TIMEOUT_SQLSTATE:
        return ExecutionError("query exceeded the time limit", code=_TIMEOUT_SQLSTATE)
    # Keep the message safe/generic; the detailed error is for the repair prompt,
    # not the end user. The sqlstate is enough signal for the agent to react.
    return ExecutionError(_safe_message(exc), code=str(sqlstate or "db_error"))


def _safe_message(exc: DBAPIError) -> str:
    orig = getattr(exc, "orig", None)
    message = getattr(orig, "message", None) or str(orig) or "query failed"
    return message.splitlines()[0][:200]
