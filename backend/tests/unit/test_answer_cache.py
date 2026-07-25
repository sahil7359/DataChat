"""The whole-answer cache: exact-normalised questions replay a stored answer and
never re-run the graph, while distinct questions stay independent."""

from __future__ import annotations

import pytest

from app.application.agent.events import AgentEvent, RowsEvent, SqlEvent
from app.application.services.answer_cache import (
    answer_cache_key,
    deserialize_answer,
    normalize_question,
    serialize_answer,
)
from app.domain.entities import ExecutionResult, Plan
from app.domain.value_objects import ChartSpec
from tests.fakes.cache import InMemoryCache
from tests.fakes.graph import ROWS, build_service
from tests.fakes.sql import FakeQueryExecutor


def test_normalisation_folds_case_whitespace_and_trailing_punctuation() -> None:
    a = normalize_question("  Top 10 countries by CO2?  ")
    b = normalize_question("top 10 countries by co2")
    assert a == b
    assert answer_cache_key("Top 10 countries by CO2?") == answer_cache_key(
        "top   10 countries by co2"
    )


def test_distinct_questions_get_distinct_keys() -> None:
    assert answer_cache_key("top 5 by gdp") != answer_cache_key("top 10 by gdp")
    assert answer_cache_key("gdp in 2022") != answer_cache_key("gdp in 2021")


def test_serialize_skips_errors_and_empty_answers() -> None:
    assert serialize_answer({"error_code": "boom", "execution": ROWS}) is None
    assert serialize_answer({"execution": None}) is None


def test_serialize_deserialize_round_trip() -> None:
    raw = serialize_answer(
        {
            "plan": Plan(steps=("a", "b"), target_tables=("owid_co2",)),
            "candidate_sql": "SELECT 1",
            "execution": ExecutionResult(
                columns=("c",), rows=((1,), (2,)), row_count=2, elapsed_ms=4, truncated=False
            ),
            "explanation": "because",
            "chart_spec": ChartSpec(spec={"mark": "bar"}),
        }
    )
    assert raw is not None
    update = deserialize_answer(raw)
    assert update["candidate_sql"] == "SELECT 1"
    assert update["execution"].row_count == 2
    assert update["execution"].rows == ((1,), (2,))
    assert update["plan"].target_tables == ("owid_co2",)
    assert update["chart_spec"].spec == {"mark": "bar"}


async def _collect(events: object) -> list[AgentEvent]:
    return [e async for e in events]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_repeat_question_replays_without_executing() -> None:
    cache = InMemoryCache()
    executor = FakeQueryExecutor(result=ROWS)
    service = build_service(executor=executor, answer_cache=cache)

    first = await _collect(service.stream("Top 10 countries by CO2 per capita in 2022"))
    assert len(executor.executed) == 1
    assert any(isinstance(e, RowsEvent) for e in first)

    # A case/whitespace/punctuation variant is the same question — served from cache.
    second = await _collect(service.stream("  top 10 countries by CO2 per capita in 2022?  "))
    assert len(executor.executed) == 1  # graph did NOT run again
    rows = [e for e in second if isinstance(e, RowsEvent)]
    assert rows and rows[0].rows == ROWS.rows
    assert any(isinstance(e, SqlEvent) for e in second)


@pytest.mark.asyncio
async def test_distinct_question_is_not_served_from_cache() -> None:
    cache = InMemoryCache()
    executor = FakeQueryExecutor(result=ROWS)
    service = build_service(executor=executor, answer_cache=cache)

    await _collect(service.stream("question one"))
    await _collect(service.stream("a completely different question"))
    assert len(executor.executed) == 2  # both ran the graph
