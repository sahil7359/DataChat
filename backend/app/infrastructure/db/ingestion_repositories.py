"""Postgres implementations of the ingestion ports.

These do the actual writes: idempotent upserts into the analytics tables, a
full replace of a dataset's semantic docs (+ embeddings), and the dataset
registry that records the checksum used for idempotency.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.value_objects import DatasetId
from app.infrastructure.db import models
from ingestion.ports import EmbeddedDoc, TableRows

_MODELS = {
    "countries": models.Country,
    "wdi_indicators": models.WdiIndicator,
    "wdi_values": models.WdiValue,
    "owid_co2": models.OwidCo2,
}
_PK = {
    "countries": ("iso3",),
    "wdi_indicators": ("indicator_code",),
    "wdi_values": ("country_iso3", "indicator_code", "year"),
    "owid_co2": ("country_iso3", "year"),
}


def _str_list(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


class PgAnalyticsLoader:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def upsert(self, table: TableRows) -> int:
        model = _MODELS[table.name]
        pk = _PK[table.name]
        values = [dict(zip(table.columns, row, strict=True)) for row in table.rows]
        if not values:
            return 0
        stmt = pg_insert(model).values(values)
        update_cols = {c: getattr(stmt.excluded, c) for c in table.columns if c not in pk}
        if update_cols:
            stmt = stmt.on_conflict_do_update(index_elements=list(pk), set_=update_cols)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(pk))
        async with self._sessionmaker() as session, session.begin():
            await session.execute(stmt)
        return len(values)


class PgDatasetRegistry:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def checksum_for(self, name: str) -> str | None:
        async with self._sessionmaker() as session:
            stmt = select(models.DatasetRow.checksum).where(models.DatasetRow.name == name)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def record(
        self, name: str, source: str, version: str, checksum: str, description: str
    ) -> DatasetId:
        async with self._sessionmaker() as session, session.begin():
            stmt = (
                pg_insert(models.DatasetRow)
                .values(
                    id=uuid.uuid4(),
                    name=name,
                    source=source,
                    version=version,
                    checksum=checksum,
                    description=description,
                )
                .on_conflict_do_update(
                    index_elements=["name"],
                    set_={
                        "source": source,
                        "version": version,
                        "checksum": checksum,
                        "description": description,
                    },
                )
                .returning(models.DatasetRow.id)
            )
            dataset_id = (await session.execute(stmt)).scalar_one()
        return DatasetId(str(dataset_id))


class PgSemanticLayerRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def replace(self, dataset_id: DatasetId, docs: list[EmbeddedDoc]) -> None:
        did = uuid.UUID(dataset_id)
        async with self._sessionmaker() as session, session.begin():
            # Idempotent rewrite: clear then re-insert this dataset's docs.
            await session.execute(
                delete(models.SemanticTable).where(models.SemanticTable.dataset_id == did)
            )
            await session.execute(
                delete(models.FewShotExample).where(models.FewShotExample.dataset_id == did)
            )

            table_ids: dict[str, uuid.UUID] = {}
            for doc in (d for d in docs if d.kind == "table"):
                tid = uuid.uuid4()
                name = str(doc.payload["table_name"])
                table_ids[name] = tid
                session.add(
                    models.SemanticTable(
                        id=tid,
                        dataset_id=did,
                        table_name=name,
                        description=str(doc.payload["description"]),
                        embedding=list(doc.vector.values),
                    )
                )
            await session.flush()

            for doc in (d for d in docs if d.kind == "column"):
                table_name = str(doc.payload["table_name"])
                if table_name not in table_ids:
                    continue
                session.add(
                    models.SemanticColumn(
                        semantic_table_id=table_ids[table_name],
                        column_name=str(doc.payload["column_name"]),
                        data_type=str(doc.payload["data_type"]),
                        unit=_opt_str(doc.payload.get("unit")),
                        description=str(doc.payload["description"]),
                        synonyms=_str_list(doc.payload.get("synonyms")),
                        embedding=list(doc.vector.values),
                    )
                )
            for doc in (d for d in docs if d.kind == "example"):
                session.add(
                    models.FewShotExample(
                        dataset_id=did,
                        question=str(doc.payload["question"]),
                        sql=str(doc.payload["sql"]),
                        tags=_str_list(doc.payload.get("tags")),
                        embedding=list(doc.vector.values),
                    )
                )
