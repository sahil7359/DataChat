"""Web search adapters behind the ``WebSearchProvider`` port.

- ``MockWebSearchProvider`` — deterministic, offline; the keyless default and what
  the tests run against.
- ``DdgsWebSearchProvider`` — keyless metasearch via the ``ddgs`` library, run in a
  worker thread since the library is synchronous.

An Ollama-hosted web search (ollama.com/api/web_search, needs a free key) can be
added as another adapter without touching callers — the port stays the same.
"""

from __future__ import annotations

import asyncio

from app.domain.entities import WebResult
from app.infrastructure.observability.logging import get_logger

_log = get_logger("web.search")


class MockWebSearchProvider:
    """Returns a couple of canned, clearly-fake hits so the fallback path is
    exercised without any network access."""

    async def search(self, query: str, *, max_results: int = 5) -> tuple[WebResult, ...]:
        return (
            WebResult(
                title=f"Example result for '{query}'",
                url="https://example.org/a",
                snippet="A representative snippet used for offline development and tests.",
            ),
            WebResult(
                title="Another source",
                url="https://example.org/b",
                snippet="A second snippet so summaries have more than one source to cite.",
            ),
        )[:max_results]


class DdgsWebSearchProvider:
    """Keyless DuckDuckGo/metasearch via ``ddgs`` (sync lib → run off the loop)."""

    async def search(self, query: str, *, max_results: int = 5) -> tuple[WebResult, ...]:
        try:
            return await asyncio.to_thread(self._search, query, max_results)
        except Exception:  # network/rate-limit failures degrade to "no web result"
            _log.warning("web_search_failed")
            return ()

    @staticmethod
    def _search(query: str, max_results: int) -> tuple[WebResult, ...]:
        from ddgs import DDGS

        hits = DDGS().text(query, max_results=max_results)
        return tuple(
            WebResult(
                title=str(h.get("title", "")),
                url=str(h.get("href", "")),
                snippet=str(h.get("body", "")),
            )
            for h in hits
        )
