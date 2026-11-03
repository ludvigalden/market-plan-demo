from __future__ import annotations

import httpx
import pytest
import respx

from plandesk.services.holidays import HolidayClient, HolidayFetchError

BASE = "https://holidays.test"


async def test_retries_5xx_then_succeeds() -> None:
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/api/v3/PublicHolidays/2026/SE")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=[{"date": "2026-05-01", "name": "May Day", "global": True}]),
        ]
        async with httpx.AsyncClient() as http:
            out = await HolidayClient(http, BASE, backoff_seconds=0).fetch_year("SE", 2026)
    assert [h.name for h in out] == ["May Day"] and route.call_count == 2


async def test_regional_holidays_are_skipped() -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/api/v3/PublicHolidays/2026/DE").respond(
            200, json=[{"date": "2026-01-06", "name": "Epiphany", "global": False}]
        )
        async with httpx.AsyncClient() as http:
            assert await HolidayClient(http, BASE).fetch_year("DE", 2026) == []


async def test_gives_up_after_max_attempts() -> None:
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/api/v3/PublicHolidays/2026/SE").mock(
            side_effect=httpx.ConnectTimeout("t")
        )
        async with httpx.AsyncClient() as http:
            client = HolidayClient(http, BASE, max_attempts=3, backoff_seconds=0)
            with pytest.raises(HolidayFetchError):
                await client.fetch_year("SE", 2026)
    assert route.call_count == 3


async def test_4xx_is_not_retried() -> None:
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/api/v3/PublicHolidays/2026/XX").respond(404)
        async with httpx.AsyncClient() as http:
            with pytest.raises(HolidayFetchError):
                await HolidayClient(http, BASE, backoff_seconds=0).fetch_year("XX", 2026)
    assert route.call_count == 1
