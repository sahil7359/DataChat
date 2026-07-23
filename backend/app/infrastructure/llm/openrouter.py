"""Adapter for OpenRouter (OpenAI-compatible, emergency-only, off by default).

Kept behind ``openrouter_enabled`` so the system stays strictly $0 — the free
OpenRouter tier is tiny (50 req/day) and only wired as a last resort."""

from __future__ import annotations

import httpx

from app.domain.value_objects import Provider
from app.infrastructure.llm.openai_compatible import OpenAICompatibleAdapter


class OpenRouterAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        model: str = "meta-llama/llama-3.3-70b-instruct:free",
        timeout_s: float = 30.0,
    ) -> None:
        super().__init__(
            Provider.OPENROUTER,
            client,
            api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            timeout_s=timeout_s,
        )
