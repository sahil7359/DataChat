"""The report/CSV builders turn a cached answer payload into downloads."""

from __future__ import annotations

import csv
import io

from app.application.services.report import build_csv, build_markdown_report

COLUMNS = ["name", "population"]
ROWS: list[list[object]] = [["India", 1417173173], ["China", 1412360000]]
PAYLOAD = {
    "question": "Top 3 countries by population in 2022",
    "sql": "SELECT c.name FROM wdi_values v JOIN countries c ON c.iso3 = v.country_iso3",
    "explanation": "India, China and the US were the most populous.",
    "plan": {"steps": ["generate", "execute"], "target_tables": ["wdi_values", "countries"]},
    "execution": {
        "columns": COLUMNS,
        "rows": ROWS,
        "row_count": 2,
        "elapsed_ms": 5,
        "truncated": False,
    },
}


def test_csv_round_trips_with_header_and_rows() -> None:
    body = build_csv(COLUMNS, ROWS)
    parsed = list(csv.reader(io.StringIO(body)))
    assert parsed[0] == ["name", "population"]
    assert parsed[1] == ["India", "1417173173"]
    assert len(parsed) == 3


def test_csv_quotes_values_containing_separators() -> None:
    body = build_csv(["label"], [["Congo, Dem. Rep."]])
    parsed = list(csv.reader(io.StringIO(body)))
    assert parsed[1] == ["Congo, Dem. Rep."]  # comma survived quoting


def test_markdown_report_has_summary_sql_data_and_sources() -> None:
    provenance = [
        ("wdi_values", "wdi", "https://data.worldbank.org"),
        ("countries", "wdi", "https://data.worldbank.org"),
    ]
    md = build_markdown_report(PAYLOAD, provenance)
    assert "# Top 3 countries by population in 2022" in md
    assert "India, China and the US" in md
    assert "```sql" in md
    assert "| name | population |" in md
    assert "| India | 1417173173 |" in md
    # Sources are de-duplicated by dataset name (both tables belong to "wdi").
    assert md.count("**wdi**") == 1


def test_markdown_report_handles_empty_result() -> None:
    payload = {**PAYLOAD, "execution": {"columns": [], "rows": [], "row_count": 0}}
    md = build_markdown_report(payload, [])
    assert "_No rows returned._" in md
