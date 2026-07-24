"""Generate-SQL node. Calls the LLM with the grounded prompt, then treats the
output as untrusted: it strips any markdown fences and validates that a single
non-empty statement came back before the guardrail even sees it (LLM05)."""

from __future__ import annotations

import re

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.application.prompts.sql_generation import SQL_GENERATION_VERSION, build_sql_messages
from app.domain.entities import LLMRequest, RetrievedContext
from app.domain.ports.llm import LLMProvider
from app.domain.ports.tracing import Tracer
from app.domain.results import LLMOutputError
from app.domain.value_objects import AgentStage, TaskKind

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


class GenerateSqlNode(BaseNode):
    name = "generate_sql"

    def __init__(self, tracer: Tracer, llm: LLMProvider) -> None:
        super().__init__(tracer)
        self._llm = llm

    async def _run(self, state: AgentState) -> NodeUpdate:
        retrieved = state.get("retrieved") or RetrievedContext()
        repair_error = state.get("error") if state.get("error_code") else None
        messages = build_sql_messages(state["question"], retrieved, repair_error=repair_error)
        response = await self._llm.complete(
            LLMRequest(
                messages=messages, task=TaskKind.SQL_GEN, prompt_version=SQL_GENERATION_VERSION
            )
        )
        sql = _extract_sql(response.text)
        prompt_versions = {
            **state.get("prompt_versions", {}),
            "sql_generation": SQL_GENERATION_VERSION,
        }
        return {
            "candidate_sql": sql,
            "provider_used": response.provider.value,
            "prompt_versions": prompt_versions,
            "stage": AgentStage.GENERATE_SQL.value,
        }

    def _validate_output(self, state: AgentState, update: NodeUpdate) -> None:
        sql = update.get("candidate_sql")
        if not isinstance(sql, str) or not sql.strip():
            raise LLMOutputError("candidate_sql", "model returned no SQL")


def _extract_sql(text: str) -> str:
    match = _FENCE.search(text)
    candidate = match.group(1) if match else text
    return candidate.strip().rstrip(";").strip()
