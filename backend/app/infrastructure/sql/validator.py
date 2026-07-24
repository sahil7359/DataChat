"""SQL guardrail: a Chain of Responsibility over the sqlglot AST.

Each rule is an independent link with a uniform ``check(ctx) -> RuleResult``, so
rules can be added/reordered without touching the others (SRP + Open/Closed). The
chain short-circuits on the first hard failure. This is the first of two
independent "no writes ever" layers; the read-only DB role is the second.

Working on the parsed AST (not regexes) is deliberate: comment tricks, casing,
whitespace, and stacked statements can't sneak past a real parser the way they
slip past string matching.
"""

from __future__ import annotations

from typing import Protocol

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.domain.entities import RuleResult, ValidationResult

_DIALECT = "postgres"

# Any of these anywhere in the tree means the statement can mutate data or schema
# — including inside a data-modifying CTE (WITH x AS (DELETE ...) ...).
_WRITE_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Copy,  # COPY ... FROM PROGRAM is remote code execution
    exp.Set,
    exp.Use,
    exp.Command,  # VACUUM, CALL, and anything else sqlglot leaves opaque
)

_ANALYTICS_TABLES = frozenset({"countries", "wdi_indicators", "wdi_values", "owid_co2"})
_BLOCKED_SCHEMAS = frozenset({"pg_catalog", "information_schema", "app"})
_BLOCKED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_exec",
        "query_to_xml",
        "current_setting",
        "set_config",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "txid_current",
        "version",
        "current_database",
        "inet_server_addr",
    }
)


class SqlContext:
    def __init__(self, sql: str, expression: exp.Expression) -> None:
        self.sql = sql
        self.expression = expression


class SqlRule(Protocol):
    name: str

    def check(self, ctx: SqlContext) -> RuleResult: ...


def _ok(name: str) -> RuleResult:
    return RuleResult(rule=name, passed=True)


def _fail(name: str, reason: str) -> RuleResult:
    return RuleResult(rule=name, passed=False, reason=reason)


class ReadOnlyRule:
    name = "ReadOnlyRule"

    def check(self, ctx: SqlContext) -> RuleResult:
        if any(isinstance(node, _WRITE_NODES) for node in ctx.expression.walk()):
            return _fail(self.name, "only read-only SELECT statements are allowed")
        if not isinstance(ctx.expression, exp.Select | exp.Union | exp.Subquery):
            return _fail(self.name, "statement is not a query")
        return _ok(self.name)


class TableAllowlistRule:
    name = "TableAllowlistRule"

    def check(self, ctx: SqlContext) -> RuleResult:
        cte_names = {cte.alias_or_name.lower() for cte in ctx.expression.find_all(exp.CTE)}
        allowed = _ANALYTICS_TABLES | cte_names
        for table in ctx.expression.find_all(exp.Table):
            if table.catalog:
                return _fail(self.name, f"cross-database access is not allowed: {table.catalog}")
            schema = (table.db or "").lower()
            if schema and schema != "analytics":
                return _fail(self.name, f"schema not allowed: {schema}")
            if table.name.lower() not in allowed:
                return _fail(self.name, f"table not in allowlist: {table.name}")
        return _ok(self.name)


class NoSystemCatalogRule:
    name = "NoSystemCatalogRule"

    def check(self, ctx: SqlContext) -> RuleResult:
        for node in ctx.expression.walk():
            if isinstance(node, exp.Table) and self._is_system_table(node):
                return _fail(self.name, f"system catalog access is not allowed: {node.name}")
            if isinstance(node, exp.Anonymous) and node.name.lower() in _BLOCKED_FUNCTIONS:
                return _fail(self.name, f"function not allowed: {node.name}")
        return _ok(self.name)

    @staticmethod
    def _is_system_table(node: exp.Table) -> bool:
        return node.name.lower().startswith("pg_") or (node.db or "").lower() in _BLOCKED_SCHEMAS


class MandatoryLimitRule:
    """Ensures a bounded result. Missing LIMIT is injected; an over-cap LIMIT is
    clamped — so no query can ever ask for an unbounded scan (defence in depth
    with the executor's own row cap)."""

    name = "MandatoryLimitRule"

    def __init__(self, row_cap: int) -> None:
        self._cap = row_cap

    def check(self, ctx: SqlContext) -> RuleResult:
        if not isinstance(ctx.expression, exp.Select | exp.Union):
            return _ok(self.name)
        limit = ctx.expression.args.get("limit")
        if limit is None:
            ctx.expression = ctx.expression.limit(self._cap)
            return RuleResult(self.name, True, f"injected LIMIT {self._cap}")
        current = _limit_value(limit)
        if current is None or current > self._cap:
            ctx.expression = ctx.expression.limit(self._cap)
            return RuleResult(self.name, True, f"clamped LIMIT to {self._cap}")
        return _ok(self.name)


def _limit_value(limit: exp.Expression) -> int | None:
    expr = limit.expression if isinstance(limit, exp.Limit) else limit
    if isinstance(expr, exp.Literal) and expr.is_int:
        return int(expr.name)
    return None


class SqlValidatorChain:
    """Realises the SqlValidator port. Pure and synchronous — no I/O — so it can
    be fuzzed exhaustively (see the injection corpus tests)."""

    def __init__(self, row_cap: int = 1000) -> None:
        self._rules: list[SqlRule] = [
            ReadOnlyRule(),
            TableAllowlistRule(),
            NoSystemCatalogRule(),
            MandatoryLimitRule(row_cap),
        ]

    def validate(self, sql: str) -> ValidationResult:
        try:
            statements = [s for s in sqlglot.parse(sql, read=_DIALECT) if s is not None]
        except ParseError as exc:
            return ValidationResult(
                ok=False, sql=sql, results=(_fail("ParseRule", f"unparseable SQL: {exc}"),)
            )

        if len(statements) != 1:
            return ValidationResult(
                ok=False,
                sql=sql,
                results=(
                    _fail("SingleStatementRule", f"expected 1 statement, got {len(statements)}"),
                ),
            )

        ctx = SqlContext(sql, statements[0])
        results: list[RuleResult] = [_ok("SingleStatementRule")]
        for rule in self._rules:
            result = rule.check(ctx)
            results.append(result)
            if not result.passed:
                return ValidationResult(ok=False, sql=sql, results=tuple(results))

        return ValidationResult(
            ok=True, sql=ctx.expression.sql(dialect=_DIALECT), results=tuple(results)
        )
