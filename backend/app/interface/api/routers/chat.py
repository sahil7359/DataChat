"""Chat endpoints: the streaming ask, and the HITL resume.

Both return Server-Sent Events. ``POST /chat`` supports an ``Idempotency-Key``
header — a retried request with the same key does not re-run the agent, it just
replays a terminal ``done`` pointing at the original run (dedupe). All agent
errors inside the stream are turned into a safe ``error`` event; a stack trace
never reaches the client.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.application.agent.events import AgentEvent, DoneEvent, ErrorEvent
from app.application.services.query_service import QueryService
from app.domain.ports.cache import Cache
from app.domain.results import AllProvidersUnavailableError, QuotaExceededError
from app.domain.value_objects import new_uuid
from app.infrastructure.observability.logging import get_logger
from app.interface.api.schemas import ChatRequest, ResumeRequest
from app.interface.api.sse import format_sse
from app.interface.deps import enforce_rate_limit, get_cache, get_query_service

router = APIRouter(tags=["chat"])
_log = get_logger("api.chat")
_IDEMPOTENCY_TTL = 86400


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    _: None = Depends(enforce_rate_limit),
    service: QueryService = Depends(get_query_service),
    cache: Cache = Depends(get_cache),
) -> StreamingResponse:
    request_id = getattr(request.state, "request_id", "")
    run_id = new_uuid()

    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        existing = await cache.get(f"idem:{idempotency_key}")
        if existing is not None:
            return _sse_response(_deduped(existing.decode("utf-8")), request_id)
        await cache.set(f"idem:{idempotency_key}", run_id.encode("utf-8"), _IDEMPOTENCY_TTL)

    events = service.stream(
        body.question,
        body.conversation_id,
        approve_sql=body.options.approve_sql,
        run_id=run_id,
    )
    return _sse_response(_safe_frames(events, request_id), request_id)


@router.post("/chat/{run_id}/resume")
async def resume(
    run_id: str,
    request: Request,
    body: ResumeRequest,
    _: None = Depends(enforce_rate_limit),
    service: QueryService = Depends(get_query_service),
) -> StreamingResponse:
    request_id = getattr(request.state, "request_id", "")
    events = service.resume(run_id, body.to_command())
    return _sse_response(_safe_frames(events, request_id), request_id)


def _sse_response(frames: AsyncIterator[str], request_id: str) -> StreamingResponse:
    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers={"X-Request-ID": request_id, "Cache-Control": "no-cache"},
    )


async def _safe_frames(events: AsyncIterator[AgentEvent], request_id: str) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield format_sse(event)
    except (AllProvidersUnavailableError, QuotaExceededError):
        yield format_sse(
            ErrorEvent(code="providers_unavailable", message="Busy right now — try again shortly.")
        )
        yield format_sse(DoneEvent(run_id="", trace_id=request_id))
    except Exception as exc:
        # exc_info, because "stream_failed" alone is unactionable: it says a turn
        # broke without saying how, and the client deliberately only ever sees
        # "Something went wrong". Server-side logs are the one place the cause can
        # live, so the traceback belongs here. Nothing extra reaches the user.
        _log.error(
            "stream_failed",
            trace_id=request_id,
            error=type(exc).__name__,
            detail=str(exc)[:500],
            exc_info=True,
        )
        yield format_sse(ErrorEvent(code="internal_error", message="Something went wrong."))
        yield format_sse(DoneEvent(run_id="", trace_id=request_id))


async def _deduped(run_id: str) -> AsyncIterator[str]:
    yield format_sse(DoneEvent(run_id=run_id))
