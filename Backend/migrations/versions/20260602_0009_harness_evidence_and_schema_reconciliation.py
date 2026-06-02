"""harness evidence and schema reconciliation

Revision ID: 20260602_0009
Revises: 20260531_0008
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op

revision = "20260602_0009"
down_revision = "20260531_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS seed INTEGER;")
    op.execute("ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS start_normalization JSONB;")
    op.execute("ALTER TABLE agent_decisions ADD COLUMN IF NOT EXISTS raw_llm_decision JSONB;")
    op.execute("ALTER TABLE agent_decisions ADD COLUMN IF NOT EXISTS guard_reason TEXT;")
    op.execute("ALTER TABLE test_reports ADD COLUMN IF NOT EXISTS report_model VARCHAR(128);")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_position_trail_run_id_tick
        ON agent_position_trail (run_id, tick_number);
        """
    )
    op.execute(
        """
        DO $$
        DECLARE constraint_name TEXT;
        BEGIN
            SELECT conname INTO constraint_name
            FROM pg_constraint
            WHERE conrelid = 'test_runs'::regclass
              AND contype = 'f'
              AND confrelid = 'wad_files'::regclass;
            IF constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE test_runs DROP CONSTRAINT %I', constraint_name);
            END IF;
            ALTER TABLE test_runs
                ADD CONSTRAINT test_runs_wad_file_id_fkey
                FOREIGN KEY (wad_file_id) REFERENCES wad_files(id) ON DELETE CASCADE;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_position_trail_run_id_tick;")
    op.execute("ALTER TABLE test_reports DROP COLUMN IF EXISTS report_model;")
    op.execute("ALTER TABLE agent_decisions DROP COLUMN IF EXISTS guard_reason;")
    op.execute("ALTER TABLE agent_decisions DROP COLUMN IF EXISTS raw_llm_decision;")
    op.execute("ALTER TABLE test_runs DROP COLUMN IF EXISTS start_normalization;")
    op.execute("ALTER TABLE test_runs DROP COLUMN IF EXISTS seed;")
