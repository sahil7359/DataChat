"""Ingestion CLI: ``python -m ingestion.run --dataset seed|wdi|owid``.

`seed` runs fully offline against the bundled slice. `wdi`/`owid` fetch from the
public APIs (network required, no key). Embeddings use Gemini when a key is
configured, otherwise the deterministic local embedder — so ingestion works
keyless for dev.
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

from app.config import Settings, get_settings
from app.domain.ports.llm import EmbeddingProvider
from app.infrastructure.connectors.owid import OwidConnector
from app.infrastructure.connectors.seed import SeedConnector
from app.infrastructure.connectors.world_bank import WorldBankConnector
from app.infrastructure.db.ingestion_repositories import (
    PgAnalyticsLoader,
    PgDatasetRegistry,
    PgSemanticLayerRepository,
)
from app.infrastructure.db.session import create_app_engine, create_session_factory
from app.infrastructure.llm.embeddings import GeminiEmbeddingAdapter, LocalHashEmbeddingProvider
from ingestion.pipeline import build_pipeline
from ingestion.ports import DatasetConnector


def _embedder(settings: Settings, client: httpx.AsyncClient) -> EmbeddingProvider:
    key = settings.gemini_api_key.get_secret_value()
    if settings.use_mocks or not key:
        return LocalHashEmbeddingProvider(dim=settings.embedding_dim)
    return GeminiEmbeddingAdapter(
        client, key, model=settings.embedding_model, dim=settings.embedding_dim
    )


def _connector(dataset: str, client: httpx.AsyncClient) -> DatasetConnector:
    if dataset == "seed":
        return SeedConnector()
    if dataset == "wdi":
        return WorldBankConnector(client)
    if dataset == "owid":
        return OwidConnector(client)
    raise SystemExit(f"unknown dataset: {dataset}")


async def _run(dataset: str) -> None:
    settings = get_settings()
    engine = create_app_engine(settings)
    sessionmaker = create_session_factory(engine)
    async with httpx.AsyncClient() as client:
        pipeline = build_pipeline(
            _connector(dataset, client),
            loader=PgAnalyticsLoader(sessionmaker),
            registry=PgDatasetRegistry(sessionmaker),
            semantic_repo=PgSemanticLayerRepository(sessionmaker),
            embedder=_embedder(settings, client),
        )
        ctx = await pipeline.run(dataset)
    await engine.dispose()

    status = "skipped (unchanged)" if ctx.skipped else f"loaded {ctx.rows_loaded} rows"
    print(f"[ingestion] {dataset}: {status}; checksum={ctx.checksum}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ingestion.run")
    parser.add_argument("--dataset", required=True, choices=["seed", "wdi", "owid"])
    args = parser.parse_args()
    asyncio.run(_run(args.dataset))


if __name__ == "__main__":
    main()
