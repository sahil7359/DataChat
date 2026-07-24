"""pgvector-backed SchemaCatalog (production retrieval).

Embeds the question once, then does a cosine top-k over the semantic tables and
few-shot examples using pgvector's ``<=>`` operator (HNSW index). Only the
retrieved subset enters the SQL-gen prompt — small context, narrower surface.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities import ColumnDoc, Example, RetrievedContext, TableDoc
from app.domain.ports.llm import EmbeddingProvider
from app.infrastructure.db import models


class PgVectorSchemaCatalog:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], embedder: EmbeddingProvider
    ) -> None:
        self._sessionmaker = sessionmaker
        self._embedder = embedder

    async def retrieve(self, question: str, k: int = 8) -> RetrievedContext:
        query = list((await self._embedder.embed(question)).values)
        async with self._sessionmaker() as session:
            tables = await self._retrieve_tables(session, query, k)
            examples = await self._retrieve_examples(session, query, k)
        return RetrievedContext(tables=tables, examples=examples)

    async def _retrieve_tables(
        self, session: AsyncSession, query: list[float], k: int
    ) -> tuple[TableDoc, ...]:
        distance = models.SemanticTable.embedding.cosine_distance(query)
        stmt = select(models.SemanticTable, distance.label("dist")).order_by(distance).limit(k)
        rows = (await session.execute(stmt)).all()
        docs: list[TableDoc] = []
        for table, dist in rows:
            columns = await self._columns_for(session, table.id)
            docs.append(
                TableDoc(
                    table_name=table.table_name,
                    description=table.description,
                    columns=columns,
                    score=round(1.0 - float(dist), 4),
                )
            )
        return tuple(docs)

    async def _columns_for(
        self, session: AsyncSession, table_id: uuid.UUID
    ) -> tuple[ColumnDoc, ...]:
        stmt = select(models.SemanticColumn).where(
            models.SemanticColumn.semantic_table_id == table_id
        )
        cols = (await session.execute(stmt)).scalars().all()
        return tuple(
            ColumnDoc(
                column_name=c.column_name,
                data_type=c.data_type,
                description=c.description,
                unit=c.unit,
                synonyms=tuple(c.synonyms),
            )
            for c in cols
        )

    async def _retrieve_examples(
        self, session: AsyncSession, query: list[float], k: int
    ) -> tuple[Example, ...]:
        distance = models.FewShotExample.embedding.cosine_distance(query)
        stmt = select(models.FewShotExample, distance.label("dist")).order_by(distance).limit(k)
        rows = (await session.execute(stmt)).all()
        return tuple(
            Example(
                question=example.question,
                sql=example.sql,
                tags=tuple(example.tags),
                score=round(1.0 - float(dist), 4),
            )
            for example, dist in rows
        )
