"""Adapter for the Google Gemini generateContent API (Design.md §5)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.domain.entities import LLMRequest, LLMResponse, MessageRole
from app.domain.results import LLMProviderError
from app.domain.value_objects import Provider
from app.infrastructure.llm.base_adapter import BaseHttpAdapter

_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiAdapter(BaseHttpAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        *,
        model: str = "gemini-1.5-flash",
        timeout_s: float = 30.0,
    ) -> None:
        super().__init__(Provider.GEMINI.value, client, timeout_s)
        self._api_key = api_key
        self._model = model

    async def complete(self, req: LLMRequest) -> LLMResponse:
        payload = _to_gemini_payload(req)
        url = f"{_BASE}/models/{self._model}:generateContent"
        body = await self._post_json(
            url,
            headers={"x-goog-api-key": self._api_key, "content-type": "application/json"},
            payload=payload,
        )
        return _parse_gemini_response(body, self._model)

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        # Whitespace-chunked delegation to complete(). True token streaming is a
        # provider-specific SSE format; the explain node only needs incremental
        # deltas, which this satisfies without a second code path to secure.
        resp = await self.complete(req)
        for token in resp.text.split(" "):
            yield token + " "


def _to_gemini_payload(req: LLMRequest) -> dict[str, object]:
    contents: list[dict[str, object]] = []
    system_parts: list[dict[str, str]] = []
    for msg in req.messages:
        if msg.role is MessageRole.SYSTEM:
            system_parts.append({"text": msg.content})
        else:
            role = "model" if msg.role is MessageRole.ASSISTANT else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})

    generation: dict[str, object] = {"temperature": req.temperature}
    if req.max_tokens is not None:
        generation["maxOutputTokens"] = req.max_tokens
    if req.stop:
        generation["stopSequences"] = list(req.stop)

    payload: dict[str, object] = {"contents": contents, "generationConfig": generation}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    return payload


def _parse_gemini_response(body: dict[str, object], model: str) -> LLMResponse:
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise LLMProviderError(Provider.GEMINI.value, "no candidates in response", retryable=False)
    first = candidates[0]
    text = _extract_text(first)
    usage = body.get("usageMetadata", {})
    usage = usage if isinstance(usage, dict) else {}
    return LLMResponse(
        text=text,
        provider=Provider.GEMINI,
        model=model,
        prompt_tokens=int(usage.get("promptTokenCount", 0)),
        completion_tokens=int(usage.get("candidatesTokenCount", 0)),
        finish_reason=str(first.get("finishReason", "")) if isinstance(first, dict) else None,
    )


def _extract_text(candidate: object) -> str:
    if not isinstance(candidate, dict):
        return ""
    content = candidate.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
