"""Shared implementation for OpenAI-compatible chat endpoints (Groq, OpenRouter).

Both speak the same ``/chat/completions`` contract, so the adapters differ only
in base URL, auth header, and default model — a textbook case for a shared base
with thin subclasses (Adapter + a touch of Template Method).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.domain.entities import LLMRequest, LLMResponse
from app.domain.results import LLMProviderError
from app.domain.value_objects import Provider
from app.infrastructure.llm.base_adapter import BaseHttpAdapter


class OpenAICompatibleAdapter(BaseHttpAdapter):
    def __init__(
        self,
        provider: Provider,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        base_url: str,
        model: str,
        timeout_s: float = 30.0,
    ) -> None:
        super().__init__(provider.value, client, timeout_s)
        self._provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def complete(self, req: LLMRequest) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
        }
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        if req.stop:
            payload["stop"] = list(req.stop)

        body = await self._post_json(
            f"{self._base_url}/chat/completions",
            headers={
                "authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            payload=payload,
        )
        return self._parse(body)

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        resp = await self.complete(req)
        for token in resp.text.split(" "):
            yield token + " "

    def _parse(self, body: dict[str, object]) -> LLMResponse:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderError(self.name, "no choices in response", retryable=False)
        first = choices[0]
        message = first.get("message", {}) if isinstance(first, dict) else {}
        text = str(message.get("content", "")) if isinstance(message, dict) else ""
        usage = body.get("usage", {})
        usage = usage if isinstance(usage, dict) else {}
        return LLMResponse(
            text=text,
            provider=self._provider,
            model=self._model,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            finish_reason=str(first.get("finish_reason", "")) if isinstance(first, dict) else None,
        )
