"""SQL guardrail and execution ports — the security spine.

``SqlValidator`` is deliberately **pure and synchronous**: no I/O, so it can be
reasoned about and fuzzed exhaustively. ``QueryExecutor`` returns a ``Result`` so
an execution failure (timeout, bad column) feeds the bounded repair loop instead
of blowing up the graph.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import ExecutionResult, ValidationResult
from app.domain.results import ExecutionError, Result


class SqlValidator(Protocol):
    def validate(self, sql: str) -> ValidationResult: ...


class QueryExecutor(Protocol):
    async def execute(self, sql: str) -> Result[ExecutionResult, ExecutionError]:
        """Execute already-validated SQL on the read-only role, with limits."""
        ...
