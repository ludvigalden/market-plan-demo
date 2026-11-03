"""Every migration upgrades and downgrades cleanly on an empty database."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import ADMIN_URL, _admin, alembic, make_url


@pytest.fixture
async def scratch_url() -> str:
    import uuid

    name = f"plandesk_mig_{uuid.uuid4().hex[:8]}"
    await _admin(f'CREATE DATABASE "{name}"')
    return make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)


async def _tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("select tablename from pg_tables where schemaname = 'public'")
        )
        names = {r[0] for r in rows}
        types = await conn.execute(text("select typname from pg_type where typtype = 'e'"))
        names |= {f"type:{r[0]}" for r in types}
    await engine.dispose()
    return names


async def test_round_trip(scratch_url: str) -> None:
    try:
        for args in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
            r = alembic(scratch_url, *args)
            assert r.returncode == 0, r.stderr
        assert "market_plan" in await _tables(scratch_url)
        assert alembic(scratch_url, "check").returncode == 0
        # Step down one revision at a time and back, proving each downgrade alone.
        for _ in range(4):
            assert alembic(scratch_url, "downgrade", "-1").returncode == 0
        assert await _tables(scratch_url) == {"alembic_version"}
        for _ in range(4):
            assert alembic(scratch_url, "upgrade", "+1").returncode == 0
    finally:
        await _admin(f'DROP DATABASE IF EXISTS "{make_url(scratch_url).database}" WITH (FORCE)')


async def test_version_expand_backfills_existing_rows(scratch_url: str) -> None:
    try:
        assert alembic(scratch_url, "upgrade", "0003").returncode == 0
        engine = create_async_engine(scratch_url)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into campaign (id, name, window_start, window_end, global_budget_eur)"
                    " values (gen_random_uuid(), 'c', '2026-05-01', '2026-05-31', 1)"
                )
            )
            await conn.execute(
                text(
                    "insert into market_plan (id, campaign_id, market_code, start_date, end_date,"
                    " budget_share, status) select gen_random_uuid(), id, 'SE', window_start,"
                    " window_end, 1, 'draft' from campaign"
                )
            )
        assert alembic(scratch_url, "upgrade", "head").returncode == 0
        async with engine.connect() as conn:
            v = (await conn.execute(text("select version from market_plan"))).scalar_one()
        await engine.dispose()
        assert v == 1
    finally:
        await _admin(f'DROP DATABASE IF EXISTS "{make_url(scratch_url).database}" WITH (FORCE)')
