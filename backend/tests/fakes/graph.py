"""Build a QueryService over the real agent graph with fakes (no DB/keys) —
shared by the agent and security test suites."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.services.query_service import QueryService
from app.domain.entities import ExecutionResult
from app.domain.ports.cache import Cache
from app.domain.ports.llm import LLMProvider
from app.domain.ports.repositories import AgentActionRepository
from app.domain.ports.sql import QueryExecutor
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.sql.validator import SqlValidatorChain
from tests.fakes.catalog import FakeSchemaCatalog
from tests.fakes.sql import FakeQueryExecutor
from tests.fakes.tracing import NoopTracer

ROWS = ExecutionResult(
    columns=("country_iso3", "co2_per_capita"),
    rows=(("QAT", 37.6), ("USA", 14.9)),
    row_count=2,
    elapsed_ms=3,
)


def build_service(
    *,
    llm: LLMProvider | None = None,
    executor: QueryExecutor | None = None,
    audit: AgentActionRepository | None = None,
    answer_cache: Cache | None = None,
    max_repair: int = 2,
) -> QueryService:
    deps = NodeDependencies(
        tracer=NoopTracer(),
        catalog=FakeSchemaCatalog(),
        llm=llm or MockLLMProvider(),
        validator=SqlValidatorChain(row_cap=1000),
        executor=executor or FakeQueryExecutor(result=ROWS),
        audit=audit,
    )
    return QueryService(
        GraphBuilder(NodeFactory(deps), max_repair_attempts=max_repair).build(MemorySaver()),
        answer_cache=answer_cache,
    )
