"""Shared test fixtures.

Integration tests need a real Postgres (pgvector). They are skipped unless
``DATACHAT_TEST_DATABASE_URL`` points at one, so the default local gate runs with
no external services. CI/Docker sets that variable.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

INTEGRATION_ENV = "DATACHAT_TEST_DATABASE_URL"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv(INTEGRATION_ENV):
        return
    skip = pytest.mark.skip(reason=f"set {INTEGRATION_ENV} to run integration tests (CI/Docker)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


def _run_alembic(url: str, direction: str) -> None:
    from alembic import command
    from alembic.config import Config

    from app.config import get_settings

    os.environ["DATACHAT_DATABASE_URL"] = url
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    if direction == "up":
        command.upgrade(cfg, "head")
    else:
        command.downgrade(cfg, "base")


@pytest_asyncio.fixture
async def migrated_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.infrastructure.db.session import create_session_factory

    url = os.environ[INTEGRATION_ENV]
    await asyncio.to_thread(_run_alembic, url, "up")
    engine = create_async_engine(url)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()
        await asyncio.to_thread(_run_alembic, url, "down")
