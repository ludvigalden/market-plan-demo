"""Public-holiday cache filled from the external holiday API.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holiday",
        sa.Column("market_code", sa.CHAR(2), sa.ForeignKey("market.code"), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "holiday_sync",
        sa.Column("market_code", sa.CHAR(2), sa.ForeignKey("market.code"), primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("holiday_sync")
    op.drop_table("holiday")
