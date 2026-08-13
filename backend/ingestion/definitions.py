"""Curated semantic layer + a tiny, self-consistent seed slice.

The seed is intentionally small (Neon free is 0.5 GB — Schema §9) but realistic
enough to answer the golden set. Values are approximate real-world 2022 figures
so the demo reads truthfully; correctness of the eval only needs the gold SQL and
predicted SQL to run against the *same* data, so exactness isn't required.
"""

from __future__ import annotations

from app.domain.scope import DataScope
from ingestion.checksum import compute_checksum
from ingestion.ports import (
    DatasetDefinition,
    ExampleDef,
    RawDataset,
    SemanticColumnDef,
    SemanticTableDef,
    TableRows,
)

# --- seed rows -------------------------------------------------------------

# iso3 -> (name, region, income_group)
_COUNTRIES: dict[str, tuple[str, str, str]] = {
    "USA": ("United States", "North America", "High income"),
    "CHN": ("China", "East Asia & Pacific", "Upper middle income"),
    "IND": ("India", "South Asia", "Lower middle income"),
    "QAT": ("Qatar", "Middle East & North Africa", "High income"),
    "DEU": ("Germany", "Europe & Central Asia", "High income"),
    "GBR": ("United Kingdom", "Europe & Central Asia", "High income"),
    "FRA": ("France", "Europe & Central Asia", "High income"),
    "JPN": ("Japan", "East Asia & Pacific", "High income"),
    "BRA": ("Brazil", "Latin America & Caribbean", "Upper middle income"),
    "ZAF": ("South Africa", "Sub-Saharan Africa", "Upper middle income"),
    "NGA": ("Nigeria", "Sub-Saharan Africa", "Lower middle income"),
    "AUS": ("Australia", "East Asia & Pacific", "High income"),
    "CAN": ("Canada", "North America", "High income"),
    "SAU": ("Saudi Arabia", "Middle East & North Africa", "High income"),
    "RUS": ("Russian Federation", "Europe & Central Asia", "Upper middle income"),
}

_GDP_PC_2022: dict[str, float] = {
    "USA": 76329,
    "CHN": 12720,
    "IND": 2411,
    "QAT": 87661,
    "DEU": 48718,
    "GBR": 45850,
    "FRA": 40886,
    "JPN": 33815,
    "BRA": 8918,
    "ZAF": 6766,
    "NGA": 2163,
    "AUS": 65100,
    "CAN": 55522,
    "SAU": 30436,
    "RUS": 15271,
}
_POP_2022: dict[str, int] = {
    "USA": 333_287_557,
    "CHN": 1_412_175_000,
    "IND": 1_417_173_173,
    "QAT": 2_695_122,
    "DEU": 83_797_985,
    "GBR": 66_971_395,
    "FRA": 68_042_591,
    "JPN": 125_124_989,
    "BRA": 215_313_498,
    "ZAF": 59_893_885,
    "NGA": 218_541_212,
    "AUS": 26_005_540,
    "CAN": 38_929_902,
    "SAU": 36_408_820,
    "RUS": 144_236_933,
}
_LIFE_2022: dict[str, float] = {
    "USA": 77.4,
    "CHN": 78.2,
    "IND": 67.7,
    "QAT": 79.3,
    "DEU": 80.7,
    "GBR": 80.9,
    "FRA": 82.3,
    "JPN": 84.0,
    "BRA": 72.8,
    "ZAF": 62.3,
    "NGA": 53.6,
    "AUS": 83.2,
    "CAN": 81.7,
    "SAU": 76.9,
    "RUS": 69.4,
}
_CO2_PC_2022: dict[str, float] = {
    "USA": 14.9,
    "CHN": 8.0,
    "IND": 2.0,
    "QAT": 37.6,
    "DEU": 8.0,
    "GBR": 4.7,
    "FRA": 4.6,
    "JPN": 8.5,
    "BRA": 2.3,
    "ZAF": 7.0,
    "NGA": 0.6,
    "AUS": 15.0,
    "CAN": 14.2,
    "SAU": 18.7,
    "RUS": 11.4,
}
_CO2_PC_2021: dict[str, float] = {k: round(v * 0.97, 2) for k, v in _CO2_PC_2022.items()}

_INDICATORS: tuple[tuple[str, str, str, str], ...] = (
    (
        "NY.GDP.PCAP.CD",
        "GDP per capita (current US$)",
        "US$",
        "Gross domestic product divided by midyear population.",
    ),
    ("SP.POP.TOTL", "Population, total", "people", "Total midyear population."),
    (
        "SP.DYN.LE00.IN",
        "Life expectancy at birth (years)",
        "years",
        "Years a newborn would live under current mortality.",
    ),
)


