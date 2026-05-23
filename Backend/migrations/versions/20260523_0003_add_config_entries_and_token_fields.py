"""add config_entries and token columns to agent_decisions

Revision ID: 20260523_0003
Revises: 20260523_0002
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260523_0003"
down_revision = "20260523_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "config_entries",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "ALTER TABLE agent_decisions "
        "ADD COLUMN IF NOT EXISTS llm_input_tokens INTEGER, "
        "ADD COLUMN IF NOT EXISTS llm_output_tokens INTEGER, "
        "ADD COLUMN IF NOT EXISTS llm_cost_estimate_usd REAL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS config_entries")
    op.execute(
        "ALTER TABLE agent_decisions "
        "DROP COLUMN IF EXISTS llm_input_tokens, "
        "DROP COLUMN IF EXISTS llm_output_tokens, "
        "DROP COLUMN IF EXISTS llm_cost_estimate_usd"
    )
