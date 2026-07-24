"""Explain node: grounded prose over the returned rows. MVP uses a single
completion; Phase 7 switches this to streamed deltas."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.application.prompts.explanation import EXPLANATION_VERSION, build_explanation_messages
from app.domain.entities import LLMRequest
from app.domain.ports.llm import LLMProvider
from app.domain.ports.tracing import Tracer
from app.domain.value_objects import AgentStage, TaskKind


class ExplainNode(BaseNode):
    name = "explain"

    def __init__(self, tracer: Tracer, llm: LLMProvider) -> None:
        super().__init__(tracer)
        self._llm = llm

    async def _run(self, state: AgentState) -> NodeUpdate:
        execution = state.get("execution")
        if execution is None:
            return {"stage": AgentStage.EXPLAIN.value}
        messages = build_explanation_messages(state["question"], execution)
        response = await self._llm.complete(
            LLMRequest(messages=messages, task=TaskKind.EXPLAIN, prompt_version=EXPLANATION_VERSION)
        )
        prompt_versions = {**state.get("prompt_versions", {}), "explanation": EXPLANATION_VERSION}
        return {
            "explanation": response.text.strip(),
            "prompt_versions": prompt_versions,
            "stage": AgentStage.EXPLAIN.value,
        }
