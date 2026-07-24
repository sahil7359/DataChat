"""Respond node: the single terminal node. Marks the run done; the BFF reads the
final state to assemble the response."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.value_objects import AgentStage


class RespondNode(BaseNode):
    name = "respond"

    async def _run(self, state: AgentState) -> NodeUpdate:
        return {"stage": AgentStage.DONE.value}
