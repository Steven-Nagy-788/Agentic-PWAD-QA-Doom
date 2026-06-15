# Database Schema

PostgreSQL 16 via asyncpg + SQLAlchemy 2.0 async. Alembic migrations are authoritative.

## Table Groups

### Uploads & Analysis

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `wad_files` | Uploaded PWAD files | SHA-256 hash, detected maps, IWAD type |
| `static_analysis_results` | Per-map analysis | Thing/enemy/item counts, spawn summaries, map features, overview PNG |

### Run Evidence (core)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `test_runs` | QA run records | Status, outcome, metrics, recording, behavior profile |
| `agent_decisions` | Every LLM→MCP decision | LLM input/output, MCP input/output, timing, guard flags |
| `game_events` | Per-tick telemetry | Position, health, ammo, kills, event type, action taken |
| `agent_position_trail` | Position history | Condensed trail with health, sentinel markers |

### Findings

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `defects` | Detected issues | Severity (1-4), type, fingerprint, position, occurrence |
| `notable_event_screenshots` | Screenshot evidence | Links screenshot path to game event |
| `test_reports` | Generated PDF reports | 14 QA sections, evidence matrix, verdict, PDF path |

### Reviewer Analytics

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `wad_spatial_memory` | Cross-run spatial data | 256-unit grid cells, event type count, last seen |
| `wad_hypotheses` | Cross-run hypotheses | Tagged observations with confidence (0.0-1.0) |

### Runtime

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `config_entries` | Runtime key-value overrides | JSONB value, auto-updated timestamp |

## Important Constraints

1. **game_events**: Multiple rows may share the same `(run_id, tick_number)`. Ordered by `(tick_number, id)` for deterministic ordering. The original UNIQUE constraint was dropped by migration `0008`.

2. **agent_position_trail**: `is_sentinel=True` marks internal boundary rows that are excluded from public API queries. Added by migration `0006`.

3. **agent_decisions**: `decision_source` tracks origin: `llm`, `deterministic_fallback`, or `guard`. Added by migration `0008`.

4. **wad_knowledge_base**: This table existed briefly and was removed by migration `0008`. Replaced by `wad_hypotheses` with more flexible schema.

5. **test_reports.run_id**: UNIQUE constraint — exactly one report per run.

6. **static_analysis_results.wad_file_id**: UNIQUE constraint — one analysis per WAD.

## Full DDL

See `Backend/sql/schema.sql` for the complete DDL with indexes, foreign keys, and constraints.

## Entity-Relationship

```
wad_files ──┬── static_analysis_results
            │
            └── test_runs ──┬── agent_decisions
                            ├── game_events ── notable_event_screenshots
                            ├── agent_position_trail
                            ├── defects
                            └── test_reports

wad_files ──┬── wad_spatial_memory
            └── wad_hypotheses
```
