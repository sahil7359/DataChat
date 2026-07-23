"""Semantic-layer retrieval port (RAG-to-SQL grounding)."""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import RetrievedContext


class SchemaCatalog(Protocol):
    async def retrieve(self, question: str, k: int = 8) -> RetrievedContext:
        """Return the top-k relevant tables/columns + few-shot examples for a question."""
        ...
