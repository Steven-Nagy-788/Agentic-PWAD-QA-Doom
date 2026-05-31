"""llm directed runtime cleanup

Revision ID: 20260531_0008
Revises: 20260531_0007
Create Date: 2026-05-31
"""
from __future__ import annotations

from alembic import op

revision = "20260531_0008"
down_revision = "20260531_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE game_events
        DROP CONSTRAINT IF EXISTS game_events_run_id_tick_number_key;
        """
    )
    op.execute(
        """
        ALTER TABLE agent_decisions
        ADD COLUMN IF NOT EXISTS decision_source VARCHAR(32) NOT NULL DEFAULT 'gemini';
        """
    )
    op.execute("DROP TABLE IF EXISTS wad_knowledge_base;")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wad_knowledge_base (
            id UUID PRIMARY KEY,
            wad_file_id UUID NOT NULL REFERENCES wad_files(id) ON DELETE CASCADE,
            map_name VARCHAR(16) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            document_text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (wad_file_id, map_name)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_wad_map
        ON wad_knowledge_base (wad_file_id, map_name);
        """
    )
    op.execute(
        """
        ALTER TABLE agent_decisions
        DROP COLUMN IF EXISTS decision_source;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'game_events_run_id_tick_number_key'
            ) THEN
                ALTER TABLE game_events
                ADD CONSTRAINT game_events_run_id_tick_number_key
                UNIQUE (run_id, tick_number);
            END IF;
        END $$;
        """
    )
