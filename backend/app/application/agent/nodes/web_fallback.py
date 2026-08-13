"""Web-fallback node: the honest escape hatch.

Only reached when a *valid* query returned no rows — the governed data has no
answer. It searches the web, extracts a small attributed table from the snippets,
summarises them with the hardened web-answer prompt, and records the sources.

Web content never touches the SQL path, and the table it produces is a
``WebTable``, not an ``ExecutionResult``, so nothing downstream can render it as
governed data. Two LLM calls, both on untrusted input, both versioned: one for the
table, one for the prose.

why extract a table at all: "no rows" is a dead end for the user, and a shaped
answer with per-row citations is more useful than a paragraph. The honesty comes
from provenance and from emitting nulls, not from pretending the data is verified.
alt: prose only (smaller attack surface, but the common case — "which countries
have X" — is inherently tabular and reads badly as a sentence).
"""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.application.prompts.web_answer import WEB_ANSWER_VERSION, build_web_answer_messages
from app.application.prompts.web_table import (
    WEB_TABLE_VERSION,
    build_web_table_messages,
    parse_web_table,
)
from app.domain.entities import LLMRequest, WebResult, WebTable
from app.domain.ports.llm import LLMProvider
from app.domain.ports.tracing import Tracer
from app.domain.ports.web_search import WebSearchProvider
from app.domain.value_objects import AgentStage, TaskKind

_NO_RESULTS = (
    "I couldn't find this in the available datasets, and a web search didn't return "
    "anything usable either."
)
_PREAMBLE = "This isn't in the available datasets, so here's a web summary:\n\n"


class WebFallbackNode(BaseNode):
    name = "web_fallback"

    def __init__(self, tracer: Tracer, llm: LLMProvider, search: WebSearchProvider) -> None:
        super().__init__(tracer)
        self._llm = llm
        self._search = search

    async def _run(self, state: AgentState) -> NodeUpdate:
        question = state["question"]
        results = await self._search.search(question)
        if not results:
            return {"explanation": _NO_RESULTS, "stage": AgentStage.WEB_FALLBACK.value}

        table = await self._extract_table(question, results)
        explanation = await self._summarise(question, results)

        versions = {
            **state.get("prompt_versions", {}),
            "web_answer": WEB_ANSWER_VERSION,
            "web_table": WEB_TABLE_VERSION,
        }
        update: NodeUpdate = {
            "explanation": _PREAMBLE + explanation,
            "web_sources": results,
            "prompt_versions": versions,
            "stage": AgentStage.WEB_FALLBACK.value,
        }
        if not table.is_empty():
            update["web_table"] = table
        return update

    async def _extract_table(self, question: str, results: tuple[WebResult, ...]) -> WebTable:
        response = await self._llm.complete(
            LLMRequest(
                messages=build_web_table_messages(question, results),
                task=TaskKind.WEB_TABLE,
                prompt_version=WEB_TABLE_VERSION,
            )
        )
        # The parser, not the prompt, is what enforces attribution: it drops any
        # row citing a source outside the ones we actually showed the model.
        return parse_web_table(response.text, source_count=len(results))

    async def _summarise(self, question: str, results: tuple[WebResult, ...]) -> str:
        response = await self._llm.complete(
            LLMRequest(
                messages=build_web_answer_messages(question, results),
                task=TaskKind.WEB_ANSWER,
                prompt_version=WEB_ANSWER_VERSION,
            )
        )
        return response.text.strip()
