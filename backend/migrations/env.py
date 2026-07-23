"""Async Alembic environment.

Autogenerate is scoped to the ``app`` schema; the ``analytics`` schema and the
security-critical roles/grants are hand-written migrations (Schema §8). The
``alembic_version`` table lives in ``app``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.infrastructure.db import models  # noqa: F401  (registers tables on the metadata)
from app.infrastructure.db.base import APP_SCHEMA, Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return get_settings().database_url


def include_object(obj: object, name: str | None, type_: str, *_: object) -> bool:
    # Only the app schema participates in autogenerate diffs.
    schema = getattr(obj, "schema", None)
    return not (type_ in {"table", "column"} and schema not in (APP_SCHEMA, None))


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=APP_SCHEMA,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    # The version table lives in the app schema, so it must exist before Alembic
    # touches it (the first migration also creates it, idempotently).
    connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {APP_SCHEMA}")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=APP_SCHEMA,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _url()
    engine = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def app_tables() -> Iterable[object]:
    return [t for t in Base.metadata.sorted_tables if t.schema == APP_SCHEMA]


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
