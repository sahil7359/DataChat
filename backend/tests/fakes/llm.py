"""In-memory LLM and embedding fakes — deterministic, no network, no keys."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Mapping

from app.domain.entities import LLMRequest, LLMResponse
from app.domain.results import LLMProviderError
from app.domain.value_objects import Provider, TaskKind, Vector


class FakeLLMProvider:
    """Scriptable provider. Returns a canned answer per task (or a default),
    records every request, and can be told to fail to exercise fallback."""

    def __init__(
        self,
        name: str = "fake",
        provider: Provider = Provider.GEMINI,
        *,
        responses: Mapping[TaskKind, str] | None = None,
        default: str = "SELECT 1",
        fail: bool = False,
    ) -> None:
        self.name = name
        self._provider = provider
        self._responses = dict(responses or {})
        self._default = default
        self._fail = fail
        self.calls: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        if self._fail:
            raise LLMProviderError(self.name, "forced failure", retryable=True)
        text = self._responses.get(req.task, self._default)
        return LLMResponse(
            text=text,
            provider=self._provider,
            model=f"{self.name}-model",
            prompt_tokens=8,
            completion_tokens=len(text.split()),
            finish_reason="stop",
        )

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        self.calls.append(req)
        if self._fail:
            raise LLMProviderError(self.name, "forced failure", retryable=True)
        text = self._responses.get(req.task, self._default)
        for token in text.split(" "):
            yield token + " "


class FakeEmbeddingProvider:
    """Deterministic embeddings derived from a hash, so tests are reproducible."""

    def __init__(self, name: str = "fake-embed", dim: int = 768) -> None:
        self.name = name
        self.dim = dim

    async def embed(self, text: str) -> Vector:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        counter = 0
        while len(values) < self.dim:
            block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for i in range(0, len(block), 4):
                if len(values) >= self.dim:
                    break
                n = int.from_bytes(block[i : i + 4], "big")
                values.append((n / 2**32) * 2.0 - 1.0)
            counter += 1
        return Vector.of(values)
