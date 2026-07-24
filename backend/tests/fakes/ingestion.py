"""In-memory ingestion fakes for testing the pipeline without a database."""

from __future__ import annotations

from app.domain.value_objects import DatasetId, new_uuid
from ingestion.ports import EmbeddedDoc, TableRows

_PK = {
    "countries": ("iso3",),
    "wdi_indicators": ("indicator_code",),
    "wdi_values": ("country_iso3", "indicator_code", "year"),
    "owid_co2": ("country_iso3", "year"),
}


class InMemoryAnalyticsLoader:
    def __init__(self) -> None:
        self.store: dict[str, dict[tuple[object, ...], tuple[object, ...]]] = {}

    async def upsert(self, table: TableRows) -> int:
        pk_index = tuple(table.columns.index(c) for c in _PK[table.name])
        bucket = self.store.setdefault(table.name, {})
        for row in table.rows:
            key = tuple(row[i] for i in pk_index)
            bucket[key] = row
        return len(table.rows)

    def row_count(self, table: str) -> int:
        return len(self.store.get(table, {}))


class InMemoryDatasetRegistry:
    def __init__(self) -> None:
        self._checksums: dict[str, str] = {}
        self._ids: dict[str, DatasetId] = {}

    async def checksum_for(self, name: str) -> str | None:
        return self._checksums.get(name)

    async def record(
        self, name: str, source: str, version: str, checksum: str, description: str
    ) -> DatasetId:
        self._checksums[name] = checksum
        dataset_id = self._ids.setdefault(name, DatasetId(new_uuid()))
        return dataset_id


class InMemorySemanticLayerRepository:
    def __init__(self) -> None:
        self.by_dataset: dict[DatasetId, list[EmbeddedDoc]] = {}

    async def replace(self, dataset_id: DatasetId, docs: list[EmbeddedDoc]) -> None:
        self.by_dataset[dataset_id] = list(docs)
