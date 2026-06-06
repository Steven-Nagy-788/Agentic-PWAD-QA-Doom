"""restore missing local head anchor

Revision ID: 20260603_0013
Revises: 20260602_0010
Create Date: 2026-06-03
"""
from __future__ import annotations

revision = "20260603_0013"
down_revision = "20260602_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision existed in the local demo database but was missing from
    # source control. Keeping it as an anchor lets fresh and existing databases
    # share one Alembic lineage.
    pass


def downgrade() -> None:
    pass
