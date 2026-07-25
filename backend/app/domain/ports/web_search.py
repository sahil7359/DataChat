"""Web search port — the escape hatch when a question has no answer in the
governed datasets.

This is deliberately a narrow, separate port: web results are *untrusted* and must
never feed the SQL path. An adapter returns snippets; the web-answer node
summarises them with a hardened prompt and always attributes sources.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import WebResult


class WebSearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int = 5) -> tuple[WebResult, ...]: ...
