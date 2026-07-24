"""FastAPI dependency providers. They pull the singletons built at startup off
``app.state`` so requests stay stateless (NFR-10) and tests can override any of
them with fakes."""

from __future__ import annotations

from fastapi import Depends, Request

from app.application.services.query_service import QueryService
from app.domain.ports.cache import Cache
from app.domain.ports.repositories import ConversationRepository
from app.interface.api.rate_limit import RateLimiter


def get_query_service(request: Request) -> QueryService:
    service: QueryService = request.app.state.query_service
    return service


def get_cache(request: Request) -> Cache:
    cache: Cache = request.app.state.cache
    return cache


def get_conversation_repo(request: Request) -> ConversationRepository | None:
    return getattr(request.app.state, "conversation_repo", None)


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


async def enforce_rate_limit(
    request: Request, limiter: RateLimiter = Depends(get_rate_limiter)
) -> None:
    await limiter(request)
