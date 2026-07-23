from datetime import UTC, datetime

from app.domain.entities import (
    ExecutionResult,
    LLMResponse,
    RetrievedContext,
    RuleResult,
    TableDoc,
    ValidationResult,
)
from app.domain.value_objects import Provider, Vector


def test_validation_result_surfaces_first_violation() -> None:
    result = ValidationResult(
        ok=False,
        sql="DELETE FROM t",
        results=(
            RuleResult("SingleStatementRule", True),
            RuleResult("ReadOnlyRule", False, "write statement"),
        ),
    )

    assert result.violations == (RuleResult("ReadOnlyRule", False, "write statement"),)
    assert result.first_violation is not None
    assert result.first_violation.rule == "ReadOnlyRule"


def test_validation_result_ok_has_no_violations() -> None:
    result = ValidationResult(ok=True, sql="SELECT 1", results=(RuleResult("r", True),))
    assert result.violations == ()
    assert result.first_violation is None


def test_execution_result_empty_detection() -> None:
    empty = ExecutionResult(columns=("n",), rows=(), row_count=0, elapsed_ms=3)
    filled = ExecutionResult(columns=("n",), rows=((1,),), row_count=1, elapsed_ms=3)
    assert empty.is_empty()
    assert not filled.is_empty()


def test_retrieved_context_empty_detection() -> None:
    assert RetrievedContext().is_empty()
    assert not RetrievedContext(tables=(TableDoc("t", "d"),)).is_empty()


def test_llm_response_totals_tokens() -> None:
    resp = LLMResponse(
        text="hi",
        provider=Provider.GROQ,
        model="m",
        prompt_tokens=10,
        completion_tokens=5,
    )
    assert resp.total_tokens == 15


def test_vector_dimension() -> None:
    v = Vector.of([0.1, 0.2, 0.3])
    assert v.dim == 3
    assert v.values == (0.1, 0.2, 0.3)


def test_entities_are_immutable() -> None:
    doc = TableDoc("owid_co2", "emissions")
    try:
        doc.description = "x"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("frozen dataclass should not allow mutation")
    # timestamps used by callers are timezone-aware UTC by convention
    assert datetime.now(UTC).tzinfo is UTC
