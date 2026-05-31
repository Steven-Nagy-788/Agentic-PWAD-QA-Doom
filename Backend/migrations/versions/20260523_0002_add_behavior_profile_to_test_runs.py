"""add behavior_profile to test_runs

Revision ID: 20260523_0002
Revises: 20260522_0001
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op


revision = "20260523_0002"
down_revision = "20260522_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE test_runs
        ADD COLUMN IF NOT EXISTS behavior_profile VARCHAR(32) DEFAULT 'thorough';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE test_runs DROP COLUMN IF EXISTS behavior_profile;")
