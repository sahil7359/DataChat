"""Build a fully-wired FastAPI app with fakes for contract tests — no DB, no
keys, no lifespan setup (app.state is pre-populated and ``configured`` is set)."""

from __future__ import annotations

from fastapi import FastAPI
from langgraph.checkpoint.memory import MemorySaver

from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.services.query_service import QueryService
from app.config import Settings
from app.domain.entities import ExecutionResult
from app.domain.ports.cache import Cache
from app.domain.ports.repositories import ConversationRepository
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.sql.validator import SqlValidatorChain
from app.interface.api.rate_limit import RateLimiter
from app.main import create_app
from ingestion.definitions import seed_scope
from tests.fakes.cache import InMemoryCache
from tests.fakes.catalog import FakeSchemaCatalog
from tests.fakes.sql import FakeQueryExecutor
from tests.fakes.tracing import NoopTracer

_ROWS = ExecutionResult(
    columns=("country_iso3", "co2_per_capita"),
    rows=(("QAT", 37.6), ("AUS", 15.0)),
    row_count=2,
    elapsed_ms=3,
)


def default_query_service() -> QueryService:
    deps = NodeDependencies(
        scope=seed_scope(),
        tracer=NoopTracer(),
        catalog=FakeSchemaCatalog(),
        llm=MockLLMProvider(),
        validator=SqlValidatorChain(row_cap=1000),
        executor=FakeQueryExecutor(result=_ROWS),
    )
    graph = GraphBuilder(NodeFactory(deps)).build(MemorySaver())
    return QueryService(graph)


def build_test_app(
    *,
    query_service: QueryService | None = None,
    cache: Cache | None = None,
    per_minute: int = 1000,
    conversation_repo: ConversationRepository | None = None,
) -> FastAPI:
    app = create_app(Settings(use_mocks=True))
    resolved_cache = cache or InMemoryCache()
    app.state.cache = resolved_cache
    app.state.query_service = query_service or default_query_service()
    app.state.rate_limiter = RateLimiter(
        resolved_cache, per_minute=per_minute, daily_quota=1_000_000
    )
    app.state.conversation_repo = conversation_repo
    app.state.configured = True
    return app
