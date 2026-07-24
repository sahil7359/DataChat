"""Evaluation harness (FR-20).

Scores the agent on a golden NL->SQL set with three scorers:
- ``execution_accuracy`` — result-set equality between the agent's query and the
  gold query (BIRD-style; compares *values*, not SQL strings, so two different
  correct queries both count as correct).
- ``sql_valid`` — the predicted SQL parses and passes the guardrail.
- ``explanation_faithfulness`` — an LLM judge rates whether the prose is grounded
  in the returned rows.

All dependencies are injected, so the harness is unit-testable with fakes and the
golden set runs against the real seed DB in CI (`pytest -m eval`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.application.services.query_service import QueryService
from app.domain.entities import ExecutionResult, LLMMessage, LLMRequest, MessageRole
from app.domain.ports.llm import LLMProvider
from app.domain.ports.sql import QueryExecutor, SqlValidator
from app.domain.results import Ok
from app.domain.value_objects import TaskKind

FAITHFULNESS_VERSION = "faithfulness_judge@v1"


@dataclass(frozen=True, slots=True)
class EvalCase:
    question: str
    gold_sql: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CaseResult:
    question: str
    predicted_sql: str | None
    execution_match: bool
    sql_valid: bool
    faithfulness: float
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EvalReport:
    execution_accuracy: float
    sql_valid_rate: float
    faithfulness: float
    guardrail_pass_rate: float
    results: tuple[CaseResult, ...] = field(default_factory=tuple)

    def regressed(self, baseline: float) -> bool:
        return self.execution_accuracy < baseline


def compare_result_sets(a: ExecutionResult | None, b: ExecutionResult | None) -> bool:
    """Order-insensitive, name-insensitive value comparison (BIRD-style)."""
    if a is None or b is None:
        return False
    return _normalise(a) == _normalise(b)


def _normalise(result: ExecutionResult) -> list[tuple[str, ...]]:
    rows = [tuple(_cell(c) for c in row) for row in result.rows]
    return sorted(rows)


def _cell(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


class FaithfulnessJudge:
    """LLM-as-judge: does the explanation stay grounded in the rows (LLM09)?"""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def score(
        self, question: str, execution: ExecutionResult | None, explanation: str
    ) -> float:
        if not explanation:
            return 0.0
        rows = _render_rows(execution)
        messages = (
            LLMMessage(
                MessageRole.SYSTEM,
                "You are grading whether an explanation is faithful to the data rows. "
                "Reply with a single number between 0 and 1, where 1 means every claim "
                "is supported by the rows and 0 means it is not.",
            ),
            LLMMessage(
                MessageRole.USER, f"Question: {question}\nRows:\n{rows}\nExplanation: {explanation}"
            ),
        )
        response = await self._llm.complete(
            LLMRequest(messages=messages, task=TaskKind.VERIFY, prompt_version=FAITHFULNESS_VERSION)
        )
        return _parse_score(response.text)


class EvalService:
    def __init__(
        self,
        query_service: QueryService,
        gold_executor: QueryExecutor,
        validator: SqlValidator,
        judge: FaithfulnessJudge,
    ) -> None:
        self._query_service = query_service
        self._gold_executor = gold_executor
        self._validator = validator
        self._judge = judge

    async def evaluate(self, cases: list[EvalCase]) -> EvalReport:
        results: list[CaseResult] = []
        for case in cases:
            results.append(await self._score_case(case))
        return _aggregate(results)

    async def _score_case(self, case: EvalCase) -> CaseResult:
        state = await self._query_service.run(case.question)
        predicted_sql = state.get("candidate_sql")
        predicted_exec = state.get("execution")

        gold = await self._gold_executor.execute(case.gold_sql)
        gold_exec = gold.value if isinstance(gold, Ok) else None
        match = compare_result_sets(predicted_exec, gold_exec)
        valid = bool(predicted_sql) and self._validator.validate(predicted_sql or "").ok
        faithfulness = await self._judge.score(
            case.question, predicted_exec, state.get("explanation") or ""
        )
        return CaseResult(
            question=case.question,
            predicted_sql=predicted_sql,
            execution_match=match,
            sql_valid=valid,
            faithfulness=faithfulness,
            failure_reason=None if match else "result set did not match gold",
        )


def _aggregate(results: list[CaseResult]) -> EvalReport:
    n = len(results) or 1
    return EvalReport(
        execution_accuracy=sum(r.execution_match for r in results) / n,
        sql_valid_rate=sum(r.sql_valid for r in results) / n,
        faithfulness=sum(r.faithfulness for r in results) / n,
        guardrail_pass_rate=sum(r.sql_valid for r in results) / n,
        results=tuple(results),
    )


def _render_rows(execution: ExecutionResult | None) -> str:
    if execution is None:
        return "(no rows)"
    header = " | ".join(execution.columns)
    body = "\n".join(" | ".join(str(c) for c in row) for row in execution.rows[:20])
    return f"{header}\n{body}"


def _parse_score(text: str) -> float:
    import re

    match = re.search(r"[01](?:\.\d+)?", text)
    if not match:
        return 0.0
    return max(0.0, min(1.0, float(match.group())))
