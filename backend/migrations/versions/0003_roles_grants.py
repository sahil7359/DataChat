"""read-only roles, grants, and execution limits (the security spine)

Revision ID: 0003_roles_grants
Revises: 0002_analytics_schema
Create Date: 2026-07-23

This migration is hand-written and security-critical (Schema §5): it creates the
``analytics_ro`` role (SELECT-only on the analytics schema, no access to app) and
the ``datachat_exec`` login role used by the executor pool, with a statement
timeout and a read-only transaction default. Together with the guardrail chain
(Phase 5) this is the defence-in-depth that makes "no writes ever" true even if
every application layer were bypassed (FR-23, LLM06, ASI02/ASI03).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.config import get_settings
from app.infrastructure.db.base import ANALYTICS_SCHEMA, APP_SCHEMA

revision: str = "0003_roles_grants"
down_revision: str | None = "0002_analytics_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = get_settings()
    timeout_ms = str(settings.statement_timeout_ms)

    # Bind the password as a parameter into a session GUC, then read it back with
    # quote_literal (%L) inside the DO block. The secret never touches the SQL
    # text, so there is no injection surface and nothing to leak in logs.
    op.execute(
        sa.text("SELECT set_config('datachat.exec_pw', :pw, false)").bindparams(
            pw=settings.executor_role_password.get_secret_value()
        )
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_ro') THEN
            CREATE ROLE analytics_ro NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'datachat_exec') THEN
            EXECUTE format(
              'CREATE ROLE datachat_exec LOGIN PASSWORD %L IN ROLE analytics_ro',
              current_setting('datachat.exec_pw')
            );
          ELSE
            EXECUTE format(
              'ALTER ROLE datachat_exec PASSWORD %L',
              current_setting('datachat.exec_pw')
            );
          END IF;
        END $$;
        """
    )

    # Least privilege: SELECT only on analytics, now and for future tables.
    op.execute(f"GRANT USAGE ON SCHEMA {ANALYTICS_SCHEMA} TO analytics_ro")
    op.execute(f"REVOKE CREATE ON SCHEMA {ANALYTICS_SCHEMA} FROM analytics_ro")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {ANALYTICS_SCHEMA} TO analytics_ro")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {ANALYTICS_SCHEMA} "
        f"GRANT SELECT ON TABLES TO analytics_ro"
    )
    # The read-only role must not be able to touch app data at all.
    op.execute(f"REVOKE ALL ON SCHEMA {APP_SCHEMA} FROM analytics_ro")

    # Hard limits enforced by the database itself.
    op.execute(f"ALTER ROLE datachat_exec SET statement_timeout = '{timeout_ms}'")
    op.execute("ALTER ROLE datachat_exec SET default_transaction_read_only = on")
    op.execute(f"ALTER ROLE datachat_exec SET search_path = {ANALYTICS_SCHEMA}")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'datachat_exec') THEN
            DROP OWNED BY datachat_exec;
            DROP ROLE datachat_exec;
          END IF;
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_ro') THEN
            DROP OWNED BY analytics_ro;
            DROP ROLE analytics_ro;
          END IF;
        END $$;
        """
    )
