"""Markets, campaigns and market plans, with the seed markets.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

plan_status = postgresql.ENUM("draft", "adapted", name="plan_status", create_type=False)

SEED_MARKETS = [
    ("DE", "Germany", "EUR"),
    ("FR", "France", "EUR"),
    ("JP", "Japan", "JPY"),
    ("SE", "Sweden", "SEK"),
    ("US", "United States", "USD"),
]


def upgrade() -> None:
    market = op.create_table(
        "market",
        sa.Column("code", sa.CHAR(2), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
    )
    op.bulk_insert(market, [{"code": c, "name": n, "currency": cur} for c, n, cur in SEED_MARKETS])

    op.create_table(
        "campaign",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("global_budget_eur", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("window_end >= window_start", name="ck_campaign_window"),
        sa.CheckConstraint("global_budget_eur > 0", name="ck_campaign_budget_positive"),
    )

    plan_status.create(op.get_bind(), checkfirst=False)
    op.create_table(
        "market_plan",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market_code", sa.CHAR(2), sa.ForeignKey("market.code"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("budget_share", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", plan_status, nullable=False),
        sa.UniqueConstraint("campaign_id", "market_code"),
        sa.CheckConstraint("end_date >= start_date", name="ck_market_plan_dates"),
        sa.CheckConstraint("budget_share >= 0 AND budget_share <= 1", name="ck_market_plan_share"),
    )
    op.create_index("ix_market_plan_campaign_id", "market_plan", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_market_plan_campaign_id", table_name="market_plan")
    op.drop_table("market_plan")
    plan_status.drop(op.get_bind(), checkfirst=False)
    op.drop_table("campaign")
    op.drop_table("market")
