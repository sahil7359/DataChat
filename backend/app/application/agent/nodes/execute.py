"""Execute node: runs the validated SQL on the read-only executor. Failure is a
``Result`` error, not a crash — it becomes state the verify/repair loop reacts to."""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.entities import AgentAction
from app.domain.ports.repositories import AgentActionRepository
from app.domain.ports.sql import QueryExecutor
from app.domain.ports.tracing import Tracer
from app.domain.results import Err, Ok
from app.domain.value_objects import ActionType, AgentStage, RunId, new_uuid


class ExecuteNode(BaseNode):
    name = "execute"

    def __init__(
        self, tracer: Tracer, executor: QueryExecutor, audit: AgentActionRepository | None = None
    ) -> None:
        super().__init__(tracer)
        self._executor = executor
        self._audit = audit

    async def _run(self, state: AgentState) -> NodeUpdate:
        validation = state.get("validation")
        sql = validation.sql if validation is not None else (state.get("candidate_sql") or "")
        result = await self._executor.execute(sql)
        match result:
            case Ok(execution):
                await self._record(state, sql, execution.row_count, execution.elapsed_ms, None)
                return {"execution": execution, "stage": AgentStage.EXECUTE.value}
            case Err(error):
                await self._record(state, sql, None, None, error.message)
                return {
                    "error": error.message,
                    "error_code": error.code,
                    "stage": AgentStage.EXECUTE.value,
                }

    async def _record(
        self, state: AgentState, sql: str, rows: int | None, elapsed: int | None, error: str | None
    ) -> None:
        # Append-only audit outbox (ASI10): every SQL the agent ran is logged.
        if self._audit is None:
            return
        await self._audit.append(
            AgentAction(
                id=new_uuid(),
                run_id=RunId(state.get("run_id", "")),
                action_type=ActionType.EXECUTE,
                created_at=datetime.now(UTC),
                sql_text=sql,
                row_count=rows,
                elapsed_ms=elapsed,
                error=error,
            )
        )
