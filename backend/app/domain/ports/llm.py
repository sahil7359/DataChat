"""LLM and embedding ports.

Any implementation — a real vendor adapter, the resilient decorator stack, or a
test fake — is interchangeable behind these Protocols (Liskov). Adding a vendor
is a new adapter + a config line; callers never change (Open/Closed).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.domain.entities import LLMRequest, LLMResponse
from app.domain.value_objects import Vector


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Return a completion, or raise ``LLMProviderError`` on failure."""
        ...

    def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        """Yield completion text deltas (used by the explain node)."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    async def embed(self, text: str) -> Vector: ...
