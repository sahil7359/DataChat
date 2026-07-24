"""Retrieve-context node: RAG grounding via the semantic catalog."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.ports.catalog import SchemaCatalog
from app.domain.ports.tracing import Tracer
from app.domain.value_objects import AgentStage


class RetrieveContextNode(BaseNode):
    name = "retrieve"

    def __init__(self, tracer: Tracer, catalog: SchemaCatalog, *, k: int = 8) -> None:
        super().__init__(tracer)
        self._catalog = catalog
        self._k = k

    async def _run(self, state: AgentState) -> NodeUpdate:
        retrieved = await self._catalog.retrieve(state["question"], self._k)
        return {"retrieved": retrieved, "stage": AgentStage.RETRIEVE.value}
