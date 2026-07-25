"""QueryService — the use-case facade for a chat turn.

Owns the compiled agent graph and exposes three entry points:
- ``run`` — invoke to completion, return the final state (used by tests/eval).
- ``stream`` — drive the graph and yield SSE events step by step (FR-12).
- ``resume`` — continue a HITL-interrupted run from its durable checkpoint (FR-13).

The graph decides *what* happens; this class only translates graph updates into
the documented event set and maps internal errors to safe user messages.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command

from app.application.agent.events import (
    AgentEvent,
    AwaitingApprovalEvent,
    ChartSpecEvent,
    DoneEvent,
    ErrorEvent,
    ExplanationDeltaEvent,
    PlanEvent,
    RowsEvent,
    SqlEvent,
    StatusEvent,
)
from app.application.agent.state import AgentState
from app.application.services.answer_cache import (
    answer_cache_key,
    deserialize_answer,
    serialize_answer,
)
from app.domain.entities import Conversation
from app.domain.ports.cache import Cache
from app.domain.ports.repositories import ConversationRepository, RunRepository
from app.domain.value_objects import AgentStage, ConversationId, RunId, new_uuid

_SAFE_MESSAGES = {
    "guardrail_blocked": "I couldn't produce a safe query for that question.",
    "rejected": "The query was cancelled.",
    "57014": "That query took too long to run — try narrowing it.",
    "providers_unavailable": "The service is busy right now — please try again shortly.",
}
_DEFAULT_ERROR = "Something went wrong while answering that question."


class QueryService:
    def __init__(
        self,
        graph: Any,
        *,
        conversations: ConversationRepository | None = None,
        runs: RunRepository | None = None,
        answer_cache: Cache | None = None,
        answer_cache_ttl_s: int = 3600,
    ) -> None:
        self._graph = graph
        # Optional run/conversation persistence. When wired, a run row is recorded
        # before the graph executes so the audit outbox (which FKs to runs) has a
        # parent to reference; the final status is written back afterwards.
        self._conversations = conversations
        self._runs = runs
        # Optional whole-answer cache: replays a prior answer for the same question
        # instead of re-running the LLM chain.
        self._answer_cache = answer_cache
        self._answer_cache_ttl = answer_cache_ttl_s

    async def run(self, question: str, conversation_id: str | None = None) -> AgentState:
        run_id = new_uuid()
        config = {"configurable": {"thread_id": run_id}}
        result: AgentState = await self._graph.ainvoke(
            _initial_state(question, conversation_id, run_id), config=config
        )
        return result

    async def stream(
        self,
        question: str,
        conversation_id: str | None = None,
        *,
        approve_sql: bool = False,
        run_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        run_id = run_id or new_uuid()
        cid = conversation_id or new_uuid()
        config = {"configurable": {"thread_id": run_id}}
        key = answer_cache_key(question)
        # A prior answer to the same question replays instantly. Skip the cache for
        # the HITL approval flow, which must actually run the graph to interrupt.
        if self._answer_cache is not None and not approve_sql:
            cached = await self._answer_cache.get(key)
            if cached is not None:
                async for event in self._replay_cached(
                    run_id, cid, conversation_id, question, cached
                ):
                    yield event
                return
        await self._begin_run(run_id, cid, conversation_id, question)
        initial = _initial_state(question, cid, run_id, approve_sql=approve_sql)
        try:
            async for event in self._drive(
                self._graph.astream(initial, config=config, stream_mode="updates"), run_id, config
            ):
                yield event
            await self._store_answer(key, config)
        finally:
            await self._finish_run(run_id, config)

    async def resume(
        self, run_id: str, decision: Mapping[str, object]
    ) -> AsyncIterator[AgentEvent]:
        config = {"configurable": {"thread_id": run_id}}
        try:
            async for event in self._drive(
                self._graph.astream(Command(resume=decision), config=config, stream_mode="updates"),
                run_id,
                config,
            ):
                yield event
        finally:
            await self._finish_run(run_id, config)

    async def _drive(
        self, stream: AsyncIterator[dict[str, Any]], run_id: str, config: dict[str, Any]
    ) -> AsyncIterator[AgentEvent]:
        interrupted = False
        async for chunk in stream:
            for node, update in chunk.items():
                if node == "__interrupt__":
                    interrupted = True
                    yield _interrupt_event(update, run_id)
                    continue
                for event in _events_for(update):
                    yield event
        if not interrupted:
            # aget_state, not get_state: the durable checkpointer is async, and its
            # synchronous accessor raises when called from the running event loop.
            snapshot = await self._graph.aget_state(config)
            for event in _final_events(snapshot.values, run_id):
                yield event

    async def _replay_cached(
        self, run_id: str, cid: str, provided_cid: str | None, question: str, cached: bytes
    ) -> AsyncIterator[AgentEvent]:
        # Still record the run/conversation so history and the audit dashboard stay
        # consistent, then replay the stored answer through the normal event mapping.
        await self._begin_run(run_id, cid, provided_cid, question)
        for event in _events_for(deserialize_answer(cached)):
            yield event
        yield StatusEvent(stage=AgentStage.DONE.value)
        yield DoneEvent(run_id=run_id)
        if self._runs is not None:
            with suppress(Exception):
                await self._runs.record_status(RunId(run_id), "done")

    async def _store_answer(self, key: str, config: dict[str, Any]) -> None:
        if self._answer_cache is None:
            return
        with suppress(Exception):
            snapshot = await self._graph.aget_state(config)
            if snapshot.next:  # paused at a HITL interrupt — nothing final to cache
                return
            payload = serialize_answer(snapshot.values)
            if payload is not None:
                await self._answer_cache.set(key, payload, self._answer_cache_ttl)

    async def _begin_run(
        self, run_id: str, cid: str, provided_cid: str | None, question: str
    ) -> None:
        if self._runs is None or self._conversations is None:
            return
        # A run belongs to a conversation (FK): create it for a fresh chat, or when a
        # client-supplied id doesn't exist yet. record_start must land before any node
        # writes an audit row.
        if provided_cid is None or await self._conversations.get(ConversationId(cid)) is None:
            now = datetime.now(UTC)
            await self._conversations.create(
                Conversation(
                    id=ConversationId(cid), title=_title(question), created_at=now, updated_at=now
                )
            )
        await self._runs.record_start(RunId(run_id), ConversationId(cid))

    async def _finish_run(self, run_id: str, config: dict[str, Any]) -> None:
        # Best-effort bookkeeping: never fail the user's answer over a status write.
        if self._runs is None:
            return
        with suppress(Exception):
            snapshot = await self._graph.aget_state(config)
            if snapshot.next:  # paused at a HITL interrupt — not a terminal state
                return
            values = snapshot.values
            error = values.get("error")
            status = "error" if values.get("error_code") else "done"
            await self._runs.record_status(
                RunId(run_id), status, error if isinstance(error, str) else None
            )


def _initial_state(
    question: str, conversation_id: str | None, run_id: str, *, approve_sql: bool = False
) -> AgentState:
    return {
        "conversation_id": conversation_id or new_uuid(),
        "run_id": run_id,
        "question": question,
        "approve_sql": approve_sql,
        "repair_attempts": 0,
        "prompt_versions": {},
    }


def _events_for(update: Mapping[str, Any]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    if "stage" in update:
        events.append(StatusEvent(stage=str(update["stage"])))
    plan = update.get("plan")
    if plan is not None:
        events.append(PlanEvent(steps=plan.steps, target_tables=plan.target_tables))
    sql = update.get("candidate_sql")
    if sql:
        events.append(SqlEvent(sql=str(sql)))
    execution = update.get("execution")
    if execution is not None:
        events.append(
            RowsEvent(
                columns=execution.columns,
                rows=execution.rows,
                row_count=execution.row_count,
                truncated=execution.truncated,
            )
        )
    explanation = update.get("explanation")
    if explanation:
        events.append(ExplanationDeltaEvent(text=str(explanation)))
    chart = update.get("chart_spec")
    if chart is not None:
        events.append(ChartSpecEvent(spec=chart.spec))
    return events


def _interrupt_event(update: object, run_id: str) -> AwaitingApprovalEvent:
    payload = _interrupt_payload(update)
    return AwaitingApprovalEvent(
        run_id=run_id,
        kind=str(payload.get("type", "approve")),
        sql=_opt_str(payload.get("sql")),
        options=tuple(payload.get("options", ()) or ()),
    )


def _interrupt_payload(update: object) -> Mapping[str, Any]:
    item = update[0] if isinstance(update, list | tuple) and update else update
    value = getattr(item, "value", item)
    return value if isinstance(value, Mapping) else {}


def _final_events(state: Mapping[str, Any], run_id: str) -> list[AgentEvent]:
    error_code = state.get("error_code")
    if error_code:
        message = _SAFE_MESSAGES.get(str(error_code), _DEFAULT_ERROR)
        return [ErrorEvent(code=str(error_code), message=message), DoneEvent(run_id=run_id)]
    return [DoneEvent(run_id=run_id)]


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _title(question: str) -> str:
    # A short, human-readable conversation title derived from the first question.
    trimmed = question.strip()
    return (trimmed[:77] + "...") if len(trimmed) > 80 else (trimmed or "Untitled")
