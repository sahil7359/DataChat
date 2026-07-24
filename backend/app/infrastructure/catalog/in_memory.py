"""In-memory SchemaCatalog for offline/dev and the mock path.

Embeds the curated definitions once at build time, then answers retrieval with a
cosine top-k. A table is scored by the best match across its own description and
any of its columns, so a question phrased about a column still surfaces the right
table. With a tiny curated corpus this gives the same behaviour as pgvector
without needing a database (Strategy: swap this for the pgvector catalog in prod).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities import ColumnDoc, Example, RetrievedContext, TableDoc
from app.domain.ports.llm import EmbeddingProvider
from app.domain.value_objects import Vector
from app.infrastructure.catalog.similarity import cosine
from ingestion.ports import DatasetDefinition


@dataclass(frozen=True, slots=True)
class _TableEntry:
    doc: TableDoc
    table_vec: Vector
    column_vecs: tuple[Vector, ...]

    def score(self, query: Vector) -> float:
        return max(cosine(query, self.table_vec), *(cosine(query, cv) for cv in self.column_vecs))


@dataclass(frozen=True, slots=True)
class _ExampleEntry:
    example: Example
    vec: Vector


class InMemorySchemaCatalog:
    def __init__(
        self, tables: list[_TableEntry], examples: list[_ExampleEntry], embedder: EmbeddingProvider
    ) -> None:
        self._tables = tables
        self._examples = examples
        self._embedder = embedder

    async def retrieve(self, question: str, k: int = 8) -> RetrievedContext:
        query = await self._embedder.embed(question)
        ranked_tables = sorted(self._tables, key=lambda t: t.score(query), reverse=True)[:k]
        ranked_examples = sorted(self._examples, key=lambda e: cosine(query, e.vec), reverse=True)[
            :k
        ]
        tables = tuple(
            TableDoc(
                table_name=t.doc.table_name,
                description=t.doc.description,
                columns=t.doc.columns,
                score=round(t.score(query), 4),
            )
            for t in ranked_tables
        )
        examples = tuple(
            Example(
                question=e.example.question,
                sql=e.example.sql,
                tags=e.example.tags,
                score=round(cosine(query, e.vec), 4),
            )
            for e in ranked_examples
        )
        return RetrievedContext(tables=tables, examples=examples)


async def build_in_memory_catalog(
    definitions: list[DatasetDefinition], embedder: EmbeddingProvider
) -> InMemorySchemaCatalog:
    tables: dict[str, _TableEntry] = {}
    examples: list[_ExampleEntry] = []
    for definition in definitions:
        for table in definition.tables:
            if table.name in tables:
                continue
            columns = tuple(
                ColumnDoc(
                    column_name=c.name,
                    data_type=c.data_type,
                    description=c.description,
                    unit=c.unit,
                    synonyms=c.synonyms,
                )
                for c in table.columns
            )
            table_vec = await embedder.embed(f"{table.name}: {table.description}")
            column_vecs = tuple(
                [
                    await embedder.embed(f"{table.name}.{c.name}: {c.description}")
                    for c in table.columns
                ]
            )
            tables[table.name] = _TableEntry(
                doc=TableDoc(table_name=table.name, description=table.description, columns=columns),
                table_vec=table_vec,
                column_vecs=column_vecs,
            )
        for example in definition.examples:
            vec = await embedder.embed(example.question)
            examples.append(
                _ExampleEntry(
                    example=Example(question=example.question, sql=example.sql, tags=example.tags),
                    vec=vec,
                )
            )
    return InMemorySchemaCatalog(list(tables.values()), examples, embedder)
