"""Evaluation harness (FR-20).

Scores the agent on a golden NL->SQL set. Two kinds of case, scored differently:

- **answerable** — the question has a correct answer in the governed data.
  Scored by ``execution_accuracy``: result-set equality between the agent's query
  and the gold query (BIRD-style; compares *values*, not SQL strings, so two
  different correct queries both count as correct).
- **refusal** — the question is out of scope (unknown country, indicator we do not
  carry, or too ambiguous to answer). There is no gold SQL, so result-set equality
  is meaningless. Scored by ``refusal_accuracy``: did the agent decline to invent
  an answer? An agent that confidently answers an unanswerable question is the
  failure mode that matters, and averaging it into execution_accuracy would hide it.

why: two metrics over two disjoint case sets, rather than one blended number.
alt: score refusals as execution_accuracy=0 (simpler, but then a perfect refusal
and a wrong answer are indistinguishable, which is exactly what we need to tell apart).

Also reported: ``sql_valid_rate`` (generated SQL parses and passes the AST
guardrail) and ``faithfulness`` (LLM judge: is the prose grounded in the rows).

All dependencies are injected, so the harness is unit-testable with fakes and the
golden set runs against the real seed DB.
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
    """One golden case. ``gold_sql`` is empty exactly when ``expect_refusal`` is set."""

    question: str
    gold_sql: str = ""
    expect_refusal: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.expect_refusal and self.gold_sql:
            raise ValueError(f"refusal case must not carry gold SQL: {self.question!r}")
        if not self.expect_refusal and not self.gold_sql:
            raise ValueError(f"answerable case needs gold SQL: {self.question!r}")


@dataclass(frozen=True, slots=True)
class CaseResult:
    question: str
    predicted_sql: str | None
    expected_refusal: bool
    refused: bool
    execution_match: bool
    sql_valid: bool
    faithfulness: float
    failure_reason: str | None = None

    @property
    def passed(self) -> bool:
        if self.expected_refusal:
            return self.refused
        return self.execution_match


@dataclass(frozen=True, slots=True)
class EvalReport:
    execution_accuracy: float
    refusal_accuracy: float
    sql_valid_rate: float
    faithfulness: float
    n_answerable: int = 0
    n_refusal: int = 0
    results: tuple[CaseResult, ...] = field(default_factory=tuple)

    def regressed(self, baseline: float, tolerance: float) -> bool:
        """True when accuracy fell more than ``tolerance`` below the committed baseline.

        Tolerance exists because a golden set is granular: with n cases, one case
        flipping moves the score by 1/n. A gate tighter than that fires on noise.
        """
        return self.execution_accuracy < baseline - tolerance


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
        refused = _refused(state)

        if case.expect_refusal:
            return CaseResult(
                question=case.question,
                predicted_sql=predicted_sql,
                expected_refusal=True,
                refused=refused,
                execution_match=False,
                sql_valid=bool(predicted_sql) and self._validator.validate(predicted_sql or "").ok,
                faithfulness=0.0,
                failure_reason=None if refused else "answered an out-of-scope question",
            )

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
            expected_refusal=False,
            refused=refused,
            execution_match=match,
            sql_valid=valid,
            faithfulness=faithfulness,
            failure_reason=None if match else "result set did not match gold",
        )


def _refused(state: object) -> bool:
    """The agent declined to produce a data answer.

    Covers all three ways that happens: an error//guardrail dead-end, a clarify
    interrupt (the run pauses without an execution), and a query that ran but
    matched nothing.
    """
    get = state.get  # type: ignore[attr-defined]
    if get("error_code") is not None or get("error") is not None:
        return True
    execution = get("execution")
    return execution is None or execution.is_empty()


def _rate(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _aggregate(results: list[CaseResult]) -> EvalReport:
    answerable = [r for r in results if not r.expected_refusal]
    refusals = [r for r in results if r.expected_refusal]
    return EvalReport(
        execution_accuracy=_rate(sum(r.execution_match for r in answerable), len(answerable)),
        refusal_accuracy=_rate(sum(r.refused for r in refusals), len(refusals)),
        sql_valid_rate=_rate(sum(r.sql_valid for r in answerable), len(answerable)),
        faithfulness=_rate(sum(r.faithfulness for r in answerable), len(answerable)),
        n_answerable=len(answerable),
        n_refusal=len(refusals),
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
