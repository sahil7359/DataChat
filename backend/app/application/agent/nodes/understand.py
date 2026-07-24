"""Understand node. Runs a cheap ambiguity check; if the question is ambiguous it
interrupts to ask the user (HITL clarify, US3), otherwise it passes straight
through. The interrupt is durable — the run pauses and resumes from the
checkpoint after the user answers."""

from __future__ import annotations

from collections.abc import Mapping

from langgraph.types import interrupt

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.application.prompts.clarify import CLARIFY_VERSION, build_clarify_messages
from app.domain.entities import LLMRequest
from app.domain.ports.llm import LLMProvider
from app.domain.ports.tracing import Tracer
from app.domain.value_objects import AgentStage, TaskKind


class UnderstandNode(BaseNode):
    name = "understand"

    def __init__(self, tracer: Tracer, llm: LLMProvider) -> None:
        super().__init__(tracer)
        self._llm = llm

    async def _run(self, state: AgentState) -> NodeUpdate:
        if state.get("clarification"):
            return {"stage": AgentStage.UNDERSTAND.value}

        response = await self._llm.complete(
            LLMRequest(
                messages=build_clarify_messages(state["question"]),
                task=TaskKind.CLARIFY,
                prompt_version=CLARIFY_VERSION,
            )
        )
        text = response.text.strip()
        if text.upper().startswith("CLEAR") or "|" not in text:
            return {"stage": AgentStage.UNDERSTAND.value}

        options = [opt.strip() for opt in text.split("|") if opt.strip()]
        answer = interrupt({"type": "clarify", "run_id": state["run_id"], "options": options})
        chosen = _extract_answer(answer)
        return {
            "clarification": chosen,
            "question": f"{state['question']} (interpretation: {chosen})",
            "stage": AgentStage.UNDERSTAND.value,
        }


def _extract_answer(answer: object) -> str:
    if isinstance(answer, Mapping):
        return str(answer.get("clarification", answer.get("choice", "")))
    return str(answer)
