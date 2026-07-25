"""Answer cache: reuse a whole prior answer when the *same* question comes back.

The slow part of a turn is the chain of LLM calls (understand → plan → generate →
verify → explain). Repeat questions are common on a shared demo, so we cache the
finished answer keyed by the *normalised* question and replay it on an exact hit —
skipping the graph entirely.

Deliberately exact-match, not fuzzy: for analytics, "top 5" vs "top 10" or "2022"
vs "2021" are near-identical as text yet need different answers, so a fuzzy match
would return a confidently-wrong result — strictly worse than a cache miss. Exact
normalisation (case/whitespace/trailing punctuation) has no such false hits.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from app.domain.entities import ExecutionResult, Plan
from app.domain.value_objects import ChartSpec

_WHITESPACE = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    """Case/whitespace-fold and drop trailing punctuation, nothing more."""
    collapsed = _WHITESPACE.sub(" ", question.strip().lower())
    return collapsed.rstrip("?!. ")


def answer_cache_key(question: str) -> str:
    digest = hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()
    return f"cache:answer:{digest}"


def report_cache_key(run_id: str) -> str:
    """Per-run key so a finished answer can be downloaded as a report/CSV later."""
    return f"report:{run_id}"


def serialize_answer(values: Mapping[str, Any]) -> bytes | None:
    """Encode a successful final state, or return None if it isn't cacheable.

    Only complete, error-free answers with a result set are stored; a failed or
    empty turn must never be pinned.
    """
    execution = values.get("execution")
    if execution is None or values.get("error_code"):
        return None
    plan = values.get("plan")
    chart = values.get("chart_spec")
    payload = {
        "question": values.get("question"),
        "plan": (
            {"steps": list(plan.steps), "target_tables": list(plan.target_tables)}
            if plan is not None
            else None
        ),
        "sql": values.get("candidate_sql"),
        "execution": {
            "columns": list(execution.columns),
            "rows": [list(row) for row in execution.rows],
            "row_count": execution.row_count,
            "elapsed_ms": execution.elapsed_ms,
            "truncated": execution.truncated,
        },
        "explanation": values.get("explanation"),
        "chart_spec": {"spec": dict(chart.spec)} if chart is not None else None,
    }
    return json.dumps(payload, default=str).encode("utf-8")


def deserialize_answer(raw: bytes) -> dict[str, Any]:
    """Rebuild a graph-style update dict so the normal event mapping can replay it."""
    data = json.loads(raw)
    update: dict[str, Any] = {}
    if data.get("plan") is not None:
        update["plan"] = Plan(
            steps=tuple(data["plan"]["steps"]),
            target_tables=tuple(data["plan"]["target_tables"]),
        )
    if data.get("sql"):
        update["candidate_sql"] = data["sql"]
    execution = data["execution"]
    update["execution"] = ExecutionResult(
        columns=tuple(execution["columns"]),
        rows=tuple(tuple(row) for row in execution["rows"]),
        row_count=execution["row_count"],
        elapsed_ms=execution["elapsed_ms"],
        truncated=execution["truncated"],
    )
    if data.get("explanation"):
        update["explanation"] = data["explanation"]
    if data.get("chart_spec") is not None:
        update["chart_spec"] = ChartSpec(spec=data["chart_spec"]["spec"])
    return update
