"""Guardrail node: the mandatory validation gate. Nothing reaches the executor
without passing here. On failure the MVP produces a safe refusal; the repair loop
(Phase 7) will instead route back to regenerate within a bounded budget."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.ports.sql import SqlValidator
from app.domain.ports.tracing import Tracer
from app.domain.value_objects import AgentStage


class GuardrailNode(BaseNode):
    name = "guardrail"

    def __init__(self, tracer: Tracer, validator: SqlValidator) -> None:
        super().__init__(tracer)
        self._validator = validator

    async def _run(self, state: AgentState) -> NodeUpdate:
        sql = state.get("candidate_sql") or ""
        validation = self._validator.validate(sql)
        update: NodeUpdate = {"validation": validation, "stage": AgentStage.GUARDRAIL.value}
        if not validation.ok:
            violation = validation.first_violation
            # The technical reason drives the repair prompt and the audit log; the
            # BFF maps error_code to a safe user-facing message.
            update["error"] = violation.reason if violation and violation.reason else "unsafe SQL"
            update["error_code"] = "guardrail_blocked"
        return update
