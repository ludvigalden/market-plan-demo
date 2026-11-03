"""Server-side validation of model-proposed adaptations.

The model only proposes. Every proposal is checked against the facts that
were sent to it; anything referencing a market, flag or date that was not in
the input, or falling outside the campaign window, is dropped with a reason.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from plandesk.models import SuggestionAction
from plandesk.services.clashes import Clash


class ProposedAdaptation(BaseModel):
    """One item of the model's structured output. No budget fields exist."""

    model_config = ConfigDict(extra="forbid")

    market_code: str = Field(min_length=2, max_length=2)
    action: SuggestionAction
    flag_date: dt.date | None
    new_date: dt.date | None
    rationale: str = Field(min_length=1, max_length=400)


class ProposalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[ProposedAdaptation] = Field(max_length=50)


@dataclass(frozen=True, slots=True)
class PlanFacts:
    market_code: str
    start: dt.date
    end: dt.date
    clashes: list[Clash]
    holiday_dates: frozenset[dt.date]


@dataclass(frozen=True, slots=True)
class AdaptationInput:
    window_start: dt.date
    window_end: dt.date
    plans: list[PlanFacts]


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    accepted: list[ProposedAdaptation]
    rejected: list[str]


def _check(item: ProposedAdaptation, inp: AdaptationInput) -> str | None:
    plan = next((p for p in inp.plans if p.market_code == item.market_code), None)
    if plan is None:
        return f"{item.market_code}: market not in input"
    flag_dates = {c.date for c in plan.clashes}
    if item.action is SuggestionAction.no_change:
        if item.new_date is not None:
            return f"{item.market_code}: no_change must not carry a new_date"
        if item.flag_date is not None and item.flag_date not in flag_dates:
            return f"{item.market_code}: flag_date {item.flag_date} was not flagged"
        return None
    if item.flag_date is None or item.flag_date not in flag_dates:
        return f"{item.market_code}: flag_date {item.flag_date} was not flagged"
    if item.action is SuggestionAction.note_messaging:
        if item.new_date is not None:
            return f"{item.market_code}: note_messaging must not carry a new_date"
        return None
    if item.new_date is None:
        return f"{item.market_code}: {item.action.value} requires new_date"
    if not (inp.window_start <= item.new_date <= inp.window_end):
        return f"{item.market_code}: new_date {item.new_date} outside campaign window"
    if item.new_date in plan.holiday_dates:
        return f"{item.market_code}: new_date {item.new_date} is itself a public holiday"
    if item.action is SuggestionAction.shift_start and item.new_date >= plan.end:
        return f"{item.market_code}: shifted start must stay before the plan end"
    if item.action is SuggestionAction.shift_end and item.new_date <= plan.start:
        return f"{item.market_code}: shifted end must stay after the plan start"
    return None


def validate_proposals(raw: object, inp: AdaptationInput) -> ValidationOutcome:
    """Parse raw model output and keep only proposals grounded in the input."""
    try:
        batch = ProposalBatch.model_validate(raw)
    except ValidationError as exc:
        return ValidationOutcome(accepted=[], rejected=[f"schema: {exc.error_count()} error(s)"])
    accepted: list[ProposedAdaptation] = []
    rejected: list[str] = []
    seen: set[tuple[str, str, dt.date | None]] = set()
    for item in batch.suggestions:
        reason = _check(item, inp)
        key = (item.market_code, item.action.value, item.flag_date)
        if reason is None and key in seen:
            reason = f"{item.market_code}: duplicate {item.action.value} for {item.flag_date}"
        if reason is None:
            seen.add(key)
            accepted.append(item)
        else:
            rejected.append(reason)
    return ValidationOutcome(accepted=accepted, rejected=rejected)
