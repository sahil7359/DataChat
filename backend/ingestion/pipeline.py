"""The ingestion pipeline: an ordered chain of steps run over one context."""

from __future__ import annotations

from typing import Protocol

from app.domain.ports.llm import EmbeddingProvider
from ingestion.definitions import DEFINITIONS
from ingestion.ports import (
    AnalyticsLoader,
    DatasetConnector,
    DatasetRegistry,
    IngestionContext,
    IngestionError,
    SemanticLayerRepository,
)
from ingestion.steps import (
    BuildSemanticLayerStep,
    FetchStep,
    IdempotencyStep,
    LoadStep,
    RegisterStep,
    ValidateStep,
    WriteSemanticStep,
)


class Step(Protocol):
    async def process(self, ctx: IngestionContext) -> IngestionContext: ...


class IngestionPipeline:
    def __init__(self, steps: list[Step]) -> None:
        self._steps = steps

    async def run(self, dataset: str) -> IngestionContext:
        definition = DEFINITIONS.get(dataset)
        if definition is None:
            raise IngestionError(f"unknown dataset: {dataset}")
        ctx = IngestionContext(dataset=dataset, definition=definition)
        for step in self._steps:
            ctx = await step.process(ctx)
        return ctx


def build_pipeline(
    connector: DatasetConnector,
    *,
    loader: AnalyticsLoader,
    registry: DatasetRegistry,
    semantic_repo: SemanticLayerRepository,
    embedder: EmbeddingProvider,
) -> IngestionPipeline:
    return IngestionPipeline(
        [
            FetchStep(connector),
            ValidateStep(),
            IdempotencyStep(registry),
            RegisterStep(registry),
            LoadStep(loader),
            BuildSemanticLayerStep(embedder),
            WriteSemanticStep(semantic_repo),
        ]
    )
