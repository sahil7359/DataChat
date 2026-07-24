"""Request-id + structured access logging middleware.

Generates/propagates an ``X-Request-ID`` correlation id, binds it to the log
context for the whole request, and echoes it on the response. This is the id that
threads FE -> BFF -> graph -> provider (NFR-9).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.domain.value_objects import new_uuid
from app.infrastructure.observability.logging import get_logger

_log = get_logger("api.access")
_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(_HEADER) or new_uuid()
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "path")
        response.headers[_HEADER] = request_id
        _log.info("request", method=request.method, status=response.status_code)
        return response
