"""Add indexes, prompt versioning columns, config trigger, fix circular FK

Revision ID: 0015
Revises: 20260606_0014
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "20260606_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Change 6: Prompt versioning ---
    op.add_column("test_runs", sa.Column("system_prompt_hash", sa.String(64), nullable=True))
    op.add_column("test_runs", sa.Column("system_prompt_text", sa.Text(), nullable=True))

    # --- Change 3: Missing indexes ---
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'game_events' AND column_name = 'agent_decision_id'
            ) THEN
                CREATE INDEX IF NOT EXISTS idx_game_events_agent_decision_id ON game_events (agent_decision_id);
            END IF;
        END $$;
    """)
    op.create_index("idx_screenshots_game_event_id", "notable_event_screenshots", ["game_event_id"], unique=False)
    op.create_index("idx_defects_report_id", "defects", ["report_id"], unique=False)
    op.create_index("idx_test_runs_outcome", "test_runs", ["outcome"], unique=False)
    op.create_index("idx_test_runs_llm_model", "test_runs", ["llm_model"], unique=False)
    op.create_index("idx_test_reports_generation_status", "test_reports", ["generation_status"], unique=False)

    # --- Change 3: config_entries auto-update trigger ---
    op.execute("""
        CREATE OR REPLACE FUNCTION update_config_entries_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_config_entries_updated
            BEFORE UPDATE ON config_entries
            FOR EACH ROW
            EXECUTE FUNCTION update_config_entries_timestamp()
    """)

    # --- Change 4: Fix circular FK (idempotent — column may already be absent) ---
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'game_events' AND column_name = 'agent_decision_id'
            ) THEN
                ALTER TABLE game_events DROP CONSTRAINT IF EXISTS game_events_agent_decision_id_fkey;
                ALTER TABLE game_events DROP COLUMN agent_decision_id;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # --- Change 4: Restore circular FK (idempotent) ---
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'game_events' AND column_name = 'agent_decision_id'
            ) THEN
                ALTER TABLE game_events ADD COLUMN agent_decision_id UUID;
                ALTER TABLE game_events ADD CONSTRAINT game_events_agent_decision_id_fkey
                    FOREIGN KEY (agent_decision_id) REFERENCES agent_decisions(id) ON DELETE SET NULL;
                CREATE INDEX IF NOT EXISTS idx_game_events_agent_decision_id ON game_events (agent_decision_id);
            END IF;
        END $$;
    """)

    # --- Change 3: Remove trigger and indexes ---
    op.execute("DROP TRIGGER IF EXISTS trg_config_entries_updated ON config_entries")
    op.execute("DROP FUNCTION IF EXISTS update_config_entries_timestamp()")
    op.drop_index("idx_test_reports_generation_status", table_name="test_reports")
    op.drop_index("idx_test_runs_llm_model", table_name="test_runs")
    op.drop_index("idx_test_runs_outcome", table_name="test_runs")
    op.drop_index("idx_defects_report_id", table_name="defects")
    op.drop_index("idx_screenshots_game_event_id", table_name="notable_event_screenshots")

    # --- Change 6: Remove prompt versioning columns ---
    op.drop_column("test_runs", "system_prompt_text")
    op.drop_column("test_runs", "system_prompt_hash")
