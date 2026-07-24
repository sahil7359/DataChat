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
from app.domain.value_objects import new_uuid

_SAFE_MESSAGES = {
    "guardrail_blocked": "I couldn't produce a safe query for that question.",
    "rejected": "The query was cancelled.",
    "57014": "That query took too long to run — try narrowing it.",
    "providers_unavailable": "The service is busy right now — please try again shortly.",
}
_DEFAULT_ERROR = "Something went wrong while answering that question."


class QueryService:
    def __init__(self, graph: Any) -> None:
        self._graph = graph

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
    ) -> AsyncIterator[AgentEvent]:
        run_id = new_uuid()
        config = {"configurable": {"thread_id": run_id}}
        initial = _initial_state(question, conversation_id, run_id, approve_sql=approve_sql)
        async for event in self._drive(
            self._graph.astream(initial, config=config, stream_mode="updates"), run_id, config
        ):
            yield event

    async def resume(
        self, run_id: str, decision: Mapping[str, object]
    ) -> AsyncIterator[AgentEvent]:
        config = {"configurable": {"thread_id": run_id}}
        async for event in self._drive(
            self._graph.astream(Command(resume=decision), config=config, stream_mode="updates"),
            run_id,
            config,
        ):
            yield event

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
            for event in _final_events(self._graph.get_state(config).values, run_id):
                yield event


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
