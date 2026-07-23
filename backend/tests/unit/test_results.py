import pytest

from app.domain.results import (
    Err,
    ExecutionError,
    GuardrailError,
    Ok,
    Result,
    ResultError,
)


def test_ok_carries_value_and_maps() -> None:
    result: Result[int, str] = Ok(2)

    assert result.is_ok()
    assert not result.is_err()
    assert result.unwrap() == 2
    assert result.map(lambda n: n * 3).unwrap() == 6
    assert result.unwrap_or(99) == 2


def test_err_short_circuits_map_and_unwrap_raises() -> None:
    result: Result[int, str] = Err("boom")

    assert result.is_err()
    assert result.map(lambda n: n * 3) == Err("boom")
    assert result.unwrap_or(99) == 99
    with pytest.raises(ResultError):
        result.unwrap()


def test_map_err_only_touches_err() -> None:
    assert Ok(1).map_err(lambda e: f"!{e}") == Ok(1)
    assert Err("x").map_err(lambda e: f"!{e}") == Err("!x")


def test_pattern_matching_reads_cleanly() -> None:
    def describe(r: Result[int, str]) -> str:
        match r:
            case Ok(value):
                return f"ok:{value}"
            case Err(error):
                return f"err:{error}"

    assert describe(Ok(5)) == "ok:5"
    assert describe(Err("nope")) == "err:nope"


def test_typed_errors_are_frozen_value_objects() -> None:
    violation = GuardrailError(message="write blocked", rule="ReadOnlyRule")
    exec_err = ExecutionError(message="timeout", code="57014")

    assert violation.rule == "ReadOnlyRule"
    assert exec_err.code == "57014"
    with pytest.raises(AttributeError):
        violation.rule = "other"  # type: ignore[misc]
