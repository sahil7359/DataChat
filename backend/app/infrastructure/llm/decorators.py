"""Resilience decorator stack for LLM providers.

Each concern is its own Decorator wrapping an inner ``LLMProvider``, composed in
one explicit order (outermost first):

    Tracing -> Caching -> CircuitBreaker -> Retry -> Adapter

Order is a design decision, not an accident:
- Tracing outermost so a span covers the whole call, including cache hits.
- Caching next so a hit skips the breaker, the retries, and the network entirely.
- CircuitBreaker before Retry so an open breaker fails fast instead of retrying.
- Retry innermost so the breaker records the outcome *after* retries are spent.

Adding a concern is a new decorator in the chain — the adapters never change (SRP,
Open/Closed).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable

from app.domain.entities import LLMRequest, LLMResponse
from app.domain.ports.cache import Cache
from app.domain.ports.llm import LLMProvider as _Provider
from app.domain.ports.tracing import Tracer
from app.domain.results import LLMProviderError
from app.domain.value_objects import Provider
from app.infrastructure.llm.circuit_breaker import CircuitBreaker

SleepFn = Callable[[float], Awaitable[None]]


class TracingProvider:
    """Wraps a provider in a span recording provider, task, tokens, and cache state."""

    def __init__(self, inner: _Provider, tracer: Tracer) -> None:
        self._inner = inner
        self._tracer = tracer
        self.name = inner.name

    async def complete(self, req: LLMRequest) -> LLMResponse:
        with self._tracer.span("llm.complete", provider=self.name, task=req.task.value) as span:
            resp = await self._inner.complete(req)
            span.set_attribute("tokens.total", resp.total_tokens)
            span.set_attribute("cached", resp.cached)
            span.set_attribute("model", resp.model)
            return resp

    def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        return self._inner.stream(req)


class CachingProvider:
    """Result cache for deterministic (temperature 0) completions."""

    def __init__(self, inner: _Provider, cache: Cache, *, ttl_s: int = 3600) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_s
        self.name = inner.name

    async def complete(self, req: LLMRequest) -> LLMResponse:
        if req.temperature != 0.0:
            return await self._inner.complete(req)
        key = _request_key(self.name, req)
        cached = await self._cache.get(key)
        if cached is not None:
            return _decode(cached)
        resp = await self._inner.complete(req)
        await self._cache.set(key, _encode(resp), self._ttl)
        return resp

    def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        return self._inner.stream(req)


class CircuitBreakerProvider:
    """Fails fast when the breaker is open; records every outcome."""

    def __init__(self, inner: _Provider, breaker: CircuitBreaker) -> None:
        self._inner = inner
        self._breaker = breaker
        self.name = inner.name

    async def complete(self, req: LLMRequest) -> LLMResponse:
        if not await self._breaker.allow(self.name):
            raise LLMProviderError(self.name, "circuit open", retryable=False)
        try:
            resp = await self._inner.complete(req)
        except LLMProviderError:
            await self._breaker.record_failure(self.name)
            raise
        await self._breaker.record_success(self.name)
        return resp

    def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        return self._inner.stream(req)


class RetryingProvider:
    """Exponential backoff + jitter, capped attempts, respects Retry-After (LLM10)."""

    def __init__(
        self,
        inner: _Provider,
        *,
        max_attempts: int = 3,
        base_delay_s: float = 0.5,
        max_delay_s: float = 8.0,
        sleep: SleepFn = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._inner = inner
        self._max_attempts = max_attempts
        self._base = base_delay_s
        self._max = max_delay_s
        self._sleep = sleep
        self._rng = rng
        self.name = inner.name

    async def complete(self, req: LLMRequest) -> LLMResponse:
        last_exc: LLMProviderError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._inner.complete(req)
            except LLMProviderError as exc:
                last_exc = exc
                if not exc.retryable or attempt == self._max_attempts:
                    raise
                await self._sleep(self._delay(attempt, exc.retry_after))
        # Unreachable: the loop either returns or raises, but keeps mypy happy.
        raise last_exc if last_exc else LLMProviderError(self.name, "retry loop exhausted")

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        backoff = min(self._max, self._base * (2 ** (attempt - 1)))
        jittered = backoff * (0.5 + 0.5 * self._rng())
        if retry_after is not None:
            return float(max(jittered, retry_after))
        return float(jittered)

    def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        return self._inner.stream(req)


def build_resilient(
    adapter: _Provider,
    *,
    tracer: Tracer,
    cache: Cache,
    breaker: CircuitBreaker,
    max_attempts: int = 3,
    cache_ttl_s: int = 3600,
    sleep: SleepFn = asyncio.sleep,
) -> _Provider:
    """Compose the decorator stack in the documented order around a raw adapter."""
    retrying = RetryingProvider(adapter, max_attempts=max_attempts, sleep=sleep)
    breaking = CircuitBreakerProvider(retrying, breaker)
    caching = CachingProvider(breaking, cache, ttl_s=cache_ttl_s)
    return TracingProvider(caching, tracer)


# --- helpers ---------------------------------------------------------------


def _request_key(name: str, req: LLMRequest) -> str:
    canonical = json.dumps(
        {
            "provider": name,
            "task": req.task.value,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stop": list(req.stop),
            "messages": [[m.role.value, m.content] for m in req.messages],
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"cache:llm:{digest}"


def _encode(resp: LLMResponse) -> bytes:
    return json.dumps(
        {
            "text": resp.text,
            "provider": resp.provider.value,
            "model": resp.model,
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
            "finish_reason": resp.finish_reason,
        }
    ).encode("utf-8")


def _decode(raw: bytes) -> LLMResponse:
    data = json.loads(raw)
    return LLMResponse(
        text=data["text"],
        provider=Provider(data["provider"]),
        model=data["model"],
        prompt_tokens=data["prompt_tokens"],
        completion_tokens=data["completion_tokens"],
        finish_reason=data["finish_reason"],
        cached=True,
    )
