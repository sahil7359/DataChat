"""Shared HTTP plumbing for vendor adapters.

Centralises timeout handling and, crucially, the mapping from HTTP failure modes
to a single ``LLMProviderError`` the router understands. 429/5xx/timeouts are
marked retryable; 4xx (bad request / auth) are not — no point retrying a request
the server will keep rejecting (LLM10: bounded, purposeful retries).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.domain.results import LLMProviderError


class BaseHttpAdapter:
    def __init__(self, name: str, client: httpx.AsyncClient, timeout_s: float) -> None:
        self.name = name
        self._client = client
        self._timeout = timeout_s

    async def _post_json(
        self, url: str, *, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            resp = await self._client.post(
                url, headers=headers, json=payload, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                self.name, f"timeout after {self._timeout}s", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(self.name, f"transport error: {exc}", retryable=True) from exc

        self._raise_for_status(resp)
        body: dict[str, Any] = resp.json()
        return body

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise LLMProviderError(
                self.name,
                "rate limited (429)",
                retryable=True,
                retry_after=_parse_retry_after(resp),
            )
        if resp.status_code >= 500:
            raise LLMProviderError(self.name, f"server error {resp.status_code}", retryable=True)
        if resp.status_code >= 400:
            # Auth/validation errors won't fix themselves on retry.
            raise LLMProviderError(
                self.name,
                f"client error {resp.status_code}",
                retryable=False,
            )


def _parse_retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
