"""Repair node: increments the bounded attempt counter and hands control back to
generation with the failure as feedback. The hard cap lives in the routing (see
graph.py) so this loop can never run away (ASI08 cascading failures)."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.value_objects import AgentStage


class RepairNode(BaseNode):
    name = "repair"

    async def _run(self, state: AgentState) -> NodeUpdate:
        attempts = state.get("repair_attempts", 0) + 1
        return {"repair_attempts": attempts, "stage": AgentStage.REPAIR.value}
