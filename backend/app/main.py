"""ASGI entrypoint and app assembly.

``create_app`` builds the FastAPI app (middleware, routers, CORS, safe error
handlers). The lifespan wires the real services (container, Postgres checkpointer,
rate limiter, repositories) unless they were already injected — which is how tests
run the whole edge with fakes and no live services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
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


async def _setup(app: FastAPI, settings: Settings) -> None:
    from app.application.prompts.registry import PROMPT_VERSIONS
    from app.container import Container
    from app.infrastructure.db.repositories import SqlConversationRepository
    from app.infrastructure.observability.mlflow_tracer import register_prompts

    container = Container(settings)
    app.state.metrics = container.metrics
    if not settings.use_mocks:
        register_prompts(PROMPT_VERSIONS)
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
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn = settings.database_url.replace("+asyncpg", "")
    saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(conn))
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
