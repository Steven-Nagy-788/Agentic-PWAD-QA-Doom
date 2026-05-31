"""add config_entries and token columns to agent_decisions

Revision ID: 20260523_0003
Revises: 20260523_0002
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op


revision = "20260523_0003"
down_revision = "20260523_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS config_entries (
            key VARCHAR(128) PRIMARY KEY,
            value JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
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
