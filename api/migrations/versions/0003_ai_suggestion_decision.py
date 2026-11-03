"""AI suggestions and the human decision on each.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

suggestion_action = postgresql.ENUM(
    "shift_start",
    "shift_end",
    "note_messaging",
    "no_change",
    name="suggestion_action",
    create_type=False,
)
verdict = postgresql.ENUM("accepted", "rejected", name="verdict", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    suggestion_action.create(bind, checkfirst=False)
    verdict.create(bind, checkfirst=False)
    op.create_table(
        "ai_suggestion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "market_plan_id",
            sa.Uuid(),
            sa.ForeignKey("market_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", suggestion_action, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("model_deployment", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_suggestion_market_plan_id", "ai_suggestion", ["market_plan_id"])
    op.create_table(
        "decision",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.Uuid(),
            sa.ForeignKey("ai_suggestion.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("verdict", verdict, nullable=False),
        sa.Column("decided_by", sa.String(120), nullable=False),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("decision")
    op.drop_index("ix_ai_suggestion_market_plan_id", table_name="ai_suggestion")
    op.drop_table("ai_suggestion")
    bind = op.get_bind()
    verdict.drop(bind, checkfirst=False)
    suggestion_action.drop(bind, checkfirst=False)
