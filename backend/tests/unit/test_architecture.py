"""Architectural fitness function: the domain layer must import nothing outward.

This is the same rule import-linter enforces in CI, expressed as a plain-``ast``
test so it also runs locally with no native dependencies. Two guards fail the
build if a future edit reaches across a clean-architecture boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "app" / "domain"

FORBIDDEN_PREFIXES = (
    "app.application",
    "app.infrastructure",
    "app.interface",
    "app.config",
    "app.container",
    # third-party frameworks/vendors — the domain is framework-free
    "fastapi",
    "starlette",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "langgraph",
    "langchain_core",
    "mlflow",
    "redis",
    "httpx",
    "sqlglot",
    "pydantic",
)


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_domain_imports_nothing_outward() -> None:
    offenders: dict[str, set[str]] = {}
    for path in DOMAIN_DIR.rglob("*.py"):
        modules = _imported_modules(path.read_text(encoding="utf-8"))
        bad = {m for m in modules if m.startswith(FORBIDDEN_PREFIXES)}
        if bad:
            offenders[str(path.relative_to(DOMAIN_DIR))] = bad

    assert not offenders, f"domain reached outward: {offenders}"


def test_domain_only_imports_itself_or_stdlib() -> None:
    # Anything under app.* that the domain imports must stay inside app.domain.
    for path in DOMAIN_DIR.rglob("*.py"):
        for module in _imported_modules(path.read_text(encoding="utf-8")):
            if module.startswith("app.") and not module.startswith("app.domain"):
                raise AssertionError(f"{path.name} imports non-domain app module {module}")
