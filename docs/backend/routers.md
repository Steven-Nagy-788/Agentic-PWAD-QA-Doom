# API Routers

All under `/v1` prefix (rewritten by Next.js from `/api/v1`). Located in `Backend/app/routers/`.

## 1. `runs.py` — Run Management (~250 lines)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/runs` | Create new run (validates WAD, no active run for WAD, spawns task) |
| GET | `/runs` | List runs (pagination, filter by WAD+map+outcome+difficulty+behavior+date) |
| GET | `/runs/{id}` | Get run detail |
| DELETE | `/runs/{id}` | Cancel + delete run (cascading: recording, screenshots, report) |
| POST | `/runs/{id}/cancel` | Signal cancellation to running task |
| GET | `/runs/{id}/state` | Current run state snapshot |
| GET | `/runs/{id}/trace` | Full decision trace (paginated) |
| GET | `/runs/{id}/events` | Game events (paginated, filterable by event_type) |
| GET | `/runs/{id}/decisions` | Agent decisions (paginated) |
| GET | `/runs/{id}/defects` | Detected defects |
| GET | `/runs/{id}/recording` | Serve MP4 recording file |
| GET | `/runs/{id}/position-trail` | Position trail (with is_sentinel excluded) |
| GET | `/runs/{id}/usage` | LLM token usage and cost |
| GET | `/runs/{id}/benchmark` | Performance metrics (latency percentiles, tool counts) |
| GET | `/runs/{id}/report` | Report metadata |
| GET | `/runs/{id}/report/status` | Generation status |
| GET | `/runs/{id}/screenshots` | List screenshots |
| GET | `/runs/{id}/live-snapshot` | Current state for live reconnect |
| PATCH | `/runs/{id}/behavior` | Update behavior profile mid-run |

## 2. `wads.py` — WAD Management (~200 lines)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/wads/upload` | Upload .wad file (validated, SHA-256, stored) |
| GET | `/wads` | List all WAD files |
| GET | `/wads/{id}` | Get WAD detail |
| DELETE | `/wads/{id}` | Delete WAD (fails if active run exists) |
| GET | `/wads/{id}/analysis` | Per-map static analysis results |
| GET | `/wads/{id}/analysis/overview` | Aggregated analysis overview |
| GET | `/wads/{id}/maps` | List maps in WAD |
| GET | `/wads/{id}/maps/{map_name}/overview` | Map overview PNG |
| GET | `/wads/{id}/runs` | Runs for this WAD |
| POST | `/wads/{id}/reanalyze` | Trigger reanalysis |
| GET | `/wads/maps` | All maps across all WADs (limit param) |

## 3. `reports.py` — Report Management (~50 lines)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/runs/{run_id}/report/regenerate` | Regenerate report (only if terminal) |
| GET | `/runs/{run_id}/report/status` | Report status |
| GET | `/runs/{run_id}/report/pdf` | Serve PDF file |

## 4. `ws.py` — WebSocket (~25 lines)

| Path | Description |
|------|-------------|
| `/ws/v1/runs/{run_id}` | Live run streaming (binary frames with JSON messages) |

Message types: `ping`, `pong`, `replay_start`, `replay_end`, `frame`, `state`, `llm_start`, `llm_decision`, `mcp_call_start`, `mcp_call_result`, `progress`, `defect`. Cache last N messages per run for replay on reconnect.

## 5. `analysis.py` — Static Analysis (~30 lines)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/wads/{wad_id}/analysis/{map_name}` | Detailed analysis for a specific map |

## 6. `patterns.py` — Cross-Run Patterns (~30 lines)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/wads/{id}/patterns` | Cross-run defect patterns (grouping, clustering, difficulty coverage) |

## 7. `admin_storage.py` — Storage Admin (~80 lines)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/storage/summary` | Storage usage by category |
| DELETE | `/admin/storage/cleanup` | Clean orphaned files |

## 8. `settings.py` — Runtime Settings (~30 lines)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings` | Get all runtime settings |
| POST | `/settings` | Set setting |
| PATCH | `/settings` | Update setting |

## 9. `memory.py` — Cross-Run Memory (~50 lines)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/memory/wad/{wad_id}` | Spatial memory for a WAD |
| GET | `/memory/wad/{wad_id}/hypotheses` | Hypotheses for a WAD |
