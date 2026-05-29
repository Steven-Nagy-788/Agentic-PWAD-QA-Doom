"""add is_sentinel to agent_position_trail

Revision ID: 20260529_0006
Revises: 20260524_0005
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0006"
down_revision = "20260524_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_position_trail
        ADD COLUMN IF NOT EXISTS is_sentinel BOOLEAN NOT NULL DEFAULT FALSE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_position_trail
        DROP COLUMN IF EXISTS is_sentinel;
        """
    )
