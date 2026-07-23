"""Repository adapters (Repository pattern) implementing the domain ports.

Persistence lives entirely behind these classes; the domain sees only its own
entities, never a SQLAlchemy row. Each method runs in its own transaction via the
session factory (a small unit of work).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.domain.entities import AgentAction, Conversation, Example, Turn
from app.domain.value_objects import (
    ActionType,
    ConversationId,
    DatasetId,
    RunId,
    TurnId,
    TurnRole,
)
from app.infrastructure.db import models


class SqlConversationRepository:
    """Adapter for ``ConversationRepository`` over the app schema."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, cid: ConversationId) -> Conversation | None:
        async with self._sessionmaker() as session:
            stmt = (
                select(models.Conversation)
                .where(models.Conversation.id == uuid.UUID(cid))
                .options(selectinload(models.Conversation.turns))
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_conversation(row) if row is not None else None

    async def create(self, conversation: Conversation) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(
                models.Conversation(
                    id=uuid.UUID(conversation.id),
                    title=conversation.title,
                    user_ref=conversation.user_ref,
                )
            )

    async def append_turn(self, cid: ConversationId, turn: Turn) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(
                models.Turn(
                    id=uuid.UUID(turn.id),
                    conversation_id=uuid.UUID(cid),
                    role=turn.role.value,
                    content=turn.content,
                    created_at=turn.created_at,
                )
            )
            await session.execute(
                update(models.Conversation)
                .where(models.Conversation.id == uuid.UUID(cid))
                .values(updated_at=turn.created_at)
            )


class SqlRunRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def record_start(self, run_id: RunId, conversation_id: ConversationId) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(
                models.Run(
                    id=uuid.UUID(run_id),
                    conversation_id=uuid.UUID(conversation_id),
                    status="running",
                )
            )

    async def record_status(self, run_id: RunId, status: str, error: str | None = None) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(models.Run)
                .where(models.Run.id == uuid.UUID(run_id))
                .values(status=status, error=error)
            )


class SqlAgentActionRepository:
    """Append-only audit outbox (ASI10 — full action trail)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def append(self, action: AgentAction) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(
                models.AgentActionRow(
                    id=uuid.UUID(action.id),
                    run_id=uuid.UUID(action.run_id),
                    action_type=action.action_type.value,
                    sql_text=action.sql_text,
                    decision=action.decision,
                    row_count=action.row_count,
                    elapsed_ms=action.elapsed_ms,
                    error=action.error,
                    created_at=action.created_at,
                )
            )

    async def for_run(self, run_id: RunId) -> tuple[AgentAction, ...]:
        async with self._sessionmaker() as session:
            stmt = (
                select(models.AgentActionRow)
                .where(models.AgentActionRow.run_id == uuid.UUID(run_id))
                .order_by(models.AgentActionRow.created_at)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return tuple(_to_agent_action(r) for r in rows)


class SqlExampleRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def for_dataset(self, dataset_id: DatasetId) -> tuple[Example, ...]:
        async with self._sessionmaker() as session:
            stmt = select(models.FewShotExample).where(
                models.FewShotExample.dataset_id == uuid.UUID(dataset_id)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return tuple(Example(question=r.question, sql=r.sql, tags=tuple(r.tags)) for r in rows)


class SqlEvalRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def record_run(
        self,
        git_sha: str,
        execution_accuracy: float,
        faithfulness: float,
        guardrail_pass_rate: float,
        mlflow_run_id: str | None,
    ) -> str:
        run_id = uuid.uuid4()
        async with self._sessionmaker() as session, session.begin():
            session.add(
                models.EvalRun(
                    id=run_id,
                    git_sha=git_sha,
                    execution_accuracy=execution_accuracy,
                    faithfulness=faithfulness,
                    guardrail_pass_rate=guardrail_pass_rate,
                    mlflow_run_id=mlflow_run_id,
                )
            )
        return str(run_id)


# --- row -> domain mappers --------------------------------------------------


def _to_conversation(row: models.Conversation) -> Conversation:
    return Conversation(
        id=ConversationId(str(row.id)),
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        user_ref=row.user_ref,
        turns=tuple(_to_turn(t) for t in sorted(row.turns, key=lambda t: t.created_at)),
    )


def _to_turn(row: models.Turn) -> Turn:
    return Turn(
        id=TurnId(str(row.id)),
        conversation_id=ConversationId(str(row.conversation_id)),
        role=TurnRole(row.role),
        content=row.content,
        created_at=row.created_at,
    )


def _to_agent_action(row: models.AgentActionRow) -> AgentAction:
    return AgentAction(
        id=str(row.id),
        run_id=RunId(str(row.run_id)),
        action_type=ActionType(row.action_type),
        created_at=row.created_at,
        sql_text=row.sql_text,
        decision=row.decision,
        row_count=row.row_count,
        elapsed_ms=row.elapsed_ms,
        error=row.error,
    )
