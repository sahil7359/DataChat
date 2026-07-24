"""Contract tests for the BFF edge: SSE stream, validation, rate limit,
idempotency, conversation history, and safe error mapping (no stack traces)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.application.agent.events import AgentEvent, DoneEvent, StatusEvent
from app.domain.entities import Conversation, Turn
from app.domain.results import AllProvidersUnavailableError
from app.domain.value_objects import ConversationId, TurnId, TurnRole, new_uuid
from tests.fakes.api import build_test_app
from tests.fakes.repositories import InMemoryConversationRepository


def test_datasets_endpoint_lists_curated_datasets() -> None:
    with TestClient(build_test_app()) as client:
        resp = client.get("/api/v1/datasets")

    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert {"seed", "wdi", "owid"} <= names


def test_chat_streams_sse_events() -> None:
    with TestClient(build_test_app()) as client:
        resp = client.post("/api/v1/chat", json={"question": "highest co2 per capita in 2022"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "event: sql" in body
    assert "event: rows" in body
    assert "event: done" in body


def test_chat_rejects_empty_question() -> None:
    with TestClient(build_test_app()) as client:
        resp = client.post("/api/v1/chat", json={"question": ""})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_rate_limit_returns_429_with_retry_after() -> None:
    with TestClient(build_test_app(per_minute=1)) as client:
        first = client.post("/api/v1/chat", json={"question": "q one"})
        second = client.post("/api/v1/chat", json={"question": "q two"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers.get("Retry-After") == "60"


class SpyQueryService:
    def __init__(self) -> None:
        self.stream_calls = 0

    async def stream(self, *args: object, **kwargs: object) -> AsyncIterator[AgentEvent]:
        self.stream_calls += 1
        yield StatusEvent(stage="done")
        yield DoneEvent(run_id="spy-run")

    async def resume(self, *args: object, **kwargs: object) -> AsyncIterator[AgentEvent]:
        yield DoneEvent(run_id="spy-run")


def test_idempotency_key_dedupes_chat() -> None:
    spy = SpyQueryService()
    app = build_test_app(query_service=spy)  # type: ignore[arg-type]
    with TestClient(app) as client:
        headers = {"Idempotency-Key": "abc-123"}
        first = client.post("/api/v1/chat", json={"question": "q"}, headers=headers)
        second = client.post("/api/v1/chat", json={"question": "q"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert spy.stream_calls == 1  # the second request did not re-run the agent
    assert "event: done" in second.text


class FailingQueryService:
    async def stream(self, *args: object, **kwargs: object) -> AsyncIterator[AgentEvent]:
        raise AllProvidersUnavailableError("all down")
        yield DoneEvent(run_id="x")  # type: ignore[unreachable]  # pragma: no cover

    async def resume(self, *args: object, **kwargs: object) -> AsyncIterator[AgentEvent]:
        yield DoneEvent(run_id="x")


def test_provider_outage_becomes_safe_error_event() -> None:
    app = build_test_app(query_service=FailingQueryService())  # type: ignore[arg-type]
    with TestClient(app) as client:
        resp = client.post("/api/v1/chat", json={"question": "q"})

    assert resp.status_code == 200  # stream opened, then degraded gracefully
    assert "providers_unavailable" in resp.text
    assert "Traceback" not in resp.text  # no stack trace leaks


def test_conversation_history_404_when_missing() -> None:
    with TestClient(build_test_app(conversation_repo=InMemoryConversationRepository())) as client:
        resp = client.get(f"/api/v1/conversations/{new_uuid()}")
    assert resp.status_code == 404


def test_conversation_history_returns_turns() -> None:
    repo = InMemoryConversationRepository()
    cid = ConversationId(new_uuid())
    now = datetime.now(UTC)

    async def _seed() -> None:
        await repo.create(Conversation(id=cid, title="CO2", created_at=now, updated_at=now))
        await repo.append_turn(
            cid,
            Turn(
                id=TurnId(new_uuid()),
                conversation_id=cid,
                role=TurnRole.USER,
                content="hi",
                created_at=now,
            ),
        )

    import anyio

    anyio.run(_seed)

    with TestClient(build_test_app(conversation_repo=repo)) as client:
        resp = client.get(f"/api/v1/conversations/{cid}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "CO2"
    assert body["turns"][0]["content"] == "hi"
