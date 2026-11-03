from __future__ import annotations

import datetime as dt

from plandesk.services.clashes import ClashKind, HolidayFact, detect_clashes

D = dt.date


def test_classifies_start_end_and_inside() -> None:
    hs = [
        HolidayFact(D(2026, 5, 31), "End"),
        HolidayFact(D(2026, 5, 1), "Start"),
        HolidayFact(D(2026, 5, 14), "Mid"),
        HolidayFact(D(2026, 6, 6), "Outside"),
        HolidayFact(D(2026, 4, 30), "Before"),
    ]
    out = detect_clashes(D(2026, 5, 1), D(2026, 5, 31), hs)
    assert [(c.kind, c.date) for c in out] == [
        (ClashKind.launch_on_holiday, D(2026, 5, 1)),
        (ClashKind.holiday_in_window, D(2026, 5, 14)),
        (ClashKind.end_on_holiday, D(2026, 5, 31)),
    ]


def test_no_holidays_no_clashes() -> None:
    assert detect_clashes(D(2026, 5, 1), D(2026, 5, 31), []) == []


def test_single_day_plan_on_holiday_is_launch_clash() -> None:
    out = detect_clashes(D(2026, 5, 1), D(2026, 5, 1), [HolidayFact(D(2026, 5, 1), "X")])
    assert [c.kind for c in out] == [ClashKind.launch_on_holiday]
