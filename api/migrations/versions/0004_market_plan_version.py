"""Optimistic-concurrency version on market plans, added as an expand step.

The column is added nullable with a server default so existing rows and
running writers keep working, existing rows are backfilled, and only then is
NOT NULL enforced.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_plan",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=True),
    )
    op.execute("UPDATE market_plan SET version = 1 WHERE version IS NULL")
    op.alter_column("market_plan", "version", nullable=False)
    op.create_check_constraint("ck_market_plan_version_positive", "market_plan", "version >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_market_plan_version_positive", "market_plan", type_="check")
    op.drop_column("market_plan", "version")
