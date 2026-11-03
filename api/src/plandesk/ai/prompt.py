"""Prompt and output schema for the adaptation call."""

from __future__ import annotations

import json
from typing import Any

from plandesk.services.adaptation import AdaptationInput

SYSTEM_PROMPT = """You help a marketing planner adapt one global campaign to local markets.
You receive each market's plan dates and the public-holiday clashes that deterministic
code has already found. For each clash, propose at most one adaptation:
- shift_start: move the market launch to new_date (a non-holiday inside the campaign window)
- shift_end: move the market end to new_date (a non-holiday inside the campaign window)
- note_messaging: keep the dates, advise a messaging change around the holiday
- no_change: the clash does not matter
Rules: reference only markets and flag dates given to you. Never invent holidays.
Never mention budget amounts or any other numbers that were not given.
Keep each rationale to one sentence and name the holiday it answers."""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["suggestions"],
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["market_code", "action", "flag_date", "new_date", "rationale"],
                "properties": {
                    "market_code": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["shift_start", "shift_end", "note_messaging", "no_change"],
                    },
                    "flag_date": {"type": ["string", "null"], "description": "ISO date"},
                    "new_date": {"type": ["string", "null"], "description": "ISO date"},
                    "rationale": {"type": "string"},
                },
            },
        }
    },
}


def user_message(inp: AdaptationInput) -> str:
    facts = {
        "campaign_window": {
            "start": inp.window_start.isoformat(),
            "end": inp.window_end.isoformat(),
        },
        "markets": [
            {
                "market_code": p.market_code,
                "plan_start": p.start.isoformat(),
                "plan_end": p.end.isoformat(),
                "clashes": [
                    {"kind": c.kind.value, "date": c.date.isoformat(), "holiday": c.holiday_name}
                    for c in p.clashes
                ],
                "other_holidays_in_window": sorted(
                    d.isoformat() for d in p.holiday_dates if d not in {c.date for c in p.clashes}
                ),
            }
            for p in inp.plans
        ],
    }
    return json.dumps(facts, sort_keys=True)
