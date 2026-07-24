"""MVP agent graph end-to-end with fakes + an in-memory checkpointer.

No DB, no keys: a seeded FakeQueryExecutor + MockLLMProvider + the real guardrail.
This proves the happy path (question -> table + grounded prose), the safe-refusal
branch, that every node is traced, and that state is checkpointed each step.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.agent.nodes.generate_sql import GenerateSqlNode
from app.application.agent.state import AgentState
from app.application.services.query_service import QueryService
from app.domain.entities import ExecutionResult
from app.domain.results import LLMOutputError
from app.domain.value_objects import TaskKind
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.sql.validator import SqlValidatorChain
from tests.fakes.catalog import FakeSchemaCatalog
from tests.fakes.llm import FakeLLMProvider
from tests.fakes.sql import FakeQueryExecutor
from tests.fakes.tracing import NoopTracer

_ROWS = ExecutionResult(
    columns=("country_iso3", "co2_per_capita"),
    rows=(("QAT", 37.6), ("AUS", 15.0), ("USA", 14.9)),
    row_count=3,
    elapsed_ms=4,
)


def _deps(
    *,
    tracer: NoopTracer,
    llm: Any = None,
    executor: FakeQueryExecutor | None = None,
) -> NodeDependencies:
    return NodeDependencies(
        tracer=tracer,
        catalog=FakeSchemaCatalog(),
        llm=llm or MockLLMProvider(),
        validator=SqlValidatorChain(row_cap=1000),
        executor=executor or FakeQueryExecutor(result=_ROWS),
    )


def _service(deps: NodeDependencies, saver: MemorySaver) -> QueryService:
    graph = GraphBuilder(NodeFactory(deps)).build(saver)
    return QueryService(graph)


async def test_happy_path_returns_table_and_grounded_prose() -> None:
    tracer = NoopTracer()
    service = _service(_deps(tracer=tracer), MemorySaver())

    state = await service.run("Which countries had the highest CO2 per capita in 2022?")

    assert state.get("error") is None
    assert state["stage"] == "done"
    execution = state.get("execution")
    assert execution is not None and execution.row_count == 3
    assert state.get("explanation")
    assert state.get("provider_used") == "gemini"
    assert "sql_generation" in state["prompt_versions"]
    assert "explanation" in state["prompt_versions"]


async def test_unsafe_generation_is_refused_not_executed() -> None:
    tracer = NoopTracer()
    unsafe = MockLLMProvider(responses={TaskKind.SQL_GEN: "DROP TABLE countries"})
    executor = FakeQueryExecutor(result=_ROWS)
    service = _service(_deps(tracer=tracer, llm=unsafe, executor=executor), MemorySaver())

    state = await service.run("delete everything")

    assert state.get("error") is not None
    assert state.get("execution") is None  # never executed
    assert executor.executed == []  # the guardrail stopped it before the executor
    assert state["stage"] == "done"


async def test_every_node_is_traced() -> None:
    tracer = NoopTracer()
    service = _service(_deps(tracer=tracer), MemorySaver())

    await service.run("Which countries had the highest CO2 per capita in 2022?")

    span_names = {span.name for span in tracer.spans}
    for node in (
        "understand",
        "retrieve",
        "plan",
        "generate_sql",
        "guardrail",
        "execute",
        "explain",
        "respond",
    ):
        assert f"node.{node}" in span_names


async def test_state_is_checkpointed_each_step() -> None:
    saver = MemorySaver()
    graph = GraphBuilder(NodeFactory(_deps(tracer=NoopTracer()))).build(saver)
    config = {"configurable": {"thread_id": "t-1"}}

    await graph.ainvoke(
        {"conversation_id": "c1", "run_id": "t-1", "question": "top co2 per capita 2022"},
        config=config,
    )

    snapshot = graph.get_state(config)
    assert snapshot.values["stage"] == "done"
    assert snapshot.values.get("execution") is not None


async def test_generate_sql_rejects_empty_output() -> None:
    node = GenerateSqlNode(NoopTracer(), FakeLLMProvider(default=""))
    state: AgentState = {"question": "q", "run_id": "r"}

    with pytest.raises(LLMOutputError):
        await node(state)


async def test_generate_sql_strips_markdown_fences() -> None:
    fenced = FakeLLMProvider(default="```sql\nSELECT 1 LIMIT 1\n```")
    node = GenerateSqlNode(NoopTracer(), fenced)
    state: AgentState = {"question": "q", "run_id": "r"}

    update = await node(state)
    assert update["candidate_sql"] == "SELECT 1 LIMIT 1"
