"""Async engines and session factories.

Two engines on purpose (Bulkhead, Design §9): the app engine runs migrations and
app-schema CRUD as ``app_rw``; the executor engine is a **separate pool** bound to
the read-only ``datachat_exec`` role. Isolating the analytics query pool means a
slow or abusive query can't exhaust the connections the app needs to serve HITL
and streaming — and the executor physically cannot write.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_app_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def create_executor_engine(settings: Settings) -> AsyncEngine:
    """A small, isolated read-only pool for analytics query execution.

    The statement timeout and read-only transaction default are enforced by the
    ``datachat_exec`` role itself (Schema §5); we set them here too as
    belt-and-braces and to make the intent visible at the connection layer.
    """
    return create_async_engine(
        settings.executor_database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_recycle=900,
        connect_args={
            "server_settings": {
                "statement_timeout": str(settings.statement_timeout_ms),
                "default_transaction_read_only": "on",
                "search_path": "analytics",
            }
        },
    )
