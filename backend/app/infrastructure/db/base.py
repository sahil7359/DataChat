"""Declarative base, schema names, and the constraint naming convention.

A deterministic naming convention is what makes Alembic migrations reproducible:
constraints/indexes get stable names instead of database-assigned ones, so
``downgrade`` can find what ``upgrade`` created.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

APP_SCHEMA = "app"
ANALYTICS_SCHEMA = "analytics"
EMBEDDING_DIM = 768  # Gemini text-embedding-004 (Schema §6)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
