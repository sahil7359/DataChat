"""In-memory RAG retrieval: relevant tables/examples surface for a question."""

from __future__ import annotations

from app.infrastructure.catalog.in_memory import InMemorySchemaCatalog, build_in_memory_catalog
from app.infrastructure.llm.embeddings import LocalHashEmbeddingProvider
from ingestion.definitions import SEED_DEFINITION


async def _catalog(dim: int = 256) -> InMemorySchemaCatalog:
    return await build_in_memory_catalog([SEED_DEFINITION], LocalHashEmbeddingProvider(dim=dim))


async def test_co2_question_surfaces_the_owid_table() -> None:
    catalog = await _catalog()
    ctx = await catalog.retrieve("Which countries had the highest CO2 per capita?", k=2)
    table_names = [t.table_name for t in ctx.tables]
    assert "owid_co2" in table_names


async def test_gdp_question_surfaces_wdi_tables() -> None:
    catalog = await _catalog()
    ctx = await catalog.retrieve("countries by GDP per capita in 2022", k=3)
    table_names = {t.table_name for t in ctx.tables}
    assert "wdi_values" in table_names or "wdi_indicators" in table_names


async def test_retrieval_returns_relevant_examples() -> None:
    catalog = await _catalog()
    ctx = await catalog.retrieve("highest CO2 per capita in 2022", k=4)
    joined = " ".join(e.sql.lower() for e in ctx.examples)
    assert "owid_co2" in joined


async def test_retrieved_tables_carry_their_columns() -> None:
    catalog = await _catalog()
    ctx = await catalog.retrieve("co2 per capita", k=1)
    assert ctx.tables
    assert ctx.tables[0].columns  # columns travel with the table for grounding


async def test_k_bounds_the_result() -> None:
    catalog = await _catalog()
    ctx = await catalog.retrieve("anything", k=1)
    assert len(ctx.tables) == 1
