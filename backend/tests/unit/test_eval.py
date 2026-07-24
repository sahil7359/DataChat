"""Evaluation harness: scorers, aggregation, and the regression gate — offline."""

from __future__ import annotations

from app.application.agent.state import AgentState
from app.application.services.eval_service import (
    EvalCase,
    EvalService,
    FaithfulnessJudge,
    compare_result_sets,
)
from app.domain.entities import ExecutionResult
from app.infrastructure.sql.validator import SqlValidatorChain
from tests.fakes.sql import FakeQueryExecutor


def _result(rows: tuple[tuple[object, ...], ...]) -> ExecutionResult:
    return ExecutionResult(columns=("a", "b"), rows=rows, row_count=len(rows), elapsed_ms=1)


def test_compare_result_sets_is_order_and_name_insensitive() -> None:
    a = _result((("QAT", 37.6), ("USA", 14.9)))
    b = ExecutionResult(
        columns=("x", "y"), rows=(("USA", 14.9), ("QAT", 37.6)), row_count=2, elapsed_ms=9
    )
    assert compare_result_sets(a, b)


def test_compare_result_sets_detects_difference() -> None:
    assert not compare_result_sets(_result((("QAT", 37.6),)), _result((("USA", 14.9),)))
    assert not compare_result_sets(_result(()), None)


class ScriptedQueryService:
    """Returns a fixed agent state per question (stands in for the real agent)."""

    def __init__(self, states: dict[str, AgentState]) -> None:
        self._states = states

    async def run(self, question: str, conversation_id: str | None = None) -> AgentState:
        return self._states[question]


class FixedJudge(FaithfulnessJudge):
    def __init__(self, score: float) -> None:
        self._score = score

    async def score(self, question: str, execution: object, explanation: str) -> float:
        return self._score


def _state(sql: str, rows: tuple[tuple[object, ...], ...]) -> AgentState:
    return {"candidate_sql": sql, "execution": _result(rows), "explanation": "grounded prose"}


async def test_perfect_run_scores_full_accuracy() -> None:
    gold_rows = (("QAT", 37.6), ("USA", 14.9))
    cases = [EvalCase(question="q1", gold_sql="SELECT * FROM owid_co2 LIMIT 2")]
    service = EvalService(
        ScriptedQueryService({"q1": _state("SELECT a, b FROM owid_co2 LIMIT 2", gold_rows)}),  # type: ignore[arg-type]
        FakeQueryExecutor(result=_result(gold_rows)),
        SqlValidatorChain(row_cap=1000),
        FixedJudge(1.0),
    )

    report = await service.evaluate(cases)

    assert report.execution_accuracy == 1.0
    assert report.sql_valid_rate == 1.0
    assert report.faithfulness == 1.0
    assert not report.regressed(baseline=0.7)


async def test_wrong_result_flags_regression() -> None:
    cases = [EvalCase(question="q1", gold_sql="SELECT a, b FROM owid_co2 LIMIT 2")]
    service = EvalService(
        ScriptedQueryService({"q1": _state("SELECT a, b FROM owid_co2 LIMIT 2", (("IND", 2.0),))}),  # type: ignore[arg-type]
        FakeQueryExecutor(result=_result((("QAT", 37.6),))),
        SqlValidatorChain(row_cap=1000),
        FixedJudge(0.5),
    )

    report = await service.evaluate(cases)

    assert report.execution_accuracy == 0.0
    assert report.regressed(baseline=0.7)  # below threshold -> CI would fail


async def test_faithfulness_judge_parses_score() -> None:
    from app.domain.value_objects import Provider
    from tests.fakes.llm import FakeLLMProvider

    judge = FaithfulnessJudge(FakeLLMProvider(provider=Provider.GROQ, default="0.9"))
    score = await judge.score("q", _result((("QAT", 37.6),)), "Qatar leads at 37.6.")
    assert score == 0.9
