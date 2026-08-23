"""Adapter for the Groq chat API (OpenAI-compatible, fast fallback provider)."""

from __future__ import annotations

import httpx

from app.domain.value_objects import Provider
from app.infrastructure.llm.openai_compatible import OpenAICompatibleAdapter


class GroqAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        model: str = "openai/gpt-oss-120b",
        timeout_s: float = 30.0,
    ) -> None:
        super().__init__(
            Provider.GROQ,
            client,
            api_key,
            base_url="https://api.groq.com/openai/v1",
            model=model,
            timeout_s=timeout_s,
        )
