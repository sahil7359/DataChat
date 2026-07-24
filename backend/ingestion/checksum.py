"""Canonical checksum of normalized dataset rows.

Used both to pin the seed fixture's integrity and to detect drift on re-ingest.
The serialization is order-stable so the same data always hashes the same way.
"""

from __future__ import annotations

import hashlib
import json

from ingestion.ports import RawDataset, TableRows


def _table_blob(table: TableRows) -> list[object]:
    ordered_rows = sorted((list(map(_norm, row)) for row in table.rows), key=repr)
    return [table.name, list(table.columns), ordered_rows]


def _norm(value: object) -> object:
    # JSON can't hold every python type; normalize to a stable string form.
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def compute_checksum(tables: tuple[TableRows, ...]) -> str:
    blob = sorted((_table_blob(t) for t in tables), key=repr)
    canonical = json.dumps(blob, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def checksum_of(raw: RawDataset) -> str:
    return compute_checksum(raw.tables)
