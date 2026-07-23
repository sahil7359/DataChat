"""Adapter tests using httpx.MockTransport — real request building and response
parsing, no network. Covers the HTTP failure -> LLMProviderError mapping."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.domain.entities import LLMMessage, LLMRequest, MessageRole
from app.domain.results import LLMProviderError
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.llm.embeddings import GeminiEmbeddingAdapter
from app.infrastructure.llm.gemini import GeminiAdapter
from app.infrastructure.llm.groq import GroqAdapter
from app.infrastructure.llm.openrouter import OpenRouterAdapter

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _req(task: TaskKind = TaskKind.SQL_GEN) -> LLMRequest:
    return LLMRequest(
        messages=(
            LLMMessage(MessageRole.SYSTEM, "you are a SQL assistant"),
            LLMMessage(MessageRole.USER, "count rows"),
        ),
        task=task,
    )


async def test_gemini_builds_request_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-goog-api-key")
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "SELECT 1"}]}, "finishReason": "STOP"}
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
            },
        )

    async with _client(handler) as client:
        adapter = GeminiAdapter(client, "secret-key", model="gemini-1.5-flash")
        resp = await adapter.complete(_req())

    assert resp.text == "SELECT 1"
    assert resp.provider is Provider.GEMINI
    assert resp.total_tokens == 7
    assert captured["key"] == "secret-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert "systemInstruction" in body  # system message routed correctly


async def test_groq_openai_shape_is_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer k"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "SELECT 2"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    async with _client(handler) as client:
        adapter = GroqAdapter(client, "k")
        resp = await adapter.complete(_req())

    assert resp.text == "SELECT 2"
    assert resp.provider is Provider.GROQ


async def test_openrouter_uses_its_base_url() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with _client(handler) as client:
        adapter = OpenRouterAdapter(client, "k")
        await adapter.complete(_req())

    assert seen["url"].startswith("https://openrouter.ai/api/v1/")


async def test_429_is_retryable_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "2.5"}, json={})

    async with _client(handler) as client:
        adapter = GroqAdapter(client, "k")
        with pytest.raises(LLMProviderError) as exc:
            await adapter.complete(_req())

    assert exc.value.retryable is True
    assert exc.value.retry_after == 2.5


async def test_500_is_retryable_and_400_is_not() -> None:
    async with _client(lambda r: httpx.Response(503, json={})) as client:
        with pytest.raises(LLMProviderError) as exc:
            await GroqAdapter(client, "k").complete(_req())
        assert exc.value.retryable is True

    async with _client(lambda r: httpx.Response(400, json={})) as client:
        with pytest.raises(LLMProviderError) as exc:
            await GroqAdapter(client, "k").complete(_req())
        assert exc.value.retryable is False


async def test_timeout_maps_to_retryable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    async with _client(handler) as client:
        with pytest.raises(LLMProviderError) as exc:
            await GroqAdapter(client, "k").complete(_req())
    assert exc.value.retryable is True


async def test_gemini_embeddings_return_sized_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embedding": {"values": [0.1, 0.2, 0.3]}})

    async with _client(handler) as client:
        adapter = GeminiEmbeddingAdapter(client, "k", dim=3)
        vec = await adapter.embed("hello")

    assert vec.dim == 3
    assert vec.values == (0.1, 0.2, 0.3)
