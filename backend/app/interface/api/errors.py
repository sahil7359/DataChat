"""Safe error mapping and exception handlers.

Internal errors never reach the client as stack traces (LLM05, and good UX). Each
maps to a stable code + a human message + the trace id, so a user can quote the id
for support while nothing sensitive leaks.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.results import (
    AllProvidersUnavailableError,
    DataChatError,
    QuotaExceededError,
)
from app.infrastructure.observability.logging import get_logger

_log = get_logger("api.errors")

_STATUS = {
    "providers_unavailable": 503,
    "quota_exceeded": 429,
    "validation_error": 422,
    "internal_error": 500,
}
_MESSAGES = {
    "providers_unavailable": "The service is busy right now — please try again shortly.",
    "quota_exceeded": "Daily usage limit reached — please try again tomorrow.",
    "validation_error": "The request was invalid.",
    "internal_error": "Something went wrong. Please try again.",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _body(code: str, request: Request) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": _MESSAGES.get(code, _MESSAGES["internal_error"]),
            "trace_id": _request_id(request),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=_body("validation_error", request))

    @app.exception_handler(AllProvidersUnavailableError)
    async def _providers(request: Request, exc: AllProvidersUnavailableError) -> JSONResponse:
        _log.warning("providers_unavailable", trace_id=_request_id(request))
        return JSONResponse(status_code=503, content=_body("providers_unavailable", request))

    @app.exception_handler(QuotaExceededError)
    async def _quota(request: Request, exc: QuotaExceededError) -> JSONResponse:
        return JSONResponse(status_code=429, content=_body("quota_exceeded", request))

    @app.exception_handler(DataChatError)
    async def _domain(request: Request, exc: DataChatError) -> JSONResponse:
        _log.warning("domain_error", trace_id=_request_id(request), error=type(exc).__name__)
        return JSONResponse(status_code=500, content=_body("internal_error", request))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the type only — never echo the message/stack to the client.
        _log.error("unhandled_exception", trace_id=_request_id(request), error=type(exc).__name__)
        return JSONResponse(status_code=500, content=_body("internal_error", request))
