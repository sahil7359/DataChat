"""Execute node: runs the validated SQL on the read-only executor. Failure is a
``Result`` error, not a crash — it becomes state the verify/repair loop reacts to."""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.ports.sql import QueryExecutor
from app.domain.ports.tracing import Tracer
from app.domain.results import Err, Ok
from app.domain.value_objects import AgentStage


class ExecuteNode(BaseNode):
    name = "execute"

    def __init__(self, tracer: Tracer, executor: QueryExecutor) -> None:
        super().__init__(tracer)
        self._executor = executor

    async def _run(self, state: AgentState) -> NodeUpdate:
        validation = state.get("validation")
        sql = validation.sql if validation is not None else (state.get("candidate_sql") or "")
        result = await self._executor.execute(sql)
        match result:
            case Ok(execution):
                return {"execution": execution, "stage": AgentStage.EXECUTE.value}
            case Err(error):
                return {
                    "error": error.message,
                    "error_code": error.code,
                    "stage": AgentStage.EXECUTE.value,
                }
