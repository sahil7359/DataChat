from collections.abc import AsyncIterator

import pytest

from app.domain.entities import LLMMessage, LLMRequest, LLMResponse, MessageRole
from app.domain.results import LLMProviderError
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.llm.circuit_breaker import BreakerState, CircuitBreaker
from app.infrastructure.llm.decorators import (
    CachingProvider,
    CircuitBreakerProvider,
    RetryingProvider,
    TracingProvider,
    build_resilient,
)
from tests.fakes.cache import InMemoryCache
from tests.fakes.tracing import NoopTracer


def _req(task: TaskKind = TaskKind.SQL_GEN, temperature: float = 0.0) -> LLMRequest:
    return LLMRequest(
        messages=(LLMMessage(MessageRole.USER, "q"),), task=task, temperature=temperature
    )


class Flaky:
    """Fails `fail_times` with a retryable error, then succeeds. Counts calls."""

    def __init__(self, *, fail_times: int = 0, retryable: bool = True) -> None:
        self.name = "flaky"
        self._fail_times = fail_times
        self._retryable = retryable
        self.calls = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise LLMProviderError(self.name, "boom", retryable=self._retryable)
        return LLMResponse(text="ok", provider=Provider.GEMINI, model="m")

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        yield "ok"


async def _noop_sleep(_seconds: float) -> None:
    return None


async def test_retry_succeeds_after_transient_failures() -> None:
    inner = Flaky(fail_times=2)
    provider = RetryingProvider(inner, max_attempts=3, sleep=_noop_sleep)

    resp = await provider.complete(_req())

    assert resp.text == "ok"
    assert inner.calls == 3


async def test_retry_gives_up_after_cap() -> None:
    inner = Flaky(fail_times=5)
    provider = RetryingProvider(inner, max_attempts=3, sleep=_noop_sleep)

    with pytest.raises(LLMProviderError):
        await provider.complete(_req())
    assert inner.calls == 3  # bounded, not infinite (LLM10)


async def test_retry_does_not_retry_non_retryable() -> None:
    inner = Flaky(fail_times=1, retryable=False)
    provider = RetryingProvider(inner, max_attempts=3, sleep=_noop_sleep)

    with pytest.raises(LLMProviderError):
        await provider.complete(_req())
    assert inner.calls == 1


async def test_retry_respects_retry_after() -> None:
    slept: list[float] = []

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    class RateLimited:
        name = "rl"

        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, req: LLMRequest) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderError("rl", "429", retryable=True, retry_after=5.0)
            return LLMResponse(text="ok", provider=Provider.GROQ, model="m")

        async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
            yield "ok"

    provider = RetryingProvider(RateLimited(), max_attempts=3, sleep=record_sleep, rng=lambda: 0.0)
    await provider.complete(_req())

    assert slept and slept[0] >= 5.0


async def test_cache_hit_skips_inner_for_deterministic_calls() -> None:
    inner = Flaky(fail_times=0)
    provider = CachingProvider(inner, InMemoryCache())

    first = await provider.complete(_req(temperature=0.0))
    second = await provider.complete(_req(temperature=0.0))

    assert inner.calls == 1
    assert first.cached is False
    assert second.cached is True


async def test_cache_bypassed_when_temperature_nonzero() -> None:
    inner = Flaky(fail_times=0)
    provider = CachingProvider(inner, InMemoryCache())

    await provider.complete(_req(temperature=0.7))
    await provider.complete(_req(temperature=0.7))

    assert inner.calls == 2


async def test_open_breaker_fails_fast_without_calling_inner() -> None:
    cache = InMemoryCache()
    breaker = CircuitBreaker(cache, fail_threshold=1, cooldown_s=999)
    await breaker.record_failure("flaky")  # -> OPEN
    assert await breaker.state("flaky") is BreakerState.OPEN

    inner = Flaky(fail_times=0)
    provider = CircuitBreakerProvider(inner, breaker)

    with pytest.raises(LLMProviderError):
        await provider.complete(_req())
    assert inner.calls == 0  # fail fast


async def test_tracing_records_span_attributes() -> None:
    tracer = NoopTracer()
    provider = TracingProvider(Flaky(fail_times=0), tracer)

    await provider.complete(_req())

    assert tracer.spans
    span = tracer.spans[0]
    assert span.name == "llm.complete"
    assert span.attributes["provider"] == "flaky"
    assert "tokens.total" in span.attributes


async def test_build_resilient_composes_and_serves() -> None:
    cache = InMemoryCache()
    breaker = CircuitBreaker(cache, fail_threshold=5, cooldown_s=30)
    provider = build_resilient(
        Flaky(fail_times=2),
        tracer=NoopTracer(),
        cache=cache,
        breaker=breaker,
        sleep=_noop_sleep,
    )

    resp = await provider.complete(_req())
    assert resp.text == "ok"
