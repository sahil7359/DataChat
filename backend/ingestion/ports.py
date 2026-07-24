"""Ports and data carriers for the ingestion pipeline.

Kept in the ingestion package (offline application code) rather than the domain,
because they describe an offline job, not the request-path core. Each step depends
only on these interfaces so a step can be tested with in-memory fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.value_objects import DatasetId, Vector


class IngestionError(Exception):
    """A dataset failed validation (bad shape, checksum mismatch, tampering)."""


@dataclass(frozen=True, slots=True)
class TableRows:
    """A normalized analytics table ready to load."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class RawDataset:
    dataset: str
    source: str
    tables: tuple[TableRows, ...]
    declared_checksum: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticColumnDef:
    name: str
    data_type: str
    description: str
    unit: str | None = None
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticTableDef:
    name: str
    description: str
    columns: tuple[SemanticColumnDef, ...]


@dataclass(frozen=True, slots=True)
class ExampleDef:
    question: str
    sql: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    """Curated semantic layer for a dataset — the grounding surface."""

    name: str
    source: str
    version: str
    description: str
    tables: tuple[SemanticTableDef, ...]
    examples: tuple[ExampleDef, ...]


@dataclass(frozen=True, slots=True)
class EmbeddedDoc:
    kind: str  # "table" | "column" | "example"
    text: str
    vector: Vector
    payload: dict[str, object]


@dataclass(slots=True)
class IngestionContext:
    """Mutable carrier threaded through the chain."""

    dataset: str
    definition: DatasetDefinition
    raw: RawDataset | None = None
    checksum: str | None = None
    skipped: bool = False
    rows_loaded: int = 0
    embedded: list[EmbeddedDoc] = field(default_factory=list)
    dataset_id: DatasetId | None = None
    notes: list[str] = field(default_factory=list)


class DatasetConnector(Protocol):
    name: str

    async def fetch(self) -> RawDataset: ...


class AnalyticsLoader(Protocol):
    async def upsert(self, table: TableRows) -> int:
        """Idempotent load of one table; returns rows written. Same data twice
        must not duplicate (ON CONFLICT / keyed store)."""
        ...


class SemanticLayerRepository(Protocol):
    async def replace(self, dataset_id: DatasetId, docs: list[EmbeddedDoc]) -> None:
        """Replace the dataset's semantic docs + embeddings (idempotent rewrite)."""
        ...


class DatasetRegistry(Protocol):
    async def checksum_for(self, name: str) -> str | None: ...

    async def record(
        self, name: str, source: str, version: str, checksum: str, description: str
    ) -> DatasetId: ...
