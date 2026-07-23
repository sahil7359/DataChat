"""ASGI entrypoint.

Phase 0 keeps this deliberately minimal: a liveness endpoint so the container
has something to boot and a smoke test to assert against. The real BFF edge
(routers, middleware, SSE) arrives in Phase 8 and is wired here via the
composition root.
"""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"]
    version: str


def create_app() -> FastAPI:
    app = FastAPI(title="DataChat API", version="0.1.0")

    @app.get("/health", response_model=Health)
    async def health() -> Health:
        from app import __version__

        return Health(status="ok", version=__version__)

    return app


app = create_app()