def _countries_table() -> TableRows:
    rows = tuple((iso, name, region, income) for iso, (name, region, income) in _COUNTRIES.items())
    return TableRows("countries", ("iso3", "name", "region", "income_group"), rows)


def _indicators_table() -> TableRows:
    return TableRows(
        "wdi_indicators", ("indicator_code", "name", "unit", "description"), _INDICATORS
    )


def _wdi_values_table() -> TableRows:
    rows: list[tuple[object, ...]] = []
    for iso in _COUNTRIES:
        rows.append((iso, "NY.GDP.PCAP.CD", 2022, float(_GDP_PC_2022[iso])))
        rows.append((iso, "SP.POP.TOTL", 2022, float(_POP_2022[iso])))
        rows.append((iso, "SP.DYN.LE00.IN", 2022, float(_LIFE_2022[iso])))
    return TableRows("wdi_values", ("country_iso3", "indicator_code", "year", "value"), tuple(rows))


def _owid_table() -> TableRows:
    rows: list[tuple[object, ...]] = []
    for iso in _COUNTRIES:
        for year, pc in ((2021, _CO2_PC_2021[iso]), (2022, _CO2_PC_2022[iso])):
            total_mt = round(pc * _POP_2022[iso] / 1_000_000, 3)
            share = round(total_mt / 375.0, 4)  # rough share of a ~37.5 Gt world
            rows.append((iso, year, total_mt, pc, share))
    return TableRows(
        "owid_co2",
        ("country_iso3", "year", "co2", "co2_per_capita", "share_global_co2"),
        tuple(rows),
    )


def seed_tables() -> tuple[TableRows, ...]:
    return (_countries_table(), _indicators_table(), _wdi_values_table(), _owid_table())


def seed_raw() -> RawDataset:
    tables = seed_tables()
    return RawDataset(
        dataset="seed",
        source="bundled-fixture",
        tables=tables,
        declared_checksum=compute_checksum(tables),
    )


# --- curated semantic layer ------------------------------------------------

_COUNTRIES_TABLE = SemanticTableDef(
    name="countries",
    description="Dimension of countries with region and World Bank income group.",
    columns=(
        SemanticColumnDef(
            "iso3",
            "char(3)",
            "ISO 3166-1 alpha-3 country code (primary key).",
            synonyms=("country code", "iso"),
        ),
        SemanticColumnDef("name", "text", "Country name.", synonyms=("country", "nation")),
        SemanticColumnDef("region", "text", "World Bank region."),
        SemanticColumnDef(
            "income_group", "text", "World Bank income classification.", synonyms=("income level",)
        ),
    ),
)
_WDI_INDICATORS_TABLE = SemanticTableDef(
    name="wdi_indicators",
    description="Catalog of World Development Indicators (code, name, unit).",
    columns=(
        SemanticColumnDef("indicator_code", "text", "WDI indicator code (primary key)."),
        SemanticColumnDef("name", "text", "Human-readable indicator name."),
        SemanticColumnDef("unit", "text", "Unit of measure."),
        SemanticColumnDef("description", "text", "What the indicator measures."),
    ),
)
_WDI_VALUES_TABLE = SemanticTableDef(
    name="wdi_values",
    description="Fact table of WDI indicator values by country and year.",
    columns=(
        SemanticColumnDef("country_iso3", "char(3)", "Country (FK to countries.iso3)."),
        SemanticColumnDef("indicator_code", "text", "Indicator (FK to wdi_indicators)."),
        SemanticColumnDef("year", "int", "Calendar year."),
        SemanticColumnDef(
            "value",
            "double",
            "Measured value; may be null for gaps.",
            synonyms=("amount", "figure"),
        ),
    ),
)
_OWID_TABLE = SemanticTableDef(
    name="owid_co2",
    description="Our World in Data CO2 emissions by country and year.",
    columns=(
        SemanticColumnDef("country_iso3", "char(3)", "Country (FK to countries.iso3)."),
        SemanticColumnDef("year", "int", "Calendar year."),
        SemanticColumnDef("co2", "double", "Annual CO2 emissions.", unit="million tonnes"),
        SemanticColumnDef(
            "co2_per_capita",
            "double",
            "CO2 emissions per person.",
            unit="tonnes per capita",
            synonyms=("emissions per capita", "per capita co2"),
        ),
        SemanticColumnDef(
            "share_global_co2", "double", "Share of global CO2 emissions.", unit="fraction"
        ),
    ),
)

