"""Full ingestion + pgvector retrieval against a live Postgres (CI/Docker)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.catalog.pgvector import PgVectorSchemaCatalog
from app.infrastructure.connectors.seed import SeedConnector
from app.infrastructure.db.ingestion_repositories import (
    PgAnalyticsLoader,
    PgDatasetRegistry,
    PgSemanticLayerRepository,
)
from app.infrastructure.llm.embeddings import LocalHashEmbeddingProvider
from ingestion.pipeline import build_pipeline

pytestmark = pytest.mark.integration


async def test_seed_ingest_loads_rows_and_retrieval_works(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    embedder = LocalHashEmbeddingProvider(dim=768)
    pipeline = build_pipeline(
        SeedConnector(),
        loader=PgAnalyticsLoader(migrated_sessionmaker),
        registry=PgDatasetRegistry(migrated_sessionmaker),
        semantic_repo=PgSemanticLayerRepository(migrated_sessionmaker),
        embedder=embedder,
    )

    first = await pipeline.run("seed")
    assert first.rows_loaded > 0

    # Re-run: idempotent, no new rows.
    async with migrated_sessionmaker() as session:
        before = (
            await session.execute(text("SELECT count(*) FROM analytics.owid_co2"))
        ).scalar_one()
    await pipeline.run("seed")
    async with migrated_sessionmaker() as session:
        after = (
            await session.execute(text("SELECT count(*) FROM analytics.owid_co2"))
        ).scalar_one()
    assert before == after

    catalog = PgVectorSchemaCatalog(migrated_sessionmaker, embedder)
    ctx = await catalog.retrieve("highest CO2 per capita in 2022", k=2)
    assert any(t.table_name == "owid_co2" for t in ctx.tables)
    assert ctx.examples
