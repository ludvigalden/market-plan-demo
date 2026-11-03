"""Request and response models; these are the OpenAPI contract."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from plandesk.models import PlanStatus, SuggestionAction, Verdict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketOut(BaseModel):
    code: str
    name: str
    currency: str


class CampaignCreate(Strict):
    name: str = Field(min_length=1, max_length=120)
    window_start: dt.date
    window_end: dt.date
    global_budget_eur: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def _window(self) -> CampaignCreate:
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        return self


class CampaignUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    global_budget_eur: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    window_start: dt.date
    window_end: dt.date
    global_budget_eur: Decimal
    market_codes: list[str]
    created_at: dt.datetime


class AssignMarkets(Strict):
    market_codes: list[str] = Field(min_length=1, max_length=20)


class HolidayOut(BaseModel):
    date: dt.date
    name: str


class ClashOut(BaseModel):
    kind: str
    date: dt.date
    holiday_name: str


class MarketPlanOut(BaseModel):
    id: uuid.UUID
    market_code: str
    market_name: str
    currency: str
    start_date: dt.date
    end_date: dt.date
    budget_share: Decimal
    budget_eur: Decimal
    status: PlanStatus
    version: int


class MarketViewRow(BaseModel):
    plan: MarketPlanOut
    holidays_available: bool
    holidays: list[HolidayOut]
    clashes: list[ClashOut]


class MarketView(BaseModel):
    campaign: CampaignOut
    markets: list[MarketViewRow]


class SuggestionOut(BaseModel):
    id: uuid.UUID
    market_plan_id: uuid.UUID
    market_code: str
    action: SuggestionAction
    flag_date: dt.date | None
    new_date: dt.date | None
    rationale: str
    model_deployment: str
    prompt_version: str
    created_at: dt.datetime
    verdict: Verdict | None
    plan_version: int


class SuggestRequest(Strict):
    market_codes: list[str] | None = None


class SuggestResult(BaseModel):
    suggestions: list[SuggestionOut]
    rejected_by_validator: int
    rejection_reasons: list[str]


class DecisionRequest(Strict):
    expected_plan_version: int = Field(ge=1)


class DecisionOut(BaseModel):
    suggestion: SuggestionOut
    plan: MarketPlanOut


class AuditEntry(BaseModel):
    decision_id: uuid.UUID
    suggestion_id: uuid.UUID
    market_code: str
    action: SuggestionAction
    verdict: Verdict
    decided_by: str
    decided_at: dt.datetime
    rationale: str
    model_deployment: str
    prompt_version: str


class Health(BaseModel):
    status: str
    database: str
    ai_provider: str
