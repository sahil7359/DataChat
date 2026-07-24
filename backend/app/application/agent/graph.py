"""GraphBuilder — assembles the LangGraph StateGraph step by step (Builder).

The graph is the MVP happy path with two safety branches: a guardrail failure
routes straight to a safe response (never execute), and an execution error routes
to respond (the bounded repair loop is added in Phase 7). The checkpointer is
injected, so tests use an in-memory saver and prod uses the Postgres saver —
durable state across cold starts (NFR-3).
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.application.agent.node_factory import NodeFactory
from app.application.agent.state import AgentState

_NODES = (
    "understand",
    "retrieve",
    "plan",
    "generate_sql",
    "guardrail",
    "execute",
    "explain",
    "respond",
)


def _route_after_guardrail(state: AgentState) -> str:
    validation = state.get("validation")
    return "execute" if validation is not None and validation.ok else "respond"


def _route_after_execute(state: AgentState) -> str:
    return "respond" if state.get("error") else "explain"


class GraphBuilder:
    def __init__(self, factory: NodeFactory) -> None:
        self._factory = factory

    def build(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> Any:
        graph = StateGraph(AgentState)
        for name in _NODES:
            graph.add_node(name, self._factory.build(name))

        graph.add_edge(START, "understand")
        graph.add_edge("understand", "retrieve")
        graph.add_edge("retrieve", "plan")
        graph.add_edge("plan", "generate_sql")
        graph.add_edge("generate_sql", "guardrail")
        graph.add_conditional_edges(
            "guardrail", _route_after_guardrail, {"execute": "execute", "respond": "respond"}
        )
        graph.add_conditional_edges(
            "execute", _route_after_execute, {"explain": "explain", "respond": "respond"}
        )
        graph.add_edge("explain", "respond")
        graph.add_edge("respond", END)
        return graph.compile(checkpointer=checkpointer)
