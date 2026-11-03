"""Public holidays from Nager.Date, cached in PostgreSQL per market and year.

A fetch failure never fails the caller: the market is reported as
"holidays unavailable" and the next request tries again.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from plandesk.models import Holiday, HolidaySync
from plandesk.services.clashes import HolidayFact

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HolidayLookup:
    available: bool
    holidays: list[HolidayFact]


class HolidayClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 0.3,
    ) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._attempts = max(1, max_attempts)
        self._backoff = backoff_seconds

    async def fetch_year(self, market_code: str, year: int) -> list[HolidayFact]:
        url = f"{self._base}/api/v3/PublicHolidays/{year}/{market_code}"
        last: Exception | None = None
        for attempt in range(self._attempts):
            try:
                resp = await self._http.get(url)
                if resp.status_code == 204:
                    return []
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("upstream 5xx", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                return [
                    HolidayFact(date=dt.date.fromisoformat(item["date"]), name=str(item["name"]))
                    for item in data
                    if item.get("global", True)
                ]
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError, KeyError) as exc:
                last = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    break
                if attempt + 1 < self._attempts:
                    await asyncio.sleep(self._backoff * (2**attempt))
        raise HolidayFetchError(f"{market_code}/{year}: {last}")


class HolidayFetchError(Exception):
    pass


async def holidays_for(
    session: AsyncSession,
    client: HolidayClient,
    market_code: str,
    start: dt.date,
    end: dt.date,
) -> HolidayLookup:
    """Holidays for one market within [start, end], filling the cache as needed."""
    years = range(start.year, end.year + 1)
    synced = set(
        (
            await session.scalars(
                select(HolidaySync.year).where(
                    HolidaySync.market_code == market_code, HolidaySync.year.in_(list(years))
                )
            )
        ).all()
    )
    available = True
    for year in years:
        if year in synced:
            continue
        try:
            facts = await client.fetch_year(market_code, year)
        except HolidayFetchError as exc:
            log.warning("holidays_unavailable %s", exc)
            available = False
            continue
        if facts:
            # Nager can list two entries for one date; keep the first name.
            by_date: dict[dt.date, str] = {}
            for f in facts:
                by_date.setdefault(f.date, f.name)
            await session.execute(
                insert(Holiday)
                .values(
                    [{"market_code": market_code, "date": d, "name": n} for d, n in by_date.items()]
                )
                .on_conflict_do_nothing()
            )
        await session.execute(
            insert(HolidaySync).values(market_code=market_code, year=year).on_conflict_do_nothing()
        )
        await session.commit()
    rows = (
        await session.scalars(
            select(Holiday)
            .where(Holiday.market_code == market_code, Holiday.date >= start, Holiday.date <= end)
            .order_by(Holiday.date)
        )
    ).all()
    return HolidayLookup(
        available=available, holidays=[HolidayFact(date=r.date, name=r.name) for r in rows]
    )
