# Alembic Migrations

Located in `Backend/migrations/`. Async Alembic using `async_engine_from_config`.

## Migration History

| Revision | Date | Description |
|----------|------|-------------|
| `0001_initial_schema` | 2026-05-22 | Bootstrap: runs `schema.sql` with custom SQL statement splitter (handles dollar quoting, comments, quoted semicolons) |
| `0002_add_behavior_profile` | 2026-05-23 | Adds `behavior_profile` column to `test_runs` |
| `0003_config_entries_and_tokens` | 2026-05-23 | Creates `config_entries` table, adds token tracking columns to `agent_decisions` |
| `0004_rename_behavior_profiles` | 2026-05-23 | Renames profiles: speedrunner→fast, safety→thorough, exploit_hunter→exploit_focused |
| `0005_add_wad_memory_tables` | 2026-05-24 | Creates `wad_spatial_memory`, `wad_hypotheses`, `wad_knowledge_base` tables; updates default models |
| `0006_add_is_sentinel` | 2026-05-29 | Adds `is_sentinel` flag to `agent_position_trail` |
| `0007_persisted_run_evidence` | 2026-05-31 | Adds `angle` to position_trail, `guard_modified` to agent_decisions, `environment_metadata` to test_runs |
| `0008_llm_directed_runtime_cleanup` | 2026-05-31 | Drops UNIQUE constraint on `game_events(run_id,tick)`, adds `decision_source` to agent_decisions, drops `wad_knowledge_base` |
| `0009_harness_evidence` | 2026-06-02 | Adds `seed`, `start_normalization`, `raw_llm_decision`, `guard_reason`, `report_model`; fixes FK constraint; adds position_trail index |
| `0010_backfill_candidate_evidence` | 2026-06-02 | Backfills `defect.resolution_status` to 'candidate' for agent-observed and static risk defect types |
| `0013_restore_missing_local_head` | 2026-06-03 | Empty revision to anchor a missing local head for lineage continuity |
| `0014_add_report_evidence` | 2026-06-06 | Adds `qa_sections` and `evidence_matrix` JSONB to `test_reports`, widens `sha256_hash`, fixes `config_entries` NOT NULL, adds composite index |

## Schema Evolution Patterns

- **Custom SQL splitter**: `0001` uses a custom statement splitter that respects dollar-quoting (`$$`), SQL comments (`--`), and quoted semicolons
- **ALTER TABLE IF NOT EXISTS**: Used in `schema.sql` for idempotent migration patterns
- **Data backfill**: `0010` backfills existing records with default values
- **Empty revisions**: `0013` uses a no-op revision for lineage repair
- **Composite indexes**: `0014` adds composite index for common query patterns

## Running Migrations

```bash
cd Backend

# Create initial database
make db-init

# Apply all pending migrations
make db-upgrade

# Check current migration status
.venv/bin/alembic current

# Generate a new migration
.venv/bin/alembic revision --autogenerate -m "description"

# Rollback one migration
.venv/bin/alembic downgrade -1
```

## Key Constraints

- `game_events(run_id, tick_number)`: NOT unique (multiple events per tick allowed), ordered by `(tick_number, id)`
- `agent_position_trail.is_sentinel`: Marks internal boundary rows, excluded from public API queries
- `wad_knowledge_base`: Removed by migration `0008`, replaced by `wad_hypotheses`
- `test_reports.run_id`: UNIQUE constraint (one report per run)
- `static_analysis_results.wad_file_id`: UNIQUE constraint (one analysis per WAD)
