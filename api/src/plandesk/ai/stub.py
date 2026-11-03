"""Deterministic stand-in for the model: the same input always gives the same proposals."""

from __future__ import annotations

import datetime as dt
from typing import Any

from plandesk.ai.provider import PROMPT_VERSION, ProviderResult
from plandesk.services.adaptation import AdaptationInput, PlanFacts
from plandesk.services.clashes import ClashKind


def _next_free(
    day: dt.date, step: int, plan: PlanFacts, lo: dt.date, hi: dt.date
) -> dt.date | None:
    cur = day
    for _ in range(14):
        cur = cur + dt.timedelta(days=step)
        if cur < lo or cur > hi:
            return None
        if cur not in plan.holiday_dates and cur.weekday() < 5:
            return cur
    return None


class StubProvider:
    name = "stub"

    async def propose(self, inp: AdaptationInput) -> ProviderResult:
        out: list[dict[str, Any]] = []
        for plan in inp.plans:
            for c in plan.clashes:
                if c.kind is ClashKind.launch_on_holiday:
                    new = _next_free(
                        c.date, 1, plan, inp.window_start, min(plan.end, inp.window_end)
                    )
                    if new is not None and new < plan.end:
                        out.append(
                            _item(
                                plan,
                                "shift_start",
                                c.date,
                                new,
                                f"Launch falls on {c.holiday_name}; start on the next working day.",
                            )
                        )
                        continue
                elif c.kind is ClashKind.end_on_holiday:
                    new = _next_free(
                        c.date, -1, plan, max(plan.start, inp.window_start), inp.window_end
                    )
                    if new is not None and new > plan.start:
                        out.append(
                            _item(
                                plan,
                                "shift_end",
                                c.date,
                                new,
                                f"End falls on {c.holiday_name}; close on the previous working day.",
                            )
                        )
                        continue
                out.append(
                    _item(
                        plan,
                        "note_messaging",
                        c.date,
                        None,
                        f"{c.holiday_name} falls inside the window; adjust messaging around it.",
                    )
                )
        return ProviderResult(
            raw={"suggestions": out}, model_deployment="stub", prompt_version=PROMPT_VERSION
        )


def _item(
    plan: PlanFacts, action: str, flag: dt.date, new: dt.date | None, why: str
) -> dict[str, Any]:
    return {
        "market_code": plan.market_code,
        "action": action,
        "flag_date": flag.isoformat(),
        "new_date": new.isoformat() if new else None,
        "rationale": why,
    }
