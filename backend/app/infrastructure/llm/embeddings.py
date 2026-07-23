"""Embedding providers.

Gemini is the production embedder (shares the free quota, pre-embedded offline at
ingestion time so it costs one call per query). The local hash embedder is a
deterministic, dependency-free stand-in for offline/dev and the mock path — it
keeps the retrieval pipeline exercisable without pulling a heavyweight model onto
the tiny host. Swapping in a real local model (e.g. BGE-small) is a new adapter
behind the same port, no core changes.
"""

from __future__ import annotations

import hashlib

import httpx

from app.domain.results import LLMProviderError
from app.domain.value_objects import Vector

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiEmbeddingAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        model: str = "text-embedding-004",
        dim: int = 768,
        timeout_s: float = 30.0,
    ) -> None:
        self.name = "gemini-embed"
        self.dim = dim
        self._client = client
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_s

    async def embed(self, text: str) -> Vector:
        url = f"{_GEMINI_BASE}/models/{self._model}:embedContent"
        payload = {
            "model": f"models/{self._model}",
            "content": {"parts": [{"text": text}]},
        }
        try:
            resp = await self._client.post(
                url,
                headers={"x-goog-api-key": self._api_key, "content-type": "application/json"},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError(self.name, f"embed transport error: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMProviderError(
                self.name, f"embed failed {resp.status_code}", retryable=resp.status_code >= 500
            )
        values = resp.json().get("embedding", {}).get("values", [])
        if not values:
            raise LLMProviderError(self.name, "empty embedding", retryable=False)
        return Vector.of(values)


class LocalHashEmbeddingProvider:
    """Deterministic hash-based embedding for offline/dev. Not semantically
    meaningful, but stable and free — good enough for a tiny curated corpus where
    top-k >= corpus size returns the whole (relevant) set anyway."""

    def __init__(self, *, dim: int = 768) -> None:
        self.name = "local-hash-embed"
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
