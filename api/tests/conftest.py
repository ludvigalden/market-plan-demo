"""Fixtures: a throwaway database on the local PostgreSQL, migrated to head."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from plandesk.config import Settings
from plandesk.main import create_app

API_DIR = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL", "postgresql+asyncpg://plandesk@127.0.0.1:55432/postgres"
)
NAGER = "https://holidays.test"


def alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


async def _admin(sql: str) -> None:
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


@pytest.fixture(scope="session")
async def empty_db_url() -> AsyncIterator[str]:
    """A fresh, empty database, dropped after the session."""
    name = f"plandesk_test_{uuid.uuid4().hex[:8]}"
    await _admin(f'CREATE DATABASE "{name}"')
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        await _admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
async def db_url(empty_db_url: str) -> str:
    result = alembic(empty_db_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return empty_db_url


def nager_payload(year: int, code: str) -> list[dict[str, object]]:
    fixed = {
        "SE": [(f"{year}-05-01", "International Workers' Day"), (f"{year}-06-06", "National Day")],
        "DE": [(f"{year}-05-01", "Labour Day"), (f"{year}-05-14", "Ascension Day")],
        "US": [(f"{year}-05-25", "Memorial Day")],
        "JP": [(f"{year}-05-05", "Children's Day")],
        "FR": [(f"{year}-05-08", "Victory in Europe Day")],
    }
    return [{"date": d, "name": n, "global": True} for d, n in fixed.get(code, [])]


@pytest.fixture
def nager() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=NAGER, assert_all_called=False) as mock:
        route = mock.get(path__regex=r"/api/v3/PublicHolidays/(?P<year>\d+)/(?P<code>[A-Z]{2})")

        def handler(request: httpx.Request, year: str, code: str) -> httpx.Response:
            return httpx.Response(200, json=nager_payload(int(year), code))

        route.side_effect = handler
        yield mock


@pytest.fixture
async def client(db_url: str, nager: respx.MockRouter) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=db_url,
        holidays_base_url=NAGER,
        holidays_backoff_seconds=0.0,
        ai_provider="stub",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://app") as c:
            yield c
