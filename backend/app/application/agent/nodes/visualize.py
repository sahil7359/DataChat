"""Visualize node: emits a validated Vega-Lite chart spec when the result is
chartable. The spec is built from the executed rows and validated before it
enters state — declarative JSON, never code (LLM05/ASI05)."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.charts import build_chart_spec, is_valid_chart_spec
from app.application.agent.state import AgentState
from app.domain.value_objects import AgentStage, ChartSpec


class VisualizeNode(BaseNode):
    name = "visualize"

    async def _run(self, state: AgentState) -> NodeUpdate:
        execution = state.get("execution")
        if execution is None:
            return {"stage": AgentStage.VISUALIZE.value}
        spec = build_chart_spec(state["question"], execution)
        return {"chart_spec": spec, "stage": AgentStage.VISUALIZE.value}

    def _validate_output(self, state: AgentState, update: NodeUpdate) -> None:
        spec = update.get("chart_spec")
        if isinstance(spec, ChartSpec) and not is_valid_chart_spec(spec.spec):
            update["chart_spec"] = None  # drop anything that fails the contract
