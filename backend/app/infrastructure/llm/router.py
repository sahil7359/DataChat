"""Provider selection (Strategy) with automatic fallback.

The router holds a set of providers (each already wrapped in the resilience
decorator stack) and a ``SelectionPolicy`` that orders them for a given task. It
tries them in order; a provider that fails fast (breaker open) or errors is
skipped and the next is tried. If all are exhausted the caller gets a single
``AllProvidersUnavailableError`` — never a raw stack trace.

Adding a provider is a new entry in the map + a config line; this class does not
change (Open/Closed).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import ClassVar, Protocol

from app.domain.entities import LLMRequest, LLMResponse
from app.domain.ports.llm import LLMProvider
from app.domain.results import AllProvidersUnavailableError, LLMProviderError
from app.domain.value_objects import Provider, TaskKind


class SelectionPolicy(Protocol):
    def order(self, task: TaskKind, available: Sequence[Provider]) -> list[Provider]: ...


class TaskAwarePolicy:
    """Route long/context-heavy tasks to Gemini, short/fast tasks to Groq, then
    fall back through the configured default order. Health is handled by the
    router skipping providers that error (breaker-open providers fail fast)."""

    _PREFER: ClassVar[dict[TaskKind, tuple[Provider, ...]]] = {
        TaskKind.SQL_GEN: (Provider.GEMINI, Provider.GROQ),
        TaskKind.REPAIR: (Provider.GEMINI, Provider.GROQ),
        TaskKind.EXPLAIN: (Provider.GEMINI, Provider.GROQ),
        TaskKind.VERIFY: (Provider.GEMINI, Provider.GROQ),
        TaskKind.CLASSIFY: (Provider.GROQ, Provider.GEMINI),
        TaskKind.CLARIFY: (Provider.GROQ, Provider.GEMINI),
    }

    def __init__(self, default_order: Sequence[Provider]) -> None:
        self._default = tuple(default_order)

    def order(self, task: TaskKind, available: Sequence[Provider]) -> list[Provider]:
        preferred = self._PREFER.get(task, self._default)
        available_set = set(available)
        ordered: list[Provider] = []
        for provider in (*preferred, *self._default):
            if provider in available_set and provider not in ordered:
                ordered.append(provider)
        # Anything available but unmentioned still gets a turn (last resort).
        for provider in available:
            if provider not in ordered:
                ordered.append(provider)
        return ordered


class ProviderRouter:
    """A composite ``LLMProvider`` that fans out to the best available vendor."""

    def __init__(
        self,
        providers: Mapping[Provider, LLMProvider],
        policy: SelectionPolicy,
    ) -> None:
        if not providers:
            raise ValueError("ProviderRouter needs at least one provider")
        self._providers = dict(providers)
        self._policy = policy
        self.name = "router"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        order = self._policy.order(req.task, list(self._providers))
        errors: list[str] = []
        for provider in order:
            try:
                return await self._providers[provider].complete(req)
            except LLMProviderError as exc:
                errors.append(str(exc))
                continue
        raise AllProvidersUnavailableError("; ".join(errors) or "no providers configured")

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        order = self._policy.order(req.task, list(self._providers))
        errors: list[str] = []
        for provider in order:
            try:
                async for token in self._providers[provider].stream(req):
                    yield token
                return
            except LLMProviderError as exc:
                errors.append(str(exc))
                continue
        raise AllProvidersUnavailableError("; ".join(errors) or "no providers configured")
