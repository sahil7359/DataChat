"""Verify node: a plausibility check on the result before we explain it.

Cheap checks for the MVP dataset: did the query error, and did it return any
rows? An implausible/empty result (with budget left) routes into the repair loop
instead of confidently explaining nothing (guards against LLM09 misinformation)."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.entities import VerificationResult
from app.domain.value_objects import AgentStage


class VerifyNode(BaseNode):
    name = "verify"

    async def _run(self, state: AgentState) -> NodeUpdate:
        execution = state.get("execution")
        if execution is None:
            return {
                "verification": VerificationResult(ok=False, plausible=False, reason="no result"),
                "stage": AgentStage.VERIFY.value,
            }
        plausible = not execution.is_empty()
        return {
            "verification": VerificationResult(
                ok=True,
                plausible=plausible,
                reason=None if plausible else "query returned no rows",
            ),
            "stage": AgentStage.VERIFY.value,
        }
