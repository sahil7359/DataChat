"""The deterministic out-of-scope gate.

Refusal accuracy was the weakest published number (0.80). The failure was not the
model being careless — it was a question about 2030 producing
``SUM(co2)/SUM(pop) WHERE year = 2030``, which over zero rows returns one NULL
row, so the pipeline believed it had an answer. Two fixes are pinned here: decide
scope before generating SQL, and stop treating an all-NULL row as data.

The gate must be conservative. A false refusal on a question we *can* answer is
worse than a miss, because a miss still falls through to the normal path.
"""

from __future__ import annotations

import pytest

from app.domain.entities import ExecutionResult
from app.domain.scope import DataScope
from ingestion.definitions import seed_scope


@pytest.fixture(scope="module")
def scope() -> DataScope:
    return seed_scope()


@pytest.mark.parametrize(
    "question",
    [
        "What was Kenya's CO2 per capita in 2022?",
        "What is the GDP of Nigeria and Kenya?",
        "How does Vietnam compare to Thailand?",
    ],
)
def test_refuses_a_country_we_did_not_load(scope: DataScope, question: str) -> None:
    verdict = scope.check(question)
    assert verdict is not None
    assert verdict.reason == "country_not_loaded"


@pytest.mark.parametrize(
    "question",
    [
        "What will global CO2 per capita be in 2030?",
        "CO2 in 2015?",
        "Show me GDP per capita in 1999",
    ],
)
def test_refuses_a_year_outside_the_loaded_range(scope: DataScope, question: str) -> None:
    verdict = scope.check(question)
    assert verdict is not None
    assert verdict.reason == "year_out_of_range"


@pytest.mark.parametrize(
    "question",
    [
        # Loaded countries, including the colloquial forms a visitor types.
        "Compare CO2 per capita between the United States and China in 2022.",
        "What was the USA CO2 per capita in 2022?",
        "How does the UK compare to France?",
        # No country or year named at all.
        "How many countries are in the dataset?",
        "Show me the best countries.",
        # Loaded years.
        "How much did Qatar's CO2 per capita change between 2021 and 2022?",
        "Which 5 countries had the highest CO2 per capita in 2022?",
        # An indicator we do not carry: deliberately NOT caught here. The
        # vocabulary is open, so a keyword list would refuse phrasings we do
        # support. It falls through to the model and the emptiness check.
        "What is the adult literacy rate in India?",
    ],
)
def test_allows_anything_it_cannot_positively_rule_out(scope: DataScope, question: str) -> None:
    assert scope.check(question) is None


def test_a_mixed_year_question_is_allowed(scope: DataScope) -> None:
    """Naming one loaded year alongside an unloaded one is a trend question we can
    partially answer — refusing it outright would be worse than answering the part
    we hold."""
    assert scope.check("How did CO2 change from 2021 to 2030?") is None


def test_bare_numbers_are_not_read_as_years(scope: DataScope) -> None:
    for question in ("Show me the top 5 countries", "Which country has over 100 million people?"):
        assert scope.check(question) is None


def test_the_message_names_the_boundary(scope: DataScope) -> None:
    described = scope.describe()
    assert "15 countries" in described
    assert "2021, 2022" in described
    assert "Qatar" in described  # a loaded country is listed by name
    assert "World Bank" in described  # the measures are named


# --- the all-NULL row ------------------------------------------------------


def _result(rows: tuple[tuple[object, ...], ...]) -> ExecutionResult:
    return ExecutionResult(columns=("a",), rows=rows, row_count=len(rows), elapsed_ms=1)


def test_an_aggregate_over_no_rows_counts_as_empty() -> None:
    """SUM() over zero matching rows returns one NULL. That is not an answer."""
    assert _result(((None,),)).is_empty()


def test_a_real_zero_is_not_empty() -> None:
    """COUNT(*) legitimately returns 0 — a number, not an absence."""
    assert not _result(((0,),)).is_empty()


def test_a_partially_null_row_is_not_empty() -> None:
    result = ExecutionResult(
        columns=("name", "value"), rows=(("Kenya", None),), row_count=1, elapsed_ms=1
    )
    assert not result.is_empty()


def test_no_rows_is_empty() -> None:
    assert _result(()).is_empty()
