"""In-memory repository fakes."""

from __future__ import annotations

from app.domain.entities import AgentAction, Conversation, Example, Turn
from app.domain.value_objects import ConversationId, DatasetId, RunId, new_uuid


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self._store: dict[ConversationId, Conversation] = {}

    async def get(self, cid: ConversationId) -> Conversation | None:
        return self._store.get(cid)

    async def create(self, conversation: Conversation) -> None:
        self._store[conversation.id] = conversation

    async def append_turn(self, cid: ConversationId, turn: Turn) -> None:
        current = self._store[cid]
        self._store[cid] = Conversation(
            id=current.id,
            title=current.title,
            created_at=current.created_at,
            updated_at=turn.created_at,
            user_ref=current.user_ref,
            turns=(*current.turns, turn),
        )


class InMemoryRunRepository:
    def __init__(self) -> None:
        self.statuses: dict[RunId, str] = {}
        self.errors: dict[RunId, str] = {}

    async def record_start(self, run_id: RunId, conversation_id: ConversationId) -> None:
        self.statuses[run_id] = "running"

    async def record_status(self, run_id: RunId, status: str, error: str | None = None) -> None:
        self.statuses[run_id] = status
        if error is not None:
            self.errors[run_id] = error


class InMemoryAgentActionRepository:
    def __init__(self) -> None:
        self.actions: list[AgentAction] = []

    async def append(self, action: AgentAction) -> None:
        self.actions.append(action)

    async def for_run(self, run_id: RunId) -> tuple[AgentAction, ...]:
        return tuple(a for a in self.actions if a.run_id == run_id)


class InMemoryExampleRepository:
    def __init__(self, examples: tuple[Example, ...] = ()) -> None:
        self._examples = examples

    async def for_dataset(self, dataset_id: DatasetId) -> tuple[Example, ...]:
        return self._examples


class InMemoryEvalRepository:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []

    async def record_run(
        self,
        git_sha: str,
        execution_accuracy: float,
        faithfulness: float,
        guardrail_pass_rate: float,
        mlflow_run_id: str | None,
    ) -> str:
        run_id = new_uuid()
        self.runs.append(
            {
                "id": run_id,
                "git_sha": git_sha,
                "execution_accuracy": execution_accuracy,
                "faithfulness": faithfulness,
                "guardrail_pass_rate": guardrail_pass_rate,
                "mlflow_run_id": mlflow_run_id,
            }
        )
        return run_id
