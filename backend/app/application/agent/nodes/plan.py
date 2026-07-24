"""Plan node: turns retrieved context into a small, explicit plan. Kept
deterministic in the MVP (target tables come from retrieval); richer planning can
be added without changing the graph shape."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.entities import Plan, RetrievedContext
from app.domain.value_objects import AgentStage


class PlanNode(BaseNode):
    name = "plan"

    async def _run(self, state: AgentState) -> NodeUpdate:
        retrieved = state.get("retrieved") or RetrievedContext()
        plan = Plan(
            steps=("retrieve schema", "generate SQL", "guardrail", "execute", "explain"),
            target_tables=tuple(t.table_name for t in retrieved.tables),
            needs_chart=_looks_like_ranking(state["question"]),
        )
        return {"plan": plan, "stage": AgentStage.PLAN.value}


def _looks_like_ranking(question: str) -> bool:
    q = question.lower()
    return any(word in q for word in ("top", "highest", "lowest", "rank", "most", "least", "by"))
