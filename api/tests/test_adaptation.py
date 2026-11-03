from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from plandesk.services.adaptation import AdaptationInput, PlanFacts, validate_proposals
from plandesk.services.clashes import Clash, ClashKind

D = dt.date

INPUT = AdaptationInput(
    window_start=D(2026, 5, 1),
    window_end=D(2026, 5, 31),
    plans=[
        PlanFacts(
            market_code="SE",
            start=D(2026, 5, 1),
            end=D(2026, 5, 31),
            clashes=[
                Clash(ClashKind.launch_on_holiday, D(2026, 5, 1), "Workers' Day"),
                Clash(ClashKind.holiday_in_window, D(2026, 5, 14), "Ascension"),
            ],
            holiday_dates=frozenset({D(2026, 5, 1), D(2026, 5, 14)}),
        )
    ],
)


def item(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "market_code": "SE",
        "action": "shift_start",
        "flag_date": "2026-05-01",
        "new_date": "2026-05-04",
        "rationale": "Workers' Day.",
    }
    base.update(kw)
    return base


def run(*items: dict[str, Any]) -> tuple[int, list[str]]:
    out = validate_proposals({"suggestions": list(items)}, INPUT)
    return len(out.accepted), out.rejected


def test_accepts_grounded_shift() -> None:
    assert run(item()) == (1, [])


def test_accepts_messaging_note() -> None:
    assert run(item(action="note_messaging", flag_date="2026-05-14", new_date=None)) == (1, [])


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"market_code": "DE"}, "market not in input"),
        ({"flag_date": "2026-05-02"}, "was not flagged"),
        ({"flag_date": None}, "was not flagged"),
        ({"new_date": "2026-06-02"}, "outside campaign window"),
        ({"new_date": "2026-05-14"}, "itself a public holiday"),
        ({"new_date": None}, "requires new_date"),
        ({"new_date": "2026-05-31"}, "before the plan end"),
        ({"action": "note_messaging"}, "must not carry a new_date"),
        (
            {"action": "shift_end", "new_date": "2026-05-01", "flag_date": "2026-05-14"},
            "itself a public holiday",
        ),
    ],
)
def test_rejects_ungrounded(override: dict[str, Any], fragment: str) -> None:
    accepted, rejected = run(item(**override))
    assert accepted == 0
    assert len(rejected) == 1 and fragment in rejected[0]


def test_wrong_action_enum_fails_schema() -> None:
    accepted, rejected = run(item(action="cut_budget"))
    assert accepted == 0 and rejected[0].startswith("schema:")


def test_budget_field_is_not_in_schema() -> None:
    accepted, rejected = run(item(budget_eur=1000))
    assert accepted == 0 and rejected[0].startswith("schema:")


def test_non_object_output_fails_closed() -> None:
    out = validate_proposals("not json", INPUT)
    assert out.accepted == [] and out.rejected


def test_duplicate_dropped() -> None:
    accepted, rejected = run(item(), item())
    assert accepted == 1 and "duplicate" in rejected[0]
