"""Fake semantic-layer catalog returning a preset grounding context."""

from __future__ import annotations

from app.domain.entities import ColumnDoc, Example, RetrievedContext, TableDoc


def default_context() -> RetrievedContext:
    return RetrievedContext(
        tables=(
            TableDoc(
                table_name="owid_co2",
                description="CO2 emissions by country and year.",
                columns=(
                    ColumnDoc("country_iso3", "char(3)", "ISO3 country code"),
                    ColumnDoc("year", "int", "Calendar year"),
                    ColumnDoc("co2_per_capita", "double", "CO2 per capita", unit="tonnes"),
                ),
                score=0.91,
            ),
        ),
        examples=(
            Example(
                question="Top 5 countries by CO2 per capita in 2022",
                sql=(
                    "SELECT country_iso3, co2_per_capita FROM owid_co2 "
                    "WHERE year = 2022 ORDER BY co2_per_capita DESC LIMIT 5"
                ),
                tags=("ranking",),
                score=0.88,
            ),
        ),
    )


class FakeSchemaCatalog:
    def __init__(self, context: RetrievedContext | None = None) -> None:
        self._context = context or default_context()
        self.queries: list[str] = []

    async def retrieve(self, question: str, k: int = 8) -> RetrievedContext:
        self.queries.append(question)
        return self._context
