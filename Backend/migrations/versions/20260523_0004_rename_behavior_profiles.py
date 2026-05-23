"""rename behavior profiles: speedrunner->fast, safety->thorough, exploit_hunter->exploit_focused

Revision ID: 20260523_0004
Revises: 20260523_0003
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op


revision = "20260523_0004"
down_revision = "20260523_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE test_runs SET behavior_profile = 'fast' WHERE behavior_profile = 'speedrunner'")
    op.execute("UPDATE test_runs SET behavior_profile = 'thorough' WHERE behavior_profile = 'safety'")
    op.execute("UPDATE test_runs SET behavior_profile = 'exploit_focused' WHERE behavior_profile = 'exploit_hunter'")


def downgrade() -> None:
    op.execute("UPDATE test_runs SET behavior_profile = 'speedrunner' WHERE behavior_profile = 'fast'")
    op.execute("UPDATE test_runs SET behavior_profile = 'safety' WHERE behavior_profile = 'thorough'")
    op.execute("UPDATE test_runs SET behavior_profile = 'exploit_hunter' WHERE behavior_profile = 'exploit_focused'")
