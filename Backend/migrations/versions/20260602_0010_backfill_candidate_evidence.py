"""backfill candidate evidence

Revision ID: 20260602_0010
Revises: 20260602_0009
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op

revision = "20260602_0010"
down_revision = "20260602_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE defects
        SET resolution_status = 'candidate'
        WHERE defect_type LIKE 'agent_observed_%'
           OR defect_type LIKE 'visual_%'
           OR defect_type IN (
               'static_ammo_insufficiency',
               'static_health_insufficiency',
               'static_ammo_risk',
               'static_health_risk'
           );
        """
    )


def downgrade() -> None:
    # Candidate review is intentionally not undone: a downgrade cannot know
    # which model-derived findings a human validated after this migration.
    pass
