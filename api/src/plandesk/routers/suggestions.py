"""AI adaptation proposals, human decisions, and the audit log."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from plandesk.convert import plan_out, suggestion_out
from plandesk.deps import CurrentUser, Holidays, Provider, Session
from plandesk.errors import ERROR_RESPONSES, Conflict, NotFound, UpstreamUnavailable
from plandesk.models import (
    AiSuggestion,
    Decision,
    MarketPlan,
    PlanStatus,
    SuggestionAction,
    Verdict,
)
from plandesk.routers.campaigns import load_campaign
from plandesk.schemas import (
    AuditEntry,
    DecisionOut,
    DecisionRequest,
    SuggestionOut,
    SuggestRequest,
    SuggestResult,
)
from plandesk.services.adaptation import AdaptationInput, PlanFacts, validate_proposals
from plandesk.services.clashes import detect_clashes
from plandesk.services.holidays import holidays_for

router = APIRouter(tags=["suggestions"], responses=ERROR_RESPONSES)


@router.post("/campaigns/{campaign_id}/suggestions", response_model=SuggestResult)
async def create_suggestions(
    campaign_id: uuid.UUID,
    session: Session,
    holidays: Holidays,
    provider: Provider,
    body: SuggestRequest | None = None,
) -> SuggestResult:
    """Ask the model for local adaptations. Proposals are validated, stored, and never applied."""
    campaign = await load_campaign(session, campaign_id)
    only = {c.upper() for c in body.market_codes} if body and body.market_codes else None
    plans = [p for p in campaign.plans if only is None or p.market_code in only]
    facts: list[PlanFacts] = []
    unavailable: list[str] = []
    for plan in sorted(plans, key=lambda p: p.market_code):
        lookup = await holidays_for(
            session, holidays, plan.market_code, campaign.window_start, campaign.window_end
        )
        if not lookup.available:
            unavailable.append(plan.market_code)
            continue
        clashes = detect_clashes(plan.start_date, plan.end_date, lookup.holidays)
        facts.append(
            PlanFacts(
                market_code=plan.market_code,
                start=plan.start_date,
                end=plan.end_date,
                clashes=clashes,
                holiday_dates=frozenset(h.date for h in lookup.holidays),
            )
        )
    reasons = [f"{c}: holidays unavailable, market skipped" for c in unavailable]
    with_clashes = [f for f in facts if f.clashes]
    if not with_clashes:
        return SuggestResult(suggestions=[], rejected_by_validator=0, rejection_reasons=reasons)

    inp = AdaptationInput(
        window_start=campaign.window_start, window_end=campaign.window_end, plans=with_clashes
    )
    try:
        result = await provider.propose(inp)
    except Exception as exc:
        raise UpstreamUnavailable(f"AI provider failed: {type(exc).__name__}") from exc
    outcome = validate_proposals(result.raw, inp)

    by_code = {p.market_code: p for p in plans}
    stored: list[AiSuggestion] = []
    for item in outcome.accepted:
        s = AiSuggestion(
            market_plan_id=by_code[item.market_code].id,
            action=item.action,
            payload={
                "flag_date": item.flag_date.isoformat() if item.flag_date else None,
                "new_date": item.new_date.isoformat() if item.new_date else None,
            },
            rationale=item.rationale,
            model_deployment=result.model_deployment,
            prompt_version=result.prompt_version,
        )
        session.add(s)
        stored.append(s)
    await session.commit()
    ids = [s.id for s in stored]
    return SuggestResult(
        suggestions=[suggestion_out(s) for s in await _load_suggestions(session, ids)],
        rejected_by_validator=len(outcome.rejected),
        rejection_reasons=reasons + outcome.rejected,
    )


async def _load_suggestions(session: Session, ids: list[uuid.UUID]) -> list[AiSuggestion]:
    if not ids:
        return []
    rows = (
        (
            await session.scalars(
                select(AiSuggestion)
                .where(AiSuggestion.id.in_(ids))
                .options(joinedload(AiSuggestion.plan).joinedload(MarketPlan.market))
                .execution_options(populate_existing=True)
            )
        )
        .unique()
        .all()
    )
    order = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda s: order[s.id])


@router.get("/campaigns/{campaign_id}/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(campaign_id: uuid.UUID, session: Session) -> list[SuggestionOut]:
    await load_campaign(session, campaign_id)
    rows = (
        (
            await session.scalars(
                select(AiSuggestion)
                .join(AiSuggestion.plan)
                .where(MarketPlan.campaign_id == campaign_id)
                .options(joinedload(AiSuggestion.plan).joinedload(MarketPlan.market))
                .order_by(AiSuggestion.created_at, MarketPlan.market_code, AiSuggestion.id)
            )
        )
        .unique()
        .all()
    )
    return [suggestion_out(s) for s in rows]


async def _decide(
    suggestion_id: uuid.UUID,
    body: DecisionRequest,
    verdict: Verdict,
    session: Session,
    user: str,
) -> DecisionOut:
    rows = await _load_suggestions(session, [suggestion_id])
    if not rows:
        raise NotFound(f"suggestion {suggestion_id} not found")
    s = rows[0]
    if s.decision is not None:
        raise Conflict(f"suggestion already {s.decision.verdict.value}")
    plan = s.plan
    if plan.version != body.expected_plan_version:
        raise Conflict(
            f"plan changed (version {plan.version}, expected {body.expected_plan_version}); reload and retry"
        )
    if verdict is Verdict.accepted:
        new_date = s.payload.get("new_date")
        if s.action is SuggestionAction.shift_start and isinstance(new_date, str):
            plan.start_date = dt.date.fromisoformat(new_date)
        elif s.action is SuggestionAction.shift_end and isinstance(new_date, str):
            plan.end_date = dt.date.fromisoformat(new_date)
        plan.status = PlanStatus.adapted
    # Every decision bumps the plan version (an UPDATE is forced even when no
    # column changed), so two planners deciding on one plan cannot both win.
    flag_modified(plan, "status")
    session.add(Decision(suggestion_id=s.id, verdict=verdict, decided_by=user))
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise Conflict("plan changed concurrently; reload and retry") from exc
    fresh = (await _load_suggestions(session, [suggestion_id]))[0]
    campaign = await load_campaign(session, plan.campaign_id)
    return DecisionOut(
        suggestion=suggestion_out(fresh), plan=plan_out(fresh.plan, campaign.global_budget_eur)
    )


@router.post("/suggestions/{suggestion_id}/accept", response_model=DecisionOut)
async def accept_suggestion(
    suggestion_id: uuid.UUID, body: DecisionRequest, session: Session, user: CurrentUser
) -> DecisionOut:
    """Apply the suggestion to the plan if the plan is still at the version the planner saw."""
    return await _decide(suggestion_id, body, Verdict.accepted, session, user)


@router.post("/suggestions/{suggestion_id}/reject", response_model=DecisionOut)
async def reject_suggestion(
    suggestion_id: uuid.UUID, body: DecisionRequest, session: Session, user: CurrentUser
) -> DecisionOut:
    """Record a rejection; the plan dates are untouched."""
    return await _decide(suggestion_id, body, Verdict.rejected, session, user)


@router.get("/campaigns/{campaign_id}/audit", response_model=list[AuditEntry])
async def list_audit(campaign_id: uuid.UUID, session: Session) -> list[AuditEntry]:
    await load_campaign(session, campaign_id)
    rows = (
        (
            await session.scalars(
                select(Decision)
                .join(Decision.suggestion)
                .join(AiSuggestion.plan)
                .where(MarketPlan.campaign_id == campaign_id)
                .options(joinedload(Decision.suggestion).joinedload(AiSuggestion.plan))
                .order_by(Decision.decided_at.desc(), Decision.id)
            )
        )
        .unique()
        .all()
    )
    return [
        AuditEntry(
            decision_id=d.id,
            suggestion_id=d.suggestion_id,
            market_code=d.suggestion.plan.market_code,
            action=d.suggestion.action,
            verdict=d.verdict,
            decided_by=d.decided_by,
            decided_at=d.decided_at,
            rationale=d.suggestion.rationale,
            model_deployment=d.suggestion.model_deployment,
            prompt_version=d.suggestion.prompt_version,
        )
        for d in rows
    ]
