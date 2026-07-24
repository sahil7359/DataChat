"""Read-only executor against a live Postgres: row cap, truncation, timeout."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.domain.results import Err, Ok
from app.infrastructure.db.ingestion_repositories import PgAnalyticsLoader
from app.infrastructure.sql.executor import ReadOnlyQueryExecutor
from ingestion.definitions import seed_tables

pytestmark = pytest.mark.integration


def _executor_engine() -> AsyncEngine:
    admin = make_url(os.environ["DATACHAT_TEST_DATABASE_URL"])
    pw = get_settings().executor_role_password.get_secret_value()
    url = admin.set(username="datachat_exec", password=pw)
    return create_async_engine(
        url,
        connect_args={
            "server_settings": {
                "statement_timeout": "5000",
                "default_transaction_read_only": "on",
                "search_path": "analytics",
            }
        },
    )


async def _seed(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    loader = PgAnalyticsLoader(sessionmaker)
    for table in seed_tables():
        await loader.upsert(table)


async def test_executor_returns_rows(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(migrated_sessionmaker)
    engine = _executor_engine()
    try:
        executor = ReadOnlyQueryExecutor(engine, row_cap=1000, timeout_s=5)
        result = await executor.execute(
            "SELECT country_iso3, co2_per_capita FROM owid_co2 WHERE year = 2022 "
            "ORDER BY co2_per_capita DESC LIMIT 3"
        )
        assert isinstance(result, Ok)
        assert result.value.columns == ("country_iso3", "co2_per_capita")
        assert result.value.row_count == 3
    finally:
        await engine.dispose()


async def test_executor_caps_rows_and_flags_truncation(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(migrated_sessionmaker)
    engine = _executor_engine()
    try:
        executor = ReadOnlyQueryExecutor(engine, row_cap=5, timeout_s=5)
        result = await executor.execute("SELECT * FROM owid_co2 LIMIT 100")
        assert isinstance(result, Ok)
        assert result.value.row_count == 5
        assert result.value.truncated is True
    finally:
        await engine.dispose()


async def test_executor_times_out_gracefully(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    engine = _executor_engine()
    try:
        executor = ReadOnlyQueryExecutor(engine, row_cap=5, timeout_s=0.5)
        result = await executor.execute("SELECT pg_sleep(5)")
        assert isinstance(result, Err)
        assert result.error.code in {"57014", "db_error"}
    finally:
        await engine.dispose()


async def test_executor_cannot_write(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(migrated_sessionmaker)
    engine = _executor_engine()
    try:
        executor = ReadOnlyQueryExecutor(engine, row_cap=5, timeout_s=5)
        result = await executor.execute("DELETE FROM owid_co2")
        assert isinstance(result, Err)  # read-only role rejects it
    finally:
        await engine.dispose()
