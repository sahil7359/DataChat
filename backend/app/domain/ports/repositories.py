"""Persistence ports. The domain never sees SQLAlchemy — only these interfaces."""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import AgentAction, Conversation, Example, Turn
from app.domain.value_objects import ConversationId, DatasetId, RunId


class ConversationRepository(Protocol):
    async def get(self, cid: ConversationId) -> Conversation | None: ...

    async def create(self, conversation: Conversation) -> None: ...

    async def append_turn(self, cid: ConversationId, turn: Turn) -> None: ...


class RunRepository(Protocol):
    async def record_start(self, run_id: RunId, conversation_id: ConversationId) -> None: ...

    async def record_status(self, run_id: RunId, status: str, error: str | None = None) -> None: ...


class AgentActionRepository(Protocol):
    """Append-only audit outbox (never updated)."""

    async def append(self, action: AgentAction) -> None: ...

    async def for_run(self, run_id: RunId) -> tuple[AgentAction, ...]: ...


class ExampleRepository(Protocol):
    async def for_dataset(self, dataset_id: DatasetId) -> tuple[Example, ...]: ...


class EvalRepository(Protocol):
    async def record_run(
        self,
        git_sha: str,
        execution_accuracy: float,
        faithfulness: float,
        guardrail_pass_rate: float,
        mlflow_run_id: str | None,
    ) -> str: ...
