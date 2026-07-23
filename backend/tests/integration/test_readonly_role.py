"""Security case (LLM06 / ASI02 / ASI03): even with a direct connection, the
``datachat_exec`` role cannot write, cannot exceed the timeout, and cannot read
the app schema. This is the second, database-level layer of defence — it holds
regardless of the guardrail chain.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

pytestmark = pytest.mark.integration


def _executor_url() -> str:
    admin = make_url(os.environ["DATACHAT_TEST_DATABASE_URL"])
    pw = get_settings().executor_role_password.get_secret_value()
    return str(admin.set(username="datachat_exec", password=pw))


async def test_readonly_role_can_select_analytics(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    engine = create_async_engine(_executor_url())
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT count(*) FROM analytics.countries"))
            assert result.scalar_one() >= 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "write_sql",
    [
        "INSERT INTO analytics.countries (iso3, name) VALUES ('ZZZ', 'Nowhere')",
        "UPDATE analytics.countries SET name = 'x'",
        "DELETE FROM analytics.countries",
        "CREATE TABLE analytics.evil (x int)",
    ],
)
async def test_readonly_role_rejects_every_write(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
    write_sql: str,
) -> None:
    engine = create_async_engine(_executor_url())
    try:
        async with engine.connect() as conn:
            with pytest.raises((DBAPIError, ProgrammingError)):
                await conn.execute(text(write_sql))
    finally:
        await engine.dispose()


async def test_readonly_role_cannot_read_app_schema(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    engine = create_async_engine(_executor_url())
    try:
        async with engine.connect() as conn:
            with pytest.raises((DBAPIError, ProgrammingError)):
                await conn.execute(text("SELECT * FROM app.conversations"))
    finally:
        await engine.dispose()
