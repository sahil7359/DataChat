"""Ingestion pipeline: idempotency, integrity (checksum/shape), and semantics."""

from __future__ import annotations

import dataclasses

import pytest

from app.infrastructure.connectors.seed import SeedConnector
from app.infrastructure.llm.embeddings import LocalHashEmbeddingProvider
from ingestion.pipeline import IngestionPipeline, build_pipeline
from ingestion.ports import IngestionError, RawDataset, TableRows
from tests.fakes.ingestion import (
    InMemoryAnalyticsLoader,
    InMemoryDatasetRegistry,
    InMemorySemanticLayerRepository,
)


def _pipeline(
    loader: InMemoryAnalyticsLoader,
    registry: InMemoryDatasetRegistry,
    semantic: InMemorySemanticLayerRepository,
) -> IngestionPipeline:
    return build_pipeline(
        SeedConnector(),
        loader=loader,
        registry=registry,
        semantic_repo=semantic,
        embedder=LocalHashEmbeddingProvider(dim=64),
    )


async def test_seed_load_is_idempotent() -> None:
    loader = InMemoryAnalyticsLoader()
    registry = InMemoryDatasetRegistry()
    semantic = InMemorySemanticLayerRepository()
    pipeline = _pipeline(loader, registry, semantic)

    first = await pipeline.run("seed")
    counts = {t: loader.row_count(t) for t in loader.store}

    second = await pipeline.run("seed")

    assert not first.skipped
    assert first.rows_loaded > 0
    assert second.skipped  # checksum unchanged -> no reload
    assert {t: loader.row_count(t) for t in loader.store} == counts  # no duplicates


async def test_semantic_layer_is_embedded_and_written() -> None:
    loader = InMemoryAnalyticsLoader()
    registry = InMemoryDatasetRegistry()
    semantic = InMemorySemanticLayerRepository()

    ctx = await _pipeline(loader, registry, semantic).run("seed")

    assert ctx.dataset_id is not None
    docs = semantic.by_dataset[ctx.dataset_id]
    kinds = {d.kind for d in docs}
    assert kinds == {"table", "column", "example"}
    assert all(d.vector.dim == 64 for d in docs)  # embedding dim == configured


async def test_tampered_data_is_rejected_by_checksum() -> None:
    # Simulate poisoning: mutate a row while keeping the trusted declared digest.
    from ingestion.definitions import seed_raw

    original = seed_raw()
    countries = original.tables[0]
    tampered_rows = (("ZZZ", "Evilland", "Nowhere", "High income"), *countries.rows[1:])
    tampered = dataclasses.replace(
        original,
        tables=(TableRows(countries.name, countries.columns, tampered_rows), *original.tables[1:]),
    )

    class TamperConnector:
        name = "seed"

        async def fetch(self) -> RawDataset:
            return tampered

    pipeline = build_pipeline(
        TamperConnector(),
        loader=InMemoryAnalyticsLoader(),
        registry=InMemoryDatasetRegistry(),
        semantic_repo=InMemorySemanticLayerRepository(),
        embedder=LocalHashEmbeddingProvider(dim=16),
    )

    with pytest.raises(IngestionError, match="checksum mismatch"):
        await pipeline.run("seed")


async def test_unexpected_table_or_column_is_rejected() -> None:
    class RogueConnector:
        name = "seed"

        async def fetch(self) -> RawDataset:
            return RawDataset(
                dataset="seed",
                source="x",
                tables=(TableRows("secrets", ("password",), (("hunter2",),)),),
            )

    pipeline = build_pipeline(
        RogueConnector(),
        loader=InMemoryAnalyticsLoader(),
        registry=InMemoryDatasetRegistry(),
        semantic_repo=InMemorySemanticLayerRepository(),
        embedder=LocalHashEmbeddingProvider(dim=16),
    )

    with pytest.raises(IngestionError, match="unknown analytics table"):
        await pipeline.run("seed")
