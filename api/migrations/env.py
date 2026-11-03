"""Alembic environment: async engine, URL from application settings."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from plandesk.config import get_settings
from plandesk.models import Base

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline mode is not supported")
asyncio.run(_online())
