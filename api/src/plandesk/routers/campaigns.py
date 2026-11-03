"""Campaigns, market assignment and the per-market view."""

from __future__ import annotations

import uuid
from decimal import ROUND_DOWN, Decimal

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from plandesk.convert import campaign_out, plan_out
from plandesk.deps import Holidays, Session
from plandesk.errors import ERROR_RESPONSES, NotFound, Unprocessable
from plandesk.models import Campaign, Market, MarketPlan
from plandesk.schemas import (
    AssignMarkets,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    ClashOut,
    HolidayOut,
    MarketOut,
    MarketView,
    MarketViewRow,
)
from plandesk.services.clashes import detect_clashes
from plandesk.services.holidays import holidays_for

router = APIRouter(tags=["campaigns"], responses=ERROR_RESPONSES)


async def load_campaign(session: Session, campaign_id: uuid.UUID) -> Campaign:
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.plans).joinedload(MarketPlan.market))
        .execution_options(populate_existing=True)
    )
    if campaign is None:
        raise NotFound(f"campaign {campaign_id} not found")
    return campaign


@router.get("/markets", response_model=list[MarketOut])
async def list_markets(session: Session) -> list[MarketOut]:
    rows = (await session.scalars(select(Market).order_by(Market.code))).all()
    return [MarketOut(code=m.code, name=m.name, currency=m.currency) for m in rows]


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(session: Session) -> list[CampaignOut]:
    rows = (
        await session.scalars(
            select(Campaign)
            .options(selectinload(Campaign.plans))
            .order_by(Campaign.created_at.desc())
        )
    ).all()
    return [campaign_out(c) for c in rows]


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, session: Session) -> CampaignOut:
    campaign = Campaign(**body.model_dump())
    session.add(campaign)
    await session.commit()
    return campaign_out(await load_campaign(session, campaign.id))


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: uuid.UUID, session: Session) -> CampaignOut:
    return campaign_out(await load_campaign(session, campaign_id))


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID, body: CampaignUpdate, session: Session
) -> CampaignOut:
    campaign = await load_campaign(session, campaign_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(campaign, key, value)
    await session.commit()
    return campaign_out(await load_campaign(session, campaign_id))


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: uuid.UUID, session: Session) -> None:
    campaign = await load_campaign(session, campaign_id)
    await session.delete(campaign)
    await session.commit()


@router.put("/campaigns/{campaign_id}/markets", response_model=CampaignOut)
async def assign_markets(
    campaign_id: uuid.UUID, body: AssignMarkets, session: Session
) -> CampaignOut:
    """Set the campaign's markets. New markets start on the global window with an equal share."""
    campaign = await load_campaign(session, campaign_id)
    wanted = sorted({c.upper() for c in body.market_codes})
    known = set((await session.scalars(select(Market.code).where(Market.code.in_(wanted)))).all())
    unknown = [c for c in wanted if c not in known]
    if unknown:
        raise Unprocessable(f"unknown market code(s): {', '.join(unknown)}")
    existing = {p.market_code: p for p in campaign.plans}
    for code, plan in existing.items():
        if code not in wanted:
            await session.delete(plan)
    share = (Decimal(1) / Decimal(len(wanted))).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    for code in wanted:
        plan = existing.get(code)
        if plan is None:
            session.add(
                MarketPlan(
                    campaign_id=campaign.id,
                    market_code=code,
                    start_date=campaign.window_start,
                    end_date=campaign.window_end,
                    budget_share=share,
                )
            )
        elif plan.budget_share != share:
            plan.budget_share = share
    await session.commit()
    return campaign_out(await load_campaign(session, campaign_id))


@router.get("/campaigns/{campaign_id}/market-view", response_model=MarketView)
async def get_market_view(
    campaign_id: uuid.UUID, session: Session, holidays: Holidays
) -> MarketView:
    """Each market's plan, its public holidays in the window, and the deterministic clash flags."""
    campaign = await load_campaign(session, campaign_id)
    rows: list[MarketViewRow] = []
    for plan in sorted(campaign.plans, key=lambda p: p.market_code):
        lookup = await holidays_for(
            session, holidays, plan.market_code, campaign.window_start, campaign.window_end
        )
        clashes = detect_clashes(plan.start_date, plan.end_date, lookup.holidays)
        rows.append(
            MarketViewRow(
                plan=plan_out(plan, campaign.global_budget_eur),
                holidays_available=lookup.available,
                holidays=[HolidayOut(date=h.date, name=h.name) for h in lookup.holidays],
                clashes=[
                    ClashOut(kind=c.kind.value, date=c.date, holiday_name=c.holiday_name)
                    for c in clashes
                ],
            )
        )
    return MarketView(campaign=campaign_out(campaign), markets=rows)
