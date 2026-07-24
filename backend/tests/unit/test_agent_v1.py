"""v1 agent: bounded self-repair, HITL approve/clarify with durable resume,
Vega-Lite charts, and the SSE event stream — all offline with fakes + MemorySaver."""

from __future__ import annotations

from collections.abc import AsyncIterator

from langgraph.checkpoint.memory import MemorySaver

from app.application.agent.events import (
    AgentEvent,
    AwaitingApprovalEvent,
    ChartSpecEvent,
    DoneEvent,
    ExplanationDeltaEvent,
    RowsEvent,
    SqlEvent,
)
from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.services.query_service import QueryService
from app.domain.entities import ExecutionResult
from app.domain.ports.llm import LLMProvider
from app.domain.ports.sql import QueryExecutor
from app.domain.results import Err, ExecutionError, Ok, Result
from app.domain.value_objects import TaskKind
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.sql.validator import SqlValidatorChain
from tests.fakes.catalog import FakeSchemaCatalog
from tests.fakes.sql import FakeQueryExecutor
from tests.fakes.tracing import NoopTracer

_ROWS = ExecutionResult(
    columns=("country_iso3", "co2_per_capita"),
    rows=(("QAT", 37.6), ("AUS", 15.0), ("USA", 14.9)),
    row_count=3,
    elapsed_ms=4,
)


class FlakyExecutor:
    """Fails `fail_times` with a DB error, then succeeds — to exercise repair."""

    def __init__(self, *, fail_times: int, result: ExecutionResult) -> None:
        self._fail_times = fail_times
        self._result = result
        self.calls = 0
        self.executed: list[str] = []

    async def execute(self, sql: str) -> Result[ExecutionResult, ExecutionError]:
        self.calls += 1
        self.executed.append(sql)
        if self.calls <= self._fail_times:
            return Err(ExecutionError("column foo does not exist", code="42703"))
        return Ok(self._result)


def _deps(
    *, llm: LLMProvider | None = None, executor: QueryExecutor | None = None
) -> NodeDependencies:
    return NodeDependencies(
        tracer=NoopTracer(),
        catalog=FakeSchemaCatalog(),
        llm=llm or MockLLMProvider(),
        validator=SqlValidatorChain(row_cap=1000),
        executor=executor or FakeQueryExecutor(result=_ROWS),
    )


def _service(deps: NodeDependencies, *, max_repair: int = 2) -> QueryService:
    graph = GraphBuilder(NodeFactory(deps), max_repair_attempts=max_repair).build(MemorySaver())
    return QueryService(graph)


async def _collect(stream: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    return [event async for event in stream]


# --- self-repair -----------------------------------------------------------


async def test_repair_fixes_a_broken_query_within_budget() -> None:
    executor = FlakyExecutor(fail_times=1, result=_ROWS)
    service = _service(_deps(executor=executor), max_repair=2)

    state = await service.run("top co2 per capita 2022")

    assert state.get("execution") is not None  # succeeded after repair
    assert state["repair_attempts"] == 1
    assert executor.calls == 2


async def test_repair_loop_is_hard_capped() -> None:
    executor = FlakyExecutor(fail_times=99, result=_ROWS)
    service = _service(_deps(executor=executor), max_repair=2)

    state = await service.run("top co2 per capita 2022")

    assert state.get("execution") is None
    assert state.get("error") is not None
    assert state["repair_attempts"] == 2  # bounded, then graceful terminal (ASI08)
    assert executor.calls == 3  # initial + 2 repairs, never more


# --- charts ----------------------------------------------------------------


async def test_chart_spec_is_emitted_and_valid() -> None:
    from app.application.agent.charts import is_valid_chart_spec

    service = _service(_deps())
    state = await service.run("highest co2 per capita in 2022")

    chart = state.get("chart_spec")
    assert chart is not None
    assert is_valid_chart_spec(chart.spec)
    assert chart.spec["mark"] == "bar"


# --- HITL approve ----------------------------------------------------------


async def test_hitl_pauses_before_execute_and_resumes_durably() -> None:
    executor = FakeQueryExecutor(result=_ROWS)
    service = _service(_deps(executor=executor))

    events = await _collect(service.stream("top co2 per capita 2022", approve_sql=True))

    approvals = [e for e in events if isinstance(e, AwaitingApprovalEvent)]
    assert len(approvals) == 1
    assert approvals[0].kind == "approve"
    assert approvals[0].sql  # the exact SQL is shown for approval
    assert executor.executed == []  # nothing ran during the pause

    run_id = approvals[0].run_id
    resumed = await _collect(service.resume(run_id, {"decision": "approve"}))

    assert any(isinstance(e, RowsEvent) for e in resumed)
    assert any(isinstance(e, DoneEvent) for e in resumed)
    assert len(executor.executed) == 1  # ran only after approval


async def test_hitl_reject_never_executes() -> None:
    executor = FakeQueryExecutor(result=_ROWS)
    service = _service(_deps(executor=executor))

    events = await _collect(service.stream("top co2 per capita 2022", approve_sql=True))
    run_id = next(e for e in events if isinstance(e, AwaitingApprovalEvent)).run_id

    await _collect(service.resume(run_id, {"decision": "reject"}))
    assert executor.executed == []


async def test_hitl_edit_revalidates_and_runs_edited_sql() -> None:
    executor = FakeQueryExecutor(result=_ROWS)
    service = _service(_deps(executor=executor))

    events = await _collect(service.stream("top co2 per capita 2022", approve_sql=True))
    run_id = next(e for e in events if isinstance(e, AwaitingApprovalEvent)).run_id

    edited = "SELECT country_iso3 FROM owid_co2 WHERE year = 2022 LIMIT 5"
    await _collect(service.resume(run_id, {"decision": "edit", "edited_sql": edited}))

    assert len(executor.executed) == 1
    assert "LIMIT 5" in executor.executed[0]  # the edited SQL ran, re-validated


# --- HITL clarify ----------------------------------------------------------


async def test_clarify_asks_then_resumes() -> None:
    ambiguous = MockLLMProvider(responses={TaskKind.CLARIFY: "GDP total|GDP per capita"})
    service = _service(_deps(llm=ambiguous))

    events = await _collect(service.stream("which are the richest countries?"))
    clarifies = [e for e in events if isinstance(e, AwaitingApprovalEvent)]
    assert clarifies and clarifies[0].kind == "clarify"
    assert "GDP per capita" in list(clarifies[0].options)

    run_id = clarifies[0].run_id
    resumed = await _collect(service.resume(run_id, {"clarification": "GDP per capita"}))
    assert any(isinstance(e, DoneEvent) for e in resumed)


# --- SSE event stream ------------------------------------------------------


async def test_stream_emits_the_documented_event_types() -> None:
    service = _service(_deps())
    events = await _collect(service.stream("highest co2 per capita in 2022"))

    types = {type(e) for e in events}
    assert SqlEvent in types
    assert RowsEvent in types
    assert ExplanationDeltaEvent in types
    assert ChartSpecEvent in types
    assert DoneEvent in types
