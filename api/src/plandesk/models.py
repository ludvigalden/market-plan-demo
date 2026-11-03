"""SQLAlchemy models. Alembic migrations under migrations/ are the schema source."""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PlanStatus(enum.StrEnum):
    draft = "draft"
    adapted = "adapted"


class SuggestionAction(enum.StrEnum):
    shift_start = "shift_start"
    shift_end = "shift_end"
    note_messaging = "note_messaging"
    no_change = "no_change"


class Verdict(enum.StrEnum):
    accepted = "accepted"
    rejected = "rejected"


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Market(Base):
    __tablename__ = "market"

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(CHAR(3))


class Campaign(Base):
    __tablename__ = "campaign"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    window_start: Mapped[dt.date] = mapped_column(Date)
    window_end: Mapped[dt.date] = mapped_column(Date)
    global_budget_eur: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    plans: Mapped[list[MarketPlan]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )


class MarketPlan(Base):
    __tablename__ = "market_plan"
    __table_args__ = (UniqueConstraint("campaign_id", "market_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaign.id", ondelete="CASCADE"), index=True
    )
    market_code: Mapped[str] = mapped_column(ForeignKey("market.code"))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)
    budget_share: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus, "plan_status"), default=PlanStatus.draft
    )
    version: Mapped[int] = mapped_column(Integer, server_default="1")

    campaign: Mapped[Campaign] = relationship(back_populates="plans")
    market: Mapped[Market] = relationship(lazy="joined")

    __mapper_args__ = {"version_id_col": version}


class Holiday(Base):
    __tablename__ = "holiday"

    market_code: Mapped[str] = mapped_column(ForeignKey("market.code"), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class HolidaySync(Base):
    """One row per (market, year) fetched from the holiday API, so an empty year is cached too."""

    __tablename__ = "holiday_sync"

    market_code: Mapped[str] = mapped_column(ForeignKey("market.code"), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiSuggestion(Base):
    __tablename__ = "ai_suggestion"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_plan.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[SuggestionAction] = mapped_column(_enum(SuggestionAction, "suggestion_action"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    model_deployment: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    plan: Mapped[MarketPlan] = relationship(lazy="joined")
    decision: Mapped[Decision | None] = relationship(
        back_populates="suggestion", lazy="joined", uselist=False
    )


class Decision(Base):
    __tablename__ = "decision"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_suggestion.id", ondelete="CASCADE"), unique=True
    )
    verdict: Mapped[Verdict] = mapped_column(_enum(Verdict, "verdict"))
    decided_by: Mapped[str] = mapped_column(String(120))
    decided_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    suggestion: Mapped[AiSuggestion] = relationship(back_populates="decision")
