"""GraphBuilder — assembles the v1 LangGraph StateGraph (Builder).

The full agent: plan → generate → guardrail → (human approve) → execute → verify →
(bounded repair) → explain → visualize → respond. Safety is in the routing:
nothing executes without passing the guardrail, the human approval is a durable
server-side interrupt, and the repair loop is hard-capped so it can never run away
(ASI08). The checkpointer is injected (MemorySaver in tests, PostgresSaver in
prod) for durable state across cold starts (NFR-3).
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.application.agent.node_factory import NodeFactory
from app.application.agent.state import AgentState
from app.domain.value_objects import HITLDecision

_NODES = (
    "understand",
    "retrieve",
    "plan",
    "generate_sql",
    "guardrail",
    "hitl_approve",
    "execute",
    "verify",
    "repair",
    "explain",
    "visualize",
    "respond",
)


class GraphBuilder:
    def __init__(self, factory: NodeFactory, *, max_repair_attempts: int = 2) -> None:
        self._factory = factory
        self._max_repair = max_repair_attempts

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
            "guardrail",
            self._route_after_guardrail,
            {
                "hitl_approve": "hitl_approve",
                "execute": "execute",
                "repair": "repair",
                "respond": "respond",
            },
        )
        graph.add_conditional_edges(
            "hitl_approve",
            _route_after_hitl,
            {"execute": "execute", "guardrail": "guardrail", "respond": "respond"},
        )
        graph.add_edge("execute", "verify")
        graph.add_conditional_edges(
            "verify",
            self._route_after_verify,
            {"repair": "repair", "explain": "explain", "respond": "respond"},
        )
        graph.add_edge("repair", "generate_sql")
        graph.add_edge("explain", "visualize")
        graph.add_edge("visualize", "respond")
        graph.add_edge("respond", END)
        return graph.compile(checkpointer=checkpointer)

    def _route_after_guardrail(self, state: AgentState) -> str:
        validation = state.get("validation")
        if validation is not None and validation.ok:
            # A user edit is itself an approval of the edited SQL — re-validate
            # (done) then run it, rather than asking for approval again.
            if state.get("hitl_decision") == HITLDecision.EDIT.value:
                return "execute"
            return "hitl_approve"
        return "repair" if _has_budget(state, self._max_repair) else "respond"

    def _route_after_verify(self, state: AgentState) -> str:
        verification = state.get("verification")
        needs_repair = state.get("error") is not None or (
            verification is not None and not verification.plausible
        )
        if needs_repair and _has_budget(state, self._max_repair):
            return "repair"
        if state.get("error") is not None:
            return "respond"
        return "explain"


def _route_after_hitl(state: AgentState) -> str:
    decision = state.get("hitl_decision")
    if decision == HITLDecision.EDIT.value:
        return "guardrail"
    if decision == HITLDecision.REJECT.value:
        return "respond"
    return "execute"


def _has_budget(state: AgentState, max_repair: int) -> bool:
    return state.get("repair_attempts", 0) < max_repair
