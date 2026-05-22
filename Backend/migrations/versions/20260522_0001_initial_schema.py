"""initial schema

Revision ID: 20260522_0001
Revises:
Create Date: 2026-05-22
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "20260522_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
    op.execute(schema_path.read_text())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS defects CASCADE")
    op.execute("DROP TABLE IF EXISTS test_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_position_trail CASCADE")
    op.execute("DROP TABLE IF EXISTS notable_event_screenshots CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_decisions CASCADE")
    op.execute("DROP TABLE IF EXISTS game_events CASCADE")
    op.execute("DROP TABLE IF EXISTS test_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS static_analysis_results CASCADE")
    op.execute("DROP TABLE IF EXISTS wad_files CASCADE")
