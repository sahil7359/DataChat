"""Adapter for a self-hosted Ollama server (Adapter pattern).

Ollama exposes an OpenAI-compatible API, so this reuses the shared base. The
important addition is auth: Ollama itself is unauthenticated, so when it's exposed
over a tunnel the endpoint is fronted by a proxy / Cloudflare Access that requires
a bearer token. This adapter always sends that token, so only the backend that
holds it can reach the GPU — "Ollama has its own security, no misuse" (LLM06).
"""

from __future__ import annotations

import httpx

from app.domain.value_objects import Provider
from app.infrastructure.llm.openai_compatible import OpenAICompatibleAdapter


class OllamaAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.2",
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__(
            Provider.OLLAMA,
            client,
            api_key,
            base_url=base_url,
            model=model,
            timeout_s=timeout_s,
        )
