from app.application.agent.charts import build_chart_spec, is_valid_chart_spec
from app.domain.entities import ExecutionResult


def _result(columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...]) -> ExecutionResult:
    return ExecutionResult(columns=columns, rows=rows, row_count=len(rows), elapsed_ms=1)


def test_bar_chart_for_category_and_measure() -> None:
    spec = build_chart_spec("top emitters", _result(("name", "co2"), (("Qatar", 37.6),)))
    assert spec is not None
    assert spec.spec["mark"] == "bar"


def test_line_chart_for_temporal_first_column() -> None:
    spec = build_chart_spec("co2 over time", _result(("year", "co2"), ((2021, 10.0), (2022, 11.0))))
    assert spec is not None
    assert spec.spec["mark"] == "line"


def test_no_chart_when_single_column() -> None:
    assert build_chart_spec("q", _result(("n",), ((1,),))) is None


def test_no_chart_when_empty() -> None:
    assert build_chart_spec("q", _result(("a", "b"), ())) is None


def test_no_chart_when_measure_not_numeric() -> None:
    spec = build_chart_spec("q", _result(("a", "b"), (("x", "not-a-number"),)))
    assert spec is None


def test_validator_rejects_malformed_specs() -> None:
    assert not is_valid_chart_spec({"mark": "bar"})  # missing $schema
    assert not is_valid_chart_spec(
        {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "mark": "pie",
            "data": {"values": []},
            "encoding": {"x": {}, "y": {}},
        }
    )  # disallowed mark
    assert not is_valid_chart_spec(
        {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "mark": "bar",
            "data": {},
            "encoding": {"x": {}, "y": {}},
        }
    )  # data has no values
