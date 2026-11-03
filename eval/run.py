"""Deterministic grader for the adaptation step. Fails closed.

For every golden case the configured provider is called with the same facts
the API would send, the server-side validator filters the output, and the
grader then requires that:
  * the validator rejected nothing (the provider stayed inside the facts);
  * every flagged holiday got exactly one suggestion;
  * each suggestion's action is one of the actions the case allows;
  * no suggestion references a market or date outside the case.
Any missing file, empty set, provider error or failed check exits non-zero.

Run from the repository root:  uv run --project api python eval/run.py
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from plandesk.ai.provider import AdaptationProvider
from plandesk.config import get_settings
from plandesk.main import build_provider
from plandesk.services.adaptation import AdaptationInput, PlanFacts, validate_proposals
from plandesk.services.clashes import HolidayFact, detect_clashes

GOLDEN = Path(__file__).resolve().parent / "golden.jsonl"


def _input(case: dict[str, Any]) -> AdaptationInput:
    plans: list[PlanFacts] = []
    for p in case["plans"]:
        hs = [HolidayFact(dt.date.fromisoformat(h["date"]), h["name"]) for h in p["holidays"]]
        start, end = dt.date.fromisoformat(p["start"]), dt.date.fromisoformat(p["end"])
        plans.append(
            PlanFacts(
                market_code=p["market_code"],
                start=start,
                end=end,
                clashes=detect_clashes(start, end, hs),
                holiday_dates=frozenset(h.date for h in hs),
            )
        )
    return AdaptationInput(
        window_start=dt.date.fromisoformat(case["window_start"]),
        window_end=dt.date.fromisoformat(case["window_end"]),
        plans=plans,
    )


async def grade(case: dict[str, Any], provider: AdaptationProvider) -> list[str]:
    inp = _input(case)
    expected: dict[str, dict[str, list[str]]] = case["expected"]
    flagged = {(p.market_code, c.date.isoformat()) for p in inp.plans for c in p.clashes}
    want = {(m, d) for m, dates in expected.items() for d in dates}
    if flagged != want:
        return [f"golden case disagrees with clash detection: {sorted(flagged ^ want)}"]
    if not flagged:
        return []
    result = await provider.propose(inp)
    outcome = validate_proposals(result.raw, inp)
    errors = [f"validator rejected: {r}" for r in outcome.rejected]
    seen: dict[tuple[str, str], int] = {}
    for s in outcome.accepted:
        key = (s.market_code, s.flag_date.isoformat() if s.flag_date else "")
        seen[key] = seen.get(key, 0) + 1
        allowed = expected.get(s.market_code, {}).get(key[1])
        if allowed is None:
            errors.append(f"unexpected suggestion for {key}")
        elif s.action.value not in allowed:
            errors.append(f"{key}: action {s.action.value} not in {allowed}")
    for key in sorted(flagged):
        n = seen.get(key, 0)
        if n != 1:
            errors.append(f"{key}: expected exactly one suggestion, got {n}")
    return errors


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", type=Path, default=GOLDEN)
    args = ap.parse_args()
    if not args.golden.is_file():
        print(f"FAIL golden set missing: {args.golden}", file=sys.stderr)
        return 2
    cases = [json.loads(line) for line in args.golden.read_text().splitlines() if line.strip()]
    if not cases:
        print("FAIL golden set is empty", file=sys.stderr)
        return 2
    settings = get_settings()
    provider = build_provider(settings)
    failed = 0
    try:
        for case in cases:
            try:
                errors = await grade(case, provider)
            except Exception as exc:  # a provider failure is a failed case, never a skip
                errors = [f"provider error: {type(exc).__name__}: {exc}"]
            status = "PASS" if not errors else "FAIL"
            failed += bool(errors)
            print(f"{status} {case['id']}")
            for e in errors:
                print(f"     {e}")
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()
    print(
        f"{len(cases) - failed}/{len(cases)} passed  provider={provider.name}"
        f"  deployment={settings.foundry_model_deployment or provider.name}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
