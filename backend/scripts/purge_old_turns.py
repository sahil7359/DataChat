"""Retention job (Schema §10): purge user turns and audit rows past the window.

User questions and the agent audit trail are kept for ``DATA_RETENTION_DAYS``
(default 90), then deleted. Run daily via a scheduler.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.config import get_settings
from app.infrastructure.db.session import create_app_engine


async def main() -> None:
    settings = get_settings()
    engine = create_app_engine(settings)
    days = settings.data_retention_days
    try:
        async with engine.begin() as conn:
            for table in ("app.turns", "app.agent_actions"):
                result = await conn.execute(
                    text(
                        f"DELETE FROM {table} "  # noqa: S608 - table name is a fixed constant
                        "WHERE created_at < now() - make_interval(days => :days)"
                    ),
                    {"days": days},
                )
                print(f"[purge] {table}: removed {result.rowcount} rows older than {days} days")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
