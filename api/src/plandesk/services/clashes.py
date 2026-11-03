"""Deterministic clash detection: which public holidays touch a market plan."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class ClashKind(StrEnum):
    launch_on_holiday = "launch_on_holiday"
    end_on_holiday = "end_on_holiday"
    holiday_in_window = "holiday_in_window"


@dataclass(frozen=True, slots=True)
class HolidayFact:
    date: dt.date
    name: str


@dataclass(frozen=True, slots=True)
class Clash:
    kind: ClashKind
    date: dt.date
    holiday_name: str


def detect_clashes(start: dt.date, end: dt.date, holidays: list[HolidayFact]) -> list[Clash]:
    """Return one clash per holiday inside [start, end], ordered by date.

    A holiday on the start date is a launch clash, one on the end date is an
    end clash, anything else in between is a messaging-relevant holiday.
    """
    out: list[Clash] = []
    for h in sorted(holidays, key=lambda h: h.date):
        if h.date < start or h.date > end:
            continue
        if h.date == start:
            kind = ClashKind.launch_on_holiday
        elif h.date == end:
            kind = ClashKind.end_on_holiday
        else:
            kind = ClashKind.holiday_in_window
        out.append(Clash(kind=kind, date=h.date, holiday_name=h.name))
    return out
