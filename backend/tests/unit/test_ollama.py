"""Ollama as a secured, primary AI service with cloud fallback."""

from __future__ import annotations

import httpx

from app.domain.entities import LLMMessage, LLMRequest, MessageRole
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.llm.ollama import OllamaAdapter
from app.infrastructure.llm.router import ProviderRouter, TaskAwarePolicy
from tests.fakes.llm import FakeLLMProvider


def _req(task: TaskKind = TaskKind.SQL_GEN) -> LLMRequest:
    return LLMRequest(messages=(LLMMessage(MessageRole.USER, "q"),), task=task)


async def test_ollama_sends_bearer_token_and_parses_response() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "SELECT 1 LIMIT 1"}, "finish_reason": "stop"}]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OllamaAdapter(
            client, "tunnel-secret", base_url="https://ollama.example.com/v1", model="llama3.2"
        )
        resp = await adapter.complete(_req())

    assert resp.provider is Provider.OLLAMA
    assert resp.text == "SELECT 1 LIMIT 1"
    assert seen["auth"] == "Bearer tunnel-secret"  # the tunnel token guards the GPU
    assert seen["url"].startswith("https://ollama.example.com/v1/")


def test_policy_leads_with_ollama_when_present() -> None:
    policy = TaskAwarePolicy(default_order=(Provider.GEMINI, Provider.GROQ))
    order = policy.order(TaskKind.CLASSIFY, [Provider.GROQ, Provider.GEMINI, Provider.OLLAMA])
    assert order[0] is Provider.OLLAMA  # primary regardless of task


def test_policy_unchanged_without_ollama() -> None:
    policy = TaskAwarePolicy(default_order=(Provider.GEMINI, Provider.GROQ))
    order = policy.order(TaskKind.CLASSIFY, [Provider.GEMINI, Provider.GROQ])
    assert order[0] is Provider.GROQ  # short task still prefers groq


async def test_router_falls_back_to_cloud_when_ollama_down() -> None:
    ollama = FakeLLMProvider(name="ollama", provider=Provider.OLLAMA, fail=True)
    groq = FakeLLMProvider(name="groq", provider=Provider.GROQ, default="SELECT 2")
    router = ProviderRouter(
        {Provider.OLLAMA: ollama, Provider.GROQ: groq},
        TaskAwarePolicy(default_order=(Provider.GEMINI, Provider.GROQ)),
    )

    resp = await router.complete(_req())

    assert resp.provider is Provider.GROQ  # PC/GPU hiccup -> cloud safety net
    assert len(ollama.calls) == 1  # tried Ollama first
