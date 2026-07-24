"""HITL approve node: pauses before execution so a human can approve, edit, or
reject the exact SQL that will run.

The interrupt is server-side and durable (ASI09 — the approval cannot be bypassed
by the client, and the pause survives a reload or cold start). When approval is
not required, the node is a transparent pass-through.
"""

from __future__ import annotations

from collections.abc import Mapping

from langgraph.types import interrupt

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.value_objects import AgentStage, HITLDecision


class HitlApproveNode(BaseNode):
    name = "hitl_approve"

    async def _run(self, state: AgentState) -> NodeUpdate:
        if not state.get("approve_sql"):
            return {"hitl_decision": HITLDecision.APPROVE.value}

        validation = state.get("validation")
        sql = validation.sql if validation is not None else state.get("candidate_sql")
        decision = interrupt({"type": "approve", "run_id": state["run_id"], "sql": sql})
        choice, edited = _parse_decision(decision)
        update: NodeUpdate = {"hitl_decision": choice, "stage": AgentStage.AWAITING_APPROVAL.value}
        if choice == HITLDecision.EDIT.value and edited:
            update["candidate_sql"] = edited
            update["validation"] = None  # force a re-validation of the edited SQL
        elif choice == HITLDecision.REJECT.value:
            update["error"] = "Query cancelled by the user."
            update["error_code"] = "rejected"
        return update


def _parse_decision(decision: object) -> tuple[str, str | None]:
    if isinstance(decision, Mapping):
        choice = str(decision.get("decision", HITLDecision.REJECT.value))
        edited = decision.get("edited_sql")
        return choice, str(edited) if edited is not None else None
    return str(decision), None
