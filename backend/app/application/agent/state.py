"""LangGraph agent state.

A ``TypedDict`` (total=False) so each node returns a partial update that LangGraph
merges. Domain entities are stored directly — they're frozen dataclasses, so the
state is immutable-by-parts and serialises cleanly for the checkpointer.
"""

from __future__ import annotations

from typing import TypedDict

from app.domain.entities import (
    ExecutionResult,
    Plan,
    RetrievedContext,
    ValidationResult,
    VerificationResult,
    WebResult,
    WebTable,
)
from app.domain.value_objects import ChartSpec


class AgentState(TypedDict, total=False):
    conversation_id: str
    run_id: str
    question: str

    retrieved: RetrievedContext | None
    plan: Plan | None
    candidate_sql: str | None
    validation: ValidationResult | None
    execution: ExecutionResult | None
    verification: VerificationResult | None
    explanation: str | None
    chart_spec: ChartSpec | None
    web_sources: tuple[WebResult, ...] | None
    # Kept separate from `execution` on purpose: web-derived rows must never be
    # mistaken for guardrailed SQL output. See entities.WebTable.
    web_table: WebTable | None

    # HITL
    approve_sql: bool
    hitl_decision: str | None
    edited_sql: str | None
    clarification: str | None

    error: str | None
    error_code: str | None
    stage: str
    repair_attempts: int

    provider_used: str | None
    prompt_versions: dict[str, str]
