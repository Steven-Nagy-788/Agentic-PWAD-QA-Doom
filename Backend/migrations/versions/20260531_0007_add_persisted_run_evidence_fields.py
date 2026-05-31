"""add persisted run evidence fields

Revision ID: 20260531_0007
Revises: 20260529_0006
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op


revision = "20260531_0007"
down_revision = "20260529_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_position_trail
        ADD COLUMN IF NOT EXISTS angle REAL NOT NULL DEFAULT 0;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_decisions
        ADD COLUMN IF NOT EXISTS guard_modified BOOLEAN NOT NULL DEFAULT FALSE;
        """
    )
    op.execute(
        """
        ALTER TABLE test_runs
        ADD COLUMN IF NOT EXISTS environment_metadata JSONB;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE test_runs
        DROP COLUMN IF EXISTS environment_metadata;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_decisions
        DROP COLUMN IF EXISTS guard_modified;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_position_trail
        DROP COLUMN IF EXISTS angle;
        """
    )
