"""app schema: pgvector, tables, and HNSW indexes

Revision ID: 0001_app_schema
Revises:
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.infrastructure.db import models  # noqa: F401  (registers tables on the metadata)
from app.infrastructure.db.base import APP_SCHEMA, Base

revision: str = "0001_app_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VECTOR_TABLES = ("semantic_tables", "semantic_columns", "few_shot_examples")


def _app_tables() -> list:
    return [t for t in Base.metadata.sorted_tables if t.schema == APP_SCHEMA]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {APP_SCHEMA}")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    tables = _app_tables()
    if not tables:  # fail loudly rather than silently stamping an empty migration
        raise RuntimeError("app-schema models are not registered on the metadata")
    Base.metadata.create_all(bind=bind, tables=tables)
    # HNSW cosine indexes for the embedding columns (Schema §6). Declared here
    # rather than on the model because the index method is Postgres/pgvector
    # specific and not part of the portable ORM contract.
    for table in _VECTOR_TABLES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding "
            f"ON {APP_SCHEMA}.{table} USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in _VECTOR_TABLES:
        op.execute(f"DROP INDEX IF EXISTS {APP_SCHEMA}.ix_{table}_embedding")
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_app_tables())))
    op.execute("DROP EXTENSION IF EXISTS vector")
