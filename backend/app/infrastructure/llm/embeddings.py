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
import re

import httpx

from app.domain.results import LLMProviderError
from app.domain.value_objects import Vector

_TOKEN = re.compile(r"[a-z0-9]+")

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
    """Feature-hashing bag-of-words embedding for offline/dev (the hashing-trick,
    à la sklearn's HashingVectorizer). Deterministic, dependency-free, and — unlike
    hashing the whole string — *lexically meaningful*: texts that share tokens land
    near each other, so retrieval actually ranks. A real model (e.g. BGE-small)
    can replace it behind the same port."""

    def __init__(self, *, dim: int = 768) -> None:
        self.name = "local-hash-embed"
        self.dim = dim

    async def embed(self, text: str) -> Vector:
        values = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign
        return Vector.of(values)
