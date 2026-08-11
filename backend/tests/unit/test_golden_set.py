"""Structural guards on the golden set.

These are cheap invariants that stop the eval from quietly becoming meaningless:
leakage from the few-shot examples, a set with no refusal cases, or a case whose
gold SQL would be rejected by the very guardrail the agent must satisfy.
"""

from __future__ import annotations

from app.application.services.golden_set import GOLDEN_SET
from app.infrastructure.sql.validator import SqlValidatorChain
from ingestion.definitions import DEFINITIONS


def test_no_question_leaks_from_the_few_shot_examples() -> None:
    """A golden question that is verbatim a retrieved few-shot example measures
    copying, not reasoning — the example lands in the prompt for that question."""
    few_shot = {
        example.question.strip().lower()
        for definition in DEFINITIONS.values()
        for example in definition.examples
    }
    leaked = [c.question for c in GOLDEN_SET if c.question.strip().lower() in few_shot]
    assert not leaked, f"golden questions duplicate few-shot examples: {leaked}"


def test_questions_are_unique() -> None:
    questions = [c.question.strip().lower() for c in GOLDEN_SET]
    assert len(questions) == len(set(questions))


def test_set_covers_both_answerable_and_refusal_cases() -> None:
    answerable = [c for c in GOLDEN_SET if not c.expect_refusal]
    refusals = [c for c in GOLDEN_SET if c.expect_refusal]
    assert len(answerable) >= 20, "too few answerable cases for a stable mean"
    assert len(refusals) >= 4, "refusal coverage is the point of the negative cases"


def test_gold_sql_passes_the_same_guardrail_the_agent_must_pass() -> None:
    """Gold SQL is executed directly, bypassing validation. If a gold query could
    not itself clear the guardrail, the comparison is unfair to the agent."""
    validator = SqlValidatorChain(row_cap=1000)
    bad = [
        (c.question, validator.validate(c.gold_sql).results)
        for c in GOLDEN_SET
        if not c.expect_refusal and not validator.validate(c.gold_sql).ok
    ]
    assert not bad, f"gold SQL fails the guardrail: {bad}"


def test_refusal_cases_carry_no_gold_sql() -> None:
    for case in GOLDEN_SET:
        if case.expect_refusal:
            assert case.gold_sql == ""
            assert case.notes, "a refusal case must say why it is unanswerable"
