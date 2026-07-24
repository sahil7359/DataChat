"""Vega-Lite chart-spec builder and validator.

The backend emits a **declarative** Vega-Lite spec (data + encoding), never code —
the frontend is a thin renderer. That's the point for security: a chart can't be
an injection vector because it's validated JSON, not a script (LLM05/ASI05).

We build the spec ourselves from the executed result (so it can't be poisoned by
the model) and validate its shape before it leaves the process.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.entities import ExecutionResult
from app.domain.value_objects import ChartSpec

_SCHEMA_URL = "https://vega.github.io/schema/vega-lite/v5.json"
_MAX_POINTS = 50
_ALLOWED_MARKS = frozenset({"bar", "line", "point"})


def build_chart_spec(question: str, execution: ExecutionResult) -> ChartSpec | None:
    """Return a bar/line spec when the result looks chartable (a category column
    plus a numeric column), else None."""
    if execution.is_empty() or len(execution.columns) < 2:
        return None
    category, measure = execution.columns[0], execution.columns[1]
    values = [
        {category: row[0], measure: _as_number(row[1])}
        for row in execution.rows[:_MAX_POINTS]
        if _as_number(row[1]) is not None
    ]
    if not values:
        return None
    mark = "line" if _is_temporal(category) else "bar"
    spec: dict[str, object] = {
        "$schema": _SCHEMA_URL,
        "mark": mark,
        "data": {"values": values},
        "encoding": {
            "x": {"field": category, "type": "temporal" if mark == "line" else "nominal"},
            "y": {"field": measure, "type": "quantitative"},
        },
        "title": question[:120],
    }
    if not is_valid_chart_spec(spec):
        return None
    return ChartSpec(spec=spec)


def is_valid_chart_spec(spec: Mapping[str, object]) -> bool:
    """Structural validation of a Vega-Lite spec (the contract, not the full
    Vega-Lite schema): required keys, an allow-listed mark, and declarative data."""
    if spec.get("$schema") != _SCHEMA_URL:
        return False
    if spec.get("mark") not in _ALLOWED_MARKS:
        return False
    data = spec.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("values"), list):
        return False
    encoding = spec.get("encoding")
    return isinstance(encoding, dict) and "x" in encoding and "y" in encoding


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _is_temporal(column: str) -> bool:
    return column.lower() in {"year", "date", "month", "day"}