_WDI_EXAMPLES = (
    ExampleDef(
        "Which 10 countries had the highest GDP per capita in 2022?",
        "SELECT c.name, v.value FROM wdi_values v JOIN countries c ON c.iso3 = v.country_iso3 "
        "WHERE v.indicator_code = 'NY.GDP.PCAP.CD' AND v.year = 2022 "
        "ORDER BY v.value DESC LIMIT 10",
        tags=("ranking", "join"),
    ),
    ExampleDef(
        "What is the average life expectancy by income group in 2022?",
        "SELECT c.income_group, AVG(v.value) AS avg_life FROM wdi_values v "
        "JOIN countries c ON c.iso3 = v.country_iso3 "
        "WHERE v.indicator_code = 'SP.DYN.LE00.IN' AND v.year = 2022 "
        "GROUP BY c.income_group ORDER BY avg_life DESC LIMIT 10",
        tags=("aggregate", "group_by"),
    ),
)
_OWID_EXAMPLES = (
    ExampleDef(
        "Which 10 countries had the highest CO2 per capita in 2022?",
        "SELECT c.name, o.co2_per_capita FROM owid_co2 o "
        "JOIN countries c ON c.iso3 = o.country_iso3 "
        "WHERE o.year = 2022 ORDER BY o.co2_per_capita DESC LIMIT 10",
        tags=("ranking", "join"),
    ),
    ExampleDef(
        "What was Germany's CO2 per capita in 2022?",
        "SELECT o.co2_per_capita FROM owid_co2 o "
        "WHERE o.country_iso3 = 'DEU' AND o.year = 2022 LIMIT 1",
        tags=("lookup", "filter"),
    ),
)

WDI_DEFINITION = DatasetDefinition(
    name="wdi",
    source="https://api.worldbank.org/v2",
    version="2022",
    description="World Bank World Development Indicators (curated subset).",
    tables=(_COUNTRIES_TABLE, _WDI_INDICATORS_TABLE, _WDI_VALUES_TABLE),
    examples=_WDI_EXAMPLES,
)
OWID_DEFINITION = DatasetDefinition(
    name="owid",
    source="https://github.com/owid/co2-data",
    version="2022",
    description="Our World in Data CO2 emissions (curated subset).",
    tables=(_COUNTRIES_TABLE, _OWID_TABLE),
    examples=_OWID_EXAMPLES,
)
SEED_DEFINITION = DatasetDefinition(
    name="seed",
    source="bundled-fixture",
    version="2022",
    description="Bundled seed slice covering WDI + OWID for keyless local dev.",
    tables=(_COUNTRIES_TABLE, _WDI_INDICATORS_TABLE, _WDI_VALUES_TABLE, _OWID_TABLE),
    examples=(*_WDI_EXAMPLES, *_OWID_EXAMPLES),
)

DEFINITIONS: dict[str, DatasetDefinition] = {
    "wdi": WDI_DEFINITION,
    "owid": OWID_DEFINITION,
    "seed": SEED_DEFINITION,
}


# --- scope, for the deterministic out-of-scope gate -------------------------


def seed_scope() -> DataScope:
    """What the seed slice actually contains, as a checkable value object.

    Derived from the same constants the loader uses, so the gate cannot claim a
    coverage the ingestion does not have. Years are the union of what the two
    sources carry: WDI is 2022 only, OWID is 2021-2022.
    """
    from ingestion.iso3166 import ALIASES, ISO_3166_NAMES

    loaded = {name.lower() for name, _, _ in _COUNTRIES.values()}
    # Colloquial forms of a loaded country count as loaded, so "USA" or
    # "the UK" is not mistaken for a country we do not carry.
    loaded |= {alias for alias, canonical in ALIASES.items() if canonical in loaded}

    return DataScope(
        country_names=frozenset(loaded),
        display_names=tuple(sorted(name for name, _, _ in _COUNTRIES.values())),
        country_codes=frozenset(code.lower() for code in _COUNTRIES),
        years=frozenset({2021, 2022}),
        indicator_labels=(
            "GDP per capita, population and life expectancy (World Bank, 2022)",
            "CO2 emissions total, per capita and share of global (Our World in Data, 2021-2022)",
        ),
        known_countries=ISO_3166_NAMES,
    )
