"""analytics schema: curated open-data tables (read-only target)

Revision ID: 0002_analytics_schema
Revises: 0001_app_schema
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.infrastructure.db import models  # noqa: F401  (registers tables on the metadata)
from app.infrastructure.db.base import ANALYTICS_SCHEMA, Base

revision: str = "0002_analytics_schema"
down_revision: str | None = "0001_app_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _analytics_tables() -> list:
    return [t for t in Base.metadata.sorted_tables if t.schema == ANALYTICS_SCHEMA]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {ANALYTICS_SCHEMA}")
    # Structure only; the rows are loaded by the idempotent ingestion job, not by
    # migrations (Schema §8).
    Base.metadata.create_all(bind=bind, tables=_analytics_tables())


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_analytics_tables())))
    op.execute(f"DROP SCHEMA IF EXISTS {ANALYTICS_SCHEMA} CASCADE")
