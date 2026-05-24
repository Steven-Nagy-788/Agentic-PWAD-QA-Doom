"""add persistent WAD memory tables

Revision ID: 20260524_0005
Revises: 20260523_0004
Create Date: 2026-05-24
"""

from __future__ import annotations

from alembic import op


revision = "20260524_0005"
down_revision = "20260523_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wad_spatial_memory (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wad_file_id UUID NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
            map_name VARCHAR(16) NOT NULL,
            cell_x SMALLINT NOT NULL,
            cell_y SMALLINT NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            occurrence_count BIGINT NOT NULL DEFAULT 1,
            last_seen_run_id UUID REFERENCES test_runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_spatial_cell_event UNIQUE (wad_file_id, map_name, cell_x, cell_y, event_type)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_spatial_wad_map ON wad_spatial_memory(wad_file_id, map_name)")
    op.execute("ALTER TABLE IF EXISTS wad_spatial_memory ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    op.execute("ALTER TABLE IF EXISTS wad_spatial_memory ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wad_hypotheses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wad_file_id UUID NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
            map_name VARCHAR(16) NOT NULL,
            tag VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5,
            confirmed_at TIMESTAMPTZ,
            refuted_at TIMESTAMPTZ,
            last_seen_run_id UUID REFERENCES test_runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_hypotheses_wad_map ON wad_hypotheses(wad_file_id, map_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hypotheses_tag ON wad_hypotheses(wad_file_id, map_name, tag)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wad_knowledge_base (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wad_file_id UUID NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
            map_name VARCHAR(16) NOT NULL,
            document_text TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_knowledge_wad_map UNIQUE (wad_file_id, map_name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_wad_map ON wad_knowledge_base(wad_file_id, map_name)")
    op.execute("ALTER TABLE test_runs ALTER COLUMN llm_model SET DEFAULT 'gemini-2.5-flash-lite'")
    op.execute("ALTER TABLE test_runs ALTER COLUMN behavior_profile SET DEFAULT 'thorough'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wad_knowledge_base")
    op.execute("DROP TABLE IF EXISTS wad_hypotheses")
    op.execute("DROP TABLE IF EXISTS wad_spatial_memory")
    op.execute("ALTER TABLE test_runs ALTER COLUMN llm_model SET DEFAULT 'gemini-2.5-flash'")
    op.execute("ALTER TABLE test_runs ALTER COLUMN behavior_profile SET DEFAULT 'safety'")
