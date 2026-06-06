"""add report evidence fields

Revision ID: 20260606_0014
Revises: 20260603_0013
Create Date: 2026-06-06
"""
from __future__ import annotations

from alembic import op

revision = "20260606_0014"
down_revision = "20260603_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE test_reports ADD COLUMN IF NOT EXISTS qa_sections JSONB;")
    op.execute("ALTER TABLE test_reports ADD COLUMN IF NOT EXISTS evidence_matrix JSONB;")
    op.execute("ALTER TABLE wad_files ALTER COLUMN sha256_hash TYPE VARCHAR(64);")
    op.execute("UPDATE config_entries SET updated_at = NOW() WHERE updated_at IS NULL;")
    op.execute("ALTER TABLE config_entries ALTER COLUMN updated_at SET NOT NULL;")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_test_runs_wad_map_created_at
        ON test_runs (wad_file_id, map_name, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE config_entries ALTER COLUMN updated_at DROP NOT NULL;")
    op.execute("ALTER TABLE test_reports DROP COLUMN IF EXISTS evidence_matrix;")
    op.execute("ALTER TABLE test_reports DROP COLUMN IF EXISTS qa_sections;")
