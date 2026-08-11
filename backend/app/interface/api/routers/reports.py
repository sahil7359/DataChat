"""Downloadable report + CSV for a finished run.

The answer for a run is stashed in the cache under ``report:{run_id}`` when it is
produced (or replayed from the answer cache). These endpoints render it as a
Markdown report or a CSV of the result set, with links back to the source datasets.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import sqlglot
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlglot import exp

from app.application.services.answer_cache import report_cache_key
from app.application.services.report import (
    build_csv,
    build_markdown_report,
    build_web_markdown_report,
)
from app.domain.entities import WebTable, WebTableRow
from app.domain.ports.cache import Cache
from app.interface.deps import get_cache
from ingestion.definitions import DEFINITIONS

router = APIRouter(tags=["reports"])


async def _load(run_id: str, cache: Cache) -> dict[str, Any]:
    raw = await cache.get(report_cache_key(run_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="report_not_found")
    payload: dict[str, Any] = json.loads(raw)
    return payload


def _tables_in_sql(sql: str) -> set[str]:
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return set()
    return {t.name.lower() for t in parsed.find_all(exp.Table)}


def _provenance(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Credit each source dataset for the tables the query actually touched.

    Tables come from the executed SQL (the plan's target list over-includes
    retrieval candidates). The bundled ``seed`` fixture is skipped, and shared
    dimension tables (e.g. ``countries`` lives in several datasets) are ignored so
    provenance points only at the dataset a table is distinctive to.
    """
    targets = _tables_in_sql(payload.get("sql") or "")
    real = [d for d in DEFINITIONS.values() if d.name != "seed"]
    owners = Counter(table.name for dataset in real for table in dataset.tables)
    return [
        (table.name, dataset.name, dataset.source)
        for dataset in real
        for table in dataset.tables
        if table.name in targets and owners[table.name] == 1
    ]


def _download(body: str, media_type: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _web_table(payload: dict[str, Any]) -> WebTable | None:
    """Rebuild the WebTable from a stored web payload, or None if this run was a
    normal governed answer."""
    if payload.get("kind") != "web":
        return None
    table = payload.get("web_table") or {}
    columns = tuple(table.get("columns") or ())
    if not columns:
        return None
    rows = tuple(
        WebTableRow(values=tuple(r.get("values") or ()), source_index=int(r.get("source", 0)))
        for r in table.get("rows") or []
    )
    return WebTable(columns=columns, rows=rows, caveat=str(table.get("caveat") or ""))


@router.get("/runs/{run_id}/report.md")
async def report_markdown(
    run_id: str, request: Request, cache: Cache = Depends(get_cache)
) -> Response:
    payload = await _load(run_id, cache)
    table = _web_table(payload)
    if table is not None:
        # Different document entirely: no SQL section, provenance warning, and a
        # per-row citation column. See report.build_web_markdown_report.
        body = build_web_markdown_report(
            str(payload.get("question") or "DataChat report"),
            table,
            str(payload.get("explanation") or ""),
            [(s.get("title", ""), s.get("url", "")) for s in payload.get("web_sources") or []],
        )
    else:
        body = build_markdown_report(payload, _provenance(payload))
    return _download(body, "text/markdown; charset=utf-8", f"datachat-{run_id}.md")


@router.get("/runs/{run_id}/data.csv")
async def report_csv(run_id: str, request: Request, cache: Cache = Depends(get_cache)) -> Response:
    payload = await _load(run_id, cache)
    table = _web_table(payload)
    if table is not None:
        # The source column travels with the data: a CSV that leaves the app
        # without provenance is exactly how a scrape gets mistaken for a dataset.
        columns = [*table.columns, "source_url"]
        sources = payload.get("web_sources") or []
        rows = [
            [
                *row.values,
                sources[row.source_index - 1].get("url", "")
                if 1 <= row.source_index <= len(sources)
                else "",
            ]
            for row in table.rows
        ]
        body = build_csv(columns, rows)
    else:
        execution = payload.get("execution") or {}
        body = build_csv(execution.get("columns", []), execution.get("rows", []))
    return _download(body, "text/csv; charset=utf-8", f"datachat-{run_id}.csv")
