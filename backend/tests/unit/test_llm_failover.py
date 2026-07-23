"""End-to-end resilience: adapters + decorator stack + router failing over from
a down Gemini (503) to a healthy Groq, using MockTransport (no real keys)."""

from __future__ import annotations

import httpx

from app.domain.entities import LLMMessage, LLMRequest, MessageRole
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.llm.circuit_breaker import BreakerState, CircuitBreaker
from app.infrastructure.llm.decorators import build_resilient
from app.infrastructure.llm.gemini import GeminiAdapter
from app.infrastructure.llm.groq import GroqAdapter
from app.infrastructure.llm.router import ProviderRouter, TaskAwarePolicy
from tests.fakes.cache import InMemoryCache
from tests.fakes.tracing import NoopTracer


async def _noop_sleep(_seconds: float) -> None:
    return None


def _down(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={})


def _groq_ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": "SELECT 42"}, "finish_reason": "stop"}]},
    )


async def test_router_fails_over_gemini_to_groq_and_trips_breaker() -> None:
    cache = InMemoryCache()
    # One failed operation (after its internal retries) trips the breaker. The
    # breaker sits outside Retry, so it counts operations, not individual attempts.
    breaker = CircuitBreaker(cache, fail_threshold=1, cooldown_s=30)

    gemini_client = httpx.AsyncClient(transport=httpx.MockTransport(_down))
    groq_client = httpx.AsyncClient(transport=httpx.MockTransport(_groq_ok))

    gemini = build_resilient(
        GeminiAdapter(gemini_client, "k"),
        tracer=NoopTracer(),
        cache=cache,
        breaker=breaker,
        max_attempts=3,
        sleep=_noop_sleep,
    )
    groq = build_resilient(
        GroqAdapter(groq_client, "k"),
        tracer=NoopTracer(),
        cache=cache,
        breaker=breaker,
        max_attempts=3,
        sleep=_noop_sleep,
    )
    router = ProviderRouter(
        {Provider.GEMINI: gemini, Provider.GROQ: groq},
        TaskAwarePolicy(default_order=(Provider.GEMINI, Provider.GROQ)),
    )

    req = LLMRequest(messages=(LLMMessage(MessageRole.USER, "q"),), task=TaskKind.SQL_GEN)
    resp = await router.complete(req)

    assert resp.provider is Provider.GROQ
    assert resp.text == "SELECT 42"
    # Gemini failed 3x (retries) -> breaker opened for gemini, not groq.
    assert await breaker.state(Provider.GEMINI.value) is BreakerState.OPEN
    assert await breaker.state(Provider.GROQ.value) is BreakerState.CLOSED

    await gemini_client.aclose()
    await groq_client.aclose()
