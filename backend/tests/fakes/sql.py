"""Fakes for the SQL guardrail and executor ports."""

from __future__ import annotations

from app.domain.entities import ExecutionResult, RuleResult, ValidationResult
from app.domain.results import Err, ExecutionError, Ok, Result


class FakeSqlValidator:
    """Passes by default; can be told to reject to test the guardrail-fail path."""

    def __init__(self, *, ok: bool = True, reason: str = "blocked") -> None:
        self._ok = ok
        self._reason = reason
        self.validated: list[str] = []

    def validate(self, sql: str) -> ValidationResult:
        self.validated.append(sql)
        if self._ok:
            return ValidationResult(ok=True, sql=sql, results=(RuleResult("fake", True),))
        return ValidationResult(
            ok=False,
            sql=sql,
            results=(RuleResult("fake", False, self._reason),),
        )


class FakeQueryExecutor:
    """Returns a canned result set, or a canned execution error."""

    def __init__(
        self,
        *,
        result: ExecutionResult | None = None,
        error: ExecutionError | None = None,
    ) -> None:
        self._result = result or ExecutionResult(
            columns=("n",), rows=((1,),), row_count=1, elapsed_ms=1
        )
        self._error = error
        self.executed: list[str] = []

    async def execute(self, sql: str) -> Result[ExecutionResult, ExecutionError]:
        self.executed.append(sql)
        if self._error is not None:
            return Err(self._error)
        return Ok(self._result)
