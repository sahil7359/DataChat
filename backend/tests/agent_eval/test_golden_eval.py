"""Golden-set evaluation against the seed DB (CI: `pytest -m eval`).

Runs the real agent graph (mock LLM, pgvector catalog, read-only executor) over
the golden set, computes the scorers, and records an ``eval_runs`` row — the same
path CI uses as a regression gate. Marked integration too so it's skipped unless a
test database is configured.
"""

from __future__ import annotations

import os

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.services.eval_service import EvalService, FaithfulnessJudge
from app.application.services.golden_set import GOLDEN_SET
from app.application.services.query_service import QueryService
from app.config import get_settings
from app.infrastructure.catalog.pgvector import PgVectorSchemaCatalog
from app.infrastructure.connectors.seed import SeedConnector
from app.infrastructure.db.ingestion_repositories import (
    PgAnalyticsLoader,
    PgDatasetRegistry,
    PgSemanticLayerRepository,
)
from app.infrastructure.db.repositories import SqlEvalRepository
from app.infrastructure.llm.embeddings import LocalHashEmbeddingProvider
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.sql.executor import ReadOnlyQueryExecutor
from app.infrastructure.sql.validator import SqlValidatorChain
from ingestion.pipeline import build_pipeline
from tests.fakes.tracing import NoopTracer

pytestmark = [pytest.mark.eval, pytest.mark.integration]


def _executor_engine() -> AsyncEngine:
    admin = make_url(os.environ["DATACHAT_TEST_DATABASE_URL"])
    pw = get_settings().executor_role_password.get_secret_value()
    return create_async_engine(admin.set(username="datachat_exec", password=pw))


async def test_golden_set_produces_metrics_and_records_a_run(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    embedder = LocalHashEmbeddingProvider(dim=768)
    await build_pipeline(
        SeedConnector(),
        loader=PgAnalyticsLoader(migrated_sessionmaker),
        registry=PgDatasetRegistry(migrated_sessionmaker),
        semantic_repo=PgSemanticLayerRepository(migrated_sessionmaker),
        embedder=embedder,
    ).run("seed")

    engine = _executor_engine()
    try:
        executor = ReadOnlyQueryExecutor(engine, row_cap=1000, timeout_s=5)
        llm = MockLLMProvider()
        deps = NodeDependencies(
            tracer=NoopTracer(),
            catalog=PgVectorSchemaCatalog(migrated_sessionmaker, embedder),
            llm=llm,
            validator=SqlValidatorChain(row_cap=1000),
            executor=executor,
        )
        service = QueryService(GraphBuilder(NodeFactory(deps)).build(MemorySaver()))
        harness = EvalService(service, executor, SqlValidatorChain(1000), FaithfulnessJudge(llm))

        report = await harness.evaluate(GOLDEN_SET)

        assert 0.0 <= report.execution_accuracy <= 1.0
        assert len(report.results) == len(GOLDEN_SET)

        repo = SqlEvalRepository(migrated_sessionmaker)
        run_id = await repo.record_run(
            "test-sha",
            report.execution_accuracy,
            report.faithfulness,
            report.guardrail_pass_rate,
            None,
        )
        assert run_id
    finally:
        await engine.dispose()
