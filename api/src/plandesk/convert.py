"""ORM rows to response models."""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from plandesk.models import AiSuggestion, Campaign, MarketPlan
from plandesk.schemas import CampaignOut, MarketPlanOut, SuggestionOut


def campaign_out(c: Campaign) -> CampaignOut:
    return CampaignOut(
        id=c.id,
        name=c.name,
        window_start=c.window_start,
        window_end=c.window_end,
        global_budget_eur=c.global_budget_eur,
        market_codes=sorted(p.market_code for p in c.plans),
        created_at=c.created_at,
    )


def plan_out(p: MarketPlan, global_budget: Decimal) -> MarketPlanOut:
    budget = (global_budget * p.budget_share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return MarketPlanOut(
        id=p.id,
        market_code=p.market_code,
        market_name=p.market.name,
        currency=p.market.currency,
        start_date=p.start_date,
        end_date=p.end_date,
        budget_share=p.budget_share,
        budget_eur=budget,
        status=p.status,
        version=p.version,
    )


def _date(v: object) -> dt.date | None:
    return dt.date.fromisoformat(v) if isinstance(v, str) else None


def suggestion_out(s: AiSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=s.id,
        market_plan_id=s.market_plan_id,
        market_code=s.plan.market_code,
        action=s.action,
        flag_date=_date(s.payload.get("flag_date")),
        new_date=_date(s.payload.get("new_date")),
        rationale=s.rationale,
        model_deployment=s.model_deployment,
        prompt_version=s.prompt_version,
        created_at=s.created_at,
        verdict=s.decision.verdict if s.decision else None,
        plan_version=s.plan.version,
    )
