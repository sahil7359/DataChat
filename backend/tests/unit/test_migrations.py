"""Static checks on the migration chain and the security-critical roles migration.

These run without a database: they prove the migration set is well-formed and
that the read-only role, grants, and execution limits are actually encoded (so a
regression that quietly drops the timeout or the REVOKE would fail the build).
The live apply/rollback + write-rejection is covered by the integration suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def _load(name: str) -> ModuleType:
    path = VERSIONS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chain_is_linear_and_ordered() -> None:
    m1 = _load("0001_app_schema")
    m2 = _load("0002_analytics_schema")
    m3 = _load("0003_roles_grants")

    assert m1.down_revision is None
    assert m2.down_revision == m1.revision
    assert m3.down_revision == m2.revision


def test_every_migration_is_reversible() -> None:
    for name in ("0001_app_schema", "0002_analytics_schema", "0003_roles_grants"):
        module = _load(name)
        assert callable(module.upgrade)
        assert callable(module.downgrade)


def test_roles_migration_encodes_least_privilege() -> None:
    source = (VERSIONS / "0003_roles_grants.py").read_text(encoding="utf-8")

    assert "CREATE ROLE analytics_ro NOLOGIN" in source
    assert "datachat_exec LOGIN" in source
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA" in source
    assert "REVOKE ALL ON SCHEMA" in source  # no app-schema access
    assert "default_transaction_read_only = on" in source
    assert "statement_timeout" in source


def test_roles_migration_never_hardcodes_the_password() -> None:
    source = (VERSIONS / "0003_roles_grants.py").read_text(encoding="utf-8")
    # The password is bound via set_config, not written into the SQL (LLM07).
    assert "PASSWORD 'datachat" not in source
    assert "get_secret_value()" in source
