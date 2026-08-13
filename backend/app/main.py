"""ASGI entrypoint and app assembly.

``create_app`` builds the FastAPI app (middleware, routers, CORS, safe error
handlers). The lifespan wires the real services (container, Postgres checkpointer,
rate limiter, repositories) unless they were already injected — which is how tests
run the whole edge with fakes and no live services.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver

from app import __version__
from app.config import Settings, get_settings
from app.infrastructure.observability.logging import configure_logging, get_logger
from app.infrastructure.observability.metrics import Metrics
from app.interface.api.errors import register_exception_handlers
from app.interface.api.middleware import RequestContextMiddleware
from app.interface.api.rate_limit import RateLimiter
from app.interface.api.routers import (
    chat,
    conversations,
    datasets,
    health,
    metrics,
    reports,
)

_log = get_logger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not getattr(app.state, "configured", False):
            await _setup(app, settings)
        yield
        await _teardown(app)

    app = FastAPI(title="DataChat API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    if not getattr(app.state, "metrics", None):
        app.state.metrics = Metrics()

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    api = "/api/v1"
    app.include_router(chat.router, prefix=api)
    app.include_router(conversations.router, prefix=api)
    app.include_router(datasets.router, prefix=api)
    app.include_router(reports.router, prefix=api)
    app.include_router(health.router)
    app.include_router(metrics.router)
    return app


async def _register_prompts_bounded(
    register: Callable[[dict[str, str]], None], versions: dict[str, str], settings: Settings
) -> None:
    """Register prompt versions without letting telemetry gate readiness.

    why: registration talks to the MLflow tracking server. When that host is
    unreachable the call blocks on connection retries — measured at ~90s, long
    enough for a platform health check on ``/ready`` to fail the deploy. The
    tracer is best-effort at request time; startup has to be too.

    Bounded and run off the event loop. On timeout the worker thread is left to
    finish and its result discarded: it is a log line, not state we need.
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(register, versions), timeout=settings.mlflow_startup_timeout_s
        )
    except TimeoutError:
        _log.warning("prompt_register_timed_out", timeout_s=settings.mlflow_startup_timeout_s)
    except Exception:
        _log.warning("prompt_register_failed")


async def _setup(app: FastAPI, settings: Settings) -> None:
    from app.application.prompts.registry import PROMPT_VERSIONS
    from app.container import Container
    from app.infrastructure.db.repositories import SqlConversationRepository
    from app.infrastructure.observability.mlflow_tracer import register_prompts

    container = Container(settings)
    app.state.metrics = container.metrics
    if not settings.use_mocks:
        await _register_prompts_bounded(register_prompts, PROMPT_VERSIONS, settings)
    stack = AsyncExitStack()
    checkpointer = await _build_checkpointer(stack, settings)

    app.state.container = container
    app.state.cache = container.cache
    app.state.query_service = container.query_service(checkpointer)
    app.state.conversation_repo = SqlConversationRepository(container._sessionmaker)
    app.state.rate_limiter = RateLimiter(
        container.cache,
        per_minute=settings.rate_limit_per_min,
        daily_quota=settings.global_daily_quota,
    )
    app.state.exit_stack = stack
    app.state.configured = True
    _log.info("app_configured", mocks=settings.use_mocks)


async def _build_checkpointer(
    stack: AsyncExitStack, settings: Settings
) -> BaseCheckpointSaver[Any]:
    """Durable checkpointer over a *pool*, not a single connection.

    why: ``AsyncPostgresSaver.from_conn_string`` opens one connection, and psycopg
    refuses overlapping commands on one connection —

        OperationalError: sending prepared query failed:
        another command is already in progress

    The graph checkpoints after every node, so two turns in flight at once (or one
    turn whose writes interleave) collide and the whole stream fails. It survived
    single-user testing and would have broken the first time two people opened the
    demo together. A pool gives each concurrent operation its own connection.

    ``max_size`` is small on purpose: the free Postgres tier has a low connection
    ceiling, and the executor holds its own separate pool.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import AsyncConnection
    from psycopg.rows import DictRow, dict_row
    from psycopg_pool import AsyncConnectionPool

    conn = settings.database_url.replace("+asyncpg", "")
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        conninfo=conn,
        min_size=1,
        max_size=settings.checkpointer_pool_size,
        kwargs={
            # The saver issues its own transactions; autocommit avoids wrapping
            # every checkpoint write in an extra outer transaction.
            "autocommit": True,
            "prepare_threshold": 0,
            # AsyncPostgresSaver reads rows by column name, so the pool must hand
            # it dict rows rather than psycopg's default tuples.
            "row_factory": dict_row,
        },
        open=False,
    )
    await stack.enter_async_context(pool)
    await pool.open(wait=True)
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    checkpointer: BaseCheckpointSaver[Any] = saver
    return checkpointer


async def _teardown(app: FastAPI) -> None:
    stack = getattr(app.state, "exit_stack", None)
    if stack is not None:
        await stack.aclose()
    container = getattr(app.state, "container", None)
    if container is not None:
        await container.aclose()


app = create_app()
