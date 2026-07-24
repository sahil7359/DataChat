"""Understand node. In the MVP it just marks the stage; ambiguity/clarify
handling arrives in Phase 7."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.value_objects import AgentStage


class UnderstandNode(BaseNode):
    name = "understand"

    async def _run(self, state: AgentState) -> NodeUpdate:
        return {"stage": AgentStage.UNDERSTAND.value}
