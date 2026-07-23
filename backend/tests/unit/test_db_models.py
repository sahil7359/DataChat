"""Verify the ORM structure matches the data design (Schema.md) without a DB."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Table

from app.infrastructure.db import models
from app.infrastructure.db.base import ANALYTICS_SCHEMA, APP_SCHEMA, EMBEDDING_DIM, Base

APP_TABLES = {
    "conversations",
    "turns",
    "runs",
    "agent_actions",
    "datasets",
    "semantic_tables",
    "semantic_columns",
    "few_shot_examples",
    "eval_cases",
    "eval_runs",
    "eval_case_results",
}
ANALYTICS_TABLES = {"countries", "wdi_indicators", "wdi_values", "owid_co2"}


def _table(model: Any) -> Table:
    return cast(Table, model.__table__)


def _tables_in(schema: str) -> set[str]:
    return {t.name for t in Base.metadata.sorted_tables if t.schema == schema}


def _check_constraint_names(model: Any) -> set[str]:
    return {
        str(c.name)
        for c in _table(model).constraints
        if c.__class__.__name__ == "CheckConstraint" and c.name
    }


def test_all_app_tables_present_and_scoped() -> None:
    assert _tables_in(APP_SCHEMA) == APP_TABLES


def test_all_analytics_tables_present_and_scoped() -> None:
    assert _tables_in(ANALYTICS_SCHEMA) == ANALYTICS_TABLES


def test_turn_and_run_have_check_constraints() -> None:
    assert "ck_turns_role_valid" in _check_constraint_names(models.Turn)
    assert "ck_runs_status_valid" in _check_constraint_names(models.Run)


def test_embedding_columns_have_the_configured_dimension() -> None:
    for model in (models.SemanticTable, models.SemanticColumn, models.FewShotExample):
        col = _table(model).c["embedding"]
        assert col.type.__class__.__name__.upper() == "VECTOR"
        assert getattr(col.type, "dim", None) == EMBEDDING_DIM


def test_fact_tables_use_composite_primary_keys() -> None:
    wdi_pk = [c.name for c in _table(models.WdiValue).primary_key.columns]
    co2_pk = [c.name for c in _table(models.OwidCo2).primary_key.columns]
    assert wdi_pk == ["country_iso3", "indicator_code", "year"]
    assert co2_pk == ["country_iso3", "year"]


def test_common_filter_indexes_exist() -> None:
    wdi_indexes = {ix.name for ix in _table(models.WdiValue).indexes}
    co2_indexes = {ix.name for ix in _table(models.OwidCo2).indexes}
    assert "ix_wdi_values_indicator_year" in wdi_indexes
    assert "ix_owid_co2_country_year" in co2_indexes
