"""Web-fallback node: the honest escape hatch.

Only reached when a *valid* query returned no rows — the governed data has no
answer. It searches the web, summarises the snippets with the hardened web-answer
prompt, and records the sources. Web content never touches the SQL path; the
result is clearly a web-sourced answer, attributed to its sources.
"""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.application.prompts.web_answer import WEB_ANSWER_VERSION, build_web_answer_messages
from app.domain.entities import LLMRequest
from app.domain.ports.llm import LLMProvider
from app.domain.ports.tracing import Tracer
from app.domain.ports.web_search import WebSearchProvider
from app.domain.value_objects import AgentStage, TaskKind

_NO_RESULTS = (
    "I couldn't find this in the available datasets, and a web search didn't return "
    "anything usable either."
)


class WebFallbackNode(BaseNode):
    name = "web_fallback"

    def __init__(self, tracer: Tracer, llm: LLMProvider, search: WebSearchProvider) -> None:
        super().__init__(tracer)
        self._llm = llm
        self._search = search

    async def _run(self, state: AgentState) -> NodeUpdate:
        results = await self._search.search(state["question"])
        if not results:
            return {"explanation": _NO_RESULTS, "stage": AgentStage.WEB_FALLBACK.value}
        messages = build_web_answer_messages(state["question"], results)
        response = await self._llm.complete(
            LLMRequest(
                messages=messages, task=TaskKind.WEB_ANSWER, prompt_version=WEB_ANSWER_VERSION
            )
        )
        preamble = "This isn't in the available datasets, so here's a web summary:\n\n"
        prompt_versions = {**state.get("prompt_versions", {}), "web_answer": WEB_ANSWER_VERSION}
        return {
            "explanation": preamble + response.text.strip(),
            "web_sources": results,
            "prompt_versions": prompt_versions,
            "stage": AgentStage.WEB_FALLBACK.value,
        }
