"""Repository round-trips against a live Postgres (runs in CI/Docker)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities import AgentAction, Conversation, Turn
from app.domain.value_objects import (
    ActionType,
    ConversationId,
    RunId,
    TurnId,
    TurnRole,
    new_uuid,
)
from app.infrastructure.db.repositories import (
    SqlAgentActionRepository,
    SqlConversationRepository,
    SqlRunRepository,
)

pytestmark = pytest.mark.integration


async def test_conversation_create_get_and_append_turn(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlConversationRepository(migrated_sessionmaker)
    cid = ConversationId(new_uuid())
    now = datetime.now(UTC)

    await repo.create(Conversation(id=cid, title="CO2 questions", created_at=now, updated_at=now))
    await repo.append_turn(
        cid,
        Turn(
            id=TurnId(new_uuid()),
            conversation_id=cid,
            role=TurnRole.USER,
            content="Top 5 emitters per capita?",
            created_at=now,
        ),
    )

    loaded = await repo.get(cid)
    assert loaded is not None
    assert loaded.title == "CO2 questions"
    assert len(loaded.turns) == 1
    assert loaded.turns[0].role is TurnRole.USER


async def test_run_and_audit_trail(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    conversations = SqlConversationRepository(migrated_sessionmaker)
    runs = SqlRunRepository(migrated_sessionmaker)
    audit = SqlAgentActionRepository(migrated_sessionmaker)

    cid = ConversationId(new_uuid())
    rid = RunId(new_uuid())
    now = datetime.now(UTC)
    await conversations.create(Conversation(id=cid, title="t", created_at=now, updated_at=now))
    await runs.record_start(rid, cid)
    await audit.append(
        AgentAction(
            id=new_uuid(),
            run_id=rid,
            action_type=ActionType.EXECUTE,
            created_at=now,
            sql_text="SELECT 1",
            row_count=1,
            elapsed_ms=4,
        )
    )
    await runs.record_status(rid, "done")

    trail = await audit.for_run(rid)
    assert len(trail) == 1
    assert trail[0].action_type is ActionType.EXECUTE
    assert trail[0].sql_text == "SELECT 1"
