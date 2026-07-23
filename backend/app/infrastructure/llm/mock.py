"""Runtime mock provider used when ``USE_MOCKS`` is set.

This is what lets the whole app run end-to-end with no API keys (FR-25): a
deterministic provider that returns plausible, seed-compatible answers per task.
It lives in infrastructure (not tests) because it is a real runtime adapter for
the mock configuration, selected by the composition root.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from app.domain.entities import LLMRequest, LLMResponse
from app.domain.value_objects import Provider, TaskKind

_DEFAULTS: Mapping[TaskKind, str] = {
    TaskKind.SQL_GEN: (
        "SELECT country_iso3, co2_per_capita FROM owid_co2 "
        "WHERE year = 2022 ORDER BY co2_per_capita DESC LIMIT 10"
    ),
    TaskKind.REPAIR: (
        "SELECT country_iso3, co2_per_capita FROM owid_co2 "
        "WHERE year = 2022 AND co2_per_capita IS NOT NULL "
        "ORDER BY co2_per_capita DESC LIMIT 10"
    ),
    TaskKind.EXPLAIN: (
        "Based on the returned rows, the listed countries had the highest CO2 per "
        "capita in 2022, with the top entry clearly ahead of the rest."
    ),
    TaskKind.VERIFY: "OK",
    TaskKind.CLARIFY: "CLEAR",
    TaskKind.CLASSIFY: "in_scope",
}


class MockLLMProvider:
    """Deterministic, offline provider. Configurable so tests/graph runs can
    inject specific answers."""

    def __init__(
        self,
        *,
        responses: Mapping[TaskKind, str] | None = None,
        provider: Provider = Provider.GEMINI,
    ) -> None:
        self.name = "mock"
        self._responses = {**_DEFAULTS, **(responses or {})}
        self._provider = provider

    async def complete(self, req: LLMRequest) -> LLMResponse:
        text = self._responses.get(req.task, "SELECT 1")
        return LLMResponse(
            text=text,
            provider=self._provider,
            model="mock-model",
            prompt_tokens=16,
            completion_tokens=len(text.split()),
            finish_reason="stop",
        )

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        text = self._responses.get(req.task, "")
        for token in text.split(" "):
            yield token + " "
