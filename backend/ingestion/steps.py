"""Chain-of-Responsibility steps. Each link has the same shape
(``process(ctx) -> ctx``) so links can be added, removed, or reordered without
touching the others (SRP + Open/Closed)."""

from __future__ import annotations

from app.domain.ports.llm import EmbeddingProvider
from app.infrastructure.db.base import ANALYTICS_SCHEMA, Base
from ingestion.checksum import checksum_of
from ingestion.ports import (
    AnalyticsLoader,
    DatasetConnector,
    DatasetRegistry,
    EmbeddedDoc,
    IngestionContext,
    IngestionError,
    SemanticColumnDef,
    SemanticLayerRepository,
    SemanticTableDef,
)

# Expected analytics shape, derived from the ORM so validation tracks the schema.
_ANALYTICS_COLUMNS: dict[str, set[str]] = {
    t.name: {c.name for c in t.columns}
    for t in Base.metadata.sorted_tables
    if t.schema == ANALYTICS_SCHEMA
}


class FetchStep:
    def __init__(self, connector: DatasetConnector) -> None:
        self._connector = connector

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        ctx.raw = await self._connector.fetch()
        return ctx


class ValidateStep:
    """Integrity gate (LLM04/ASI06): the fetched data must match the known
    analytics schema, and — if the source declared a checksum — the bytes must
    match it, so tampering in transit or a poisoned source is rejected here."""

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        if ctx.raw is None:
            raise IngestionError("nothing fetched")
        for table in ctx.raw.tables:
            allowed = _ANALYTICS_COLUMNS.get(table.name)
            if allowed is None:
                raise IngestionError(f"unknown analytics table: {table.name}")
            unexpected = set(table.columns) - allowed
            if unexpected:
                raise IngestionError(f"unexpected columns in {table.name}: {sorted(unexpected)}")
            for row in table.rows:
                if len(row) != len(table.columns):
                    raise IngestionError(f"row width mismatch in {table.name}")

        computed = checksum_of(ctx.raw)
        if ctx.raw.declared_checksum and ctx.raw.declared_checksum != computed:
            raise IngestionError(
                f"checksum mismatch for {ctx.dataset}: data does not match the trusted digest"
            )
        ctx.checksum = computed
        return ctx


class IdempotencyStep:
    def __init__(self, registry: DatasetRegistry) -> None:
        self._registry = registry

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        existing = await self._registry.checksum_for(ctx.dataset)
        if existing is not None and existing == ctx.checksum:
            ctx.skipped = True
            ctx.notes.append("checksum unchanged; skipping load")
        return ctx


class RegisterStep:
    def __init__(self, registry: DatasetRegistry) -> None:
        self._registry = registry

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        if ctx.checksum is None:
            raise IngestionError("register step reached before validation set a checksum")
        ctx.dataset_id = await self._registry.record(
            name=ctx.dataset,
            source=ctx.definition.source,
            version=ctx.definition.version,
            checksum=ctx.checksum,
            description=ctx.definition.description,
        )
        return ctx


class LoadStep:
    def __init__(self, loader: AnalyticsLoader) -> None:
        self._loader = loader

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        if ctx.skipped or ctx.raw is None:
            return ctx
        total = 0
        for table in ctx.raw.tables:
            total += await self._loader.upsert(table)
        ctx.rows_loaded = total
        return ctx


class BuildSemanticLayerStep:
    """Embeds the *curated* definition (never the fetched data) into docs."""

    def __init__(self, embedder: EmbeddingProvider) -> None:
        self._embedder = embedder

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        if ctx.skipped:
            return ctx
        docs: list[EmbeddedDoc] = []
        for table in ctx.definition.tables:
            docs.append(await self._embed_table(table))
            for column in table.columns:
                docs.append(await self._embed_column(table.name, column))
        for example in ctx.definition.examples:
            vector = await self._embedder.embed(example.question)
            docs.append(
                EmbeddedDoc(
                    kind="example",
                    text=example.question,
                    vector=vector,
                    payload={
                        "question": example.question,
                        "sql": example.sql,
                        "tags": list(example.tags),
                    },
                )
            )
        ctx.embedded = docs
        return ctx

    async def _embed_table(self, table: SemanticTableDef) -> EmbeddedDoc:
        text = f"{table.name}: {table.description}"
        return EmbeddedDoc(
            kind="table",
            text=text,
            vector=await self._embedder.embed(text),
            payload={"table_name": table.name, "description": table.description},
        )

    async def _embed_column(self, table_name: str, column: SemanticColumnDef) -> EmbeddedDoc:
        unit = f" [{column.unit}]" if column.unit else ""
        synonyms = f" synonyms: {', '.join(column.synonyms)}" if column.synonyms else ""
        text = (
            f"{table_name}.{column.name} ({column.data_type}{unit}): {column.description}{synonyms}"
        )
        return EmbeddedDoc(
            kind="column",
            text=text,
            vector=await self._embedder.embed(text),
            payload={
                "table_name": table_name,
                "column_name": column.name,
                "data_type": column.data_type,
                "unit": column.unit,
                "description": column.description,
                "synonyms": list(column.synonyms),
            },
        )


class WriteSemanticStep:
    def __init__(self, repository: SemanticLayerRepository) -> None:
        self._repository = repository

    async def process(self, ctx: IngestionContext) -> IngestionContext:
        if ctx.skipped or ctx.dataset_id is None:
            return ctx
        await self._repository.replace(ctx.dataset_id, ctx.embedded)
        return ctx
