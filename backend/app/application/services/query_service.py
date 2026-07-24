"""QueryService — the use-case facade for a chat turn.

Owns the compiled agent graph and turns a question into a final ``AgentState``.
The BFF (Phase 8) reads that state to shape the API response. Streaming and HITL
resume are layered on in Phase 7.
"""

from __future__ import annotations

from typing import Any

from app.application.agent.state import AgentState
from app.domain.value_objects import new_uuid


class QueryService:
    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def run(self, question: str, conversation_id: str | None = None) -> AgentState:
        conversation_id = conversation_id or new_uuid()
        run_id = new_uuid()
        initial: AgentState = {
            "conversation_id": conversation_id,
            "run_id": run_id,
            "question": question,
            "repair_attempts": 0,
            "prompt_versions": {},
        }
        config = {"configurable": {"thread_id": run_id}}
        result: AgentState = await self._graph.ainvoke(initial, config=config)
        return result
