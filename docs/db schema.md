# Database Schema Notes

The executable schema lives in `Backend/sql/schema.sql`; incremental changes live in `Backend/migrations/versions/`.

## Main Tables

| Table | Purpose |
| --- | --- |
| `wad_files` | Uploaded WAD metadata, validation status, detected maps, storage path, hash, IWAD requirement. |
| `static_analysis_results` | Per-WAD/per-map static analysis: geometry, thing counts, skill summaries, balance metrics, map PNG path. |
| `test_runs` | One QA run: selected WAD/map, status, outcome, LLM model, behavior profile, final metrics, artifact paths. |
| `agent_decisions` | Ordered LLM decisions, raw inputs/outputs, MCP tool calls, token usage, cost estimates, latency. |
| `game_events` | Ordered telemetry/events from the run loop. |
| `agent_position_trail` | Position samples used for coverage, trails, and report visualizations. |
| `defects` | Static/runtime/agent-observed defects, severity, evidence, fingerprinting. |
| `test_reports` | Report metadata and generated PDF path. |
| `notable_event_screenshots` | Evidence screenshots for report/event context. |
| `config_entries` | Runtime settings overrides shown in `/v1/settings`. |
| `wad_spatial_memory` | Per-WAD/per-map grid-cell memory for stuck/death/resource/key/secret/visited events. |
| `wad_hypotheses` | Cross-run hypotheses about a WAD/map. |
| `wad_knowledge_base` | Cross-run text knowledge documents. |

## Schema Management

For a new local database:

```bash
cd Backend
make db-init
make db-upgrade
```

For direct bootstrap without Alembic:

```bash
cd Backend
make db-schema
```

When models change:

```bash
cd Backend
MSG="describe change" make db-migrate
make db-upgrade
```

## Current Migration Chain

- `20260522_0001_initial_schema.py`
- `20260523_0002_add_behavior_profile_to_test_runs.py`
- `20260523_0003_add_config_entries_and_token_fields.py`
- `20260523_0004_rename_behavior_profiles.py`
- `20260524_0005_add_wad_memory_tables.py`

## Notes

Static analysis is implemented in Python using `omgifol` plus local constants and heuristics in `Backend/app/services/analysis_service.py` and `analysis_constants.py`.

The current simulator integration is `mcp-doom` using the `vizdoom` Python package directly through FastMCP. There is no forked external Doom MCP repository in the active implementation.
