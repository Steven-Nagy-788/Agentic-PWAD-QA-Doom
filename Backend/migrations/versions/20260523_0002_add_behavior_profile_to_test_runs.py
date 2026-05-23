"""add behavior_profile to test_runs

Revision ID: 20260523_0002
Revises: 20260522_0001
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_0002"
down_revision = "20260522_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_runs",
        sa.Column("behavior_profile", sa.String(32), server_default="thorough", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("test_runs", "behavior_profile")
