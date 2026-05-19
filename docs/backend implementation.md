# Agentic PWAD QA Backend Implementation

This document describes the current backend and MCP integration for the Agentic PWAD QA Doom project.

The system accepts Doom PWAD uploads, performs static map analysis with `omgifol`, stores WAD metadata and analysis in PostgreSQL, launches autonomous ViZDoom runs through the persistent `mcp-doom` FastMCP SSE server, streams run state over WebSocket, records gameplay artifacts, detects defects, and generates PDF QA reports.

## Runtime Architecture

The backend is a FastAPI application in `Backend/`. The adjacent `mcp-doom/` directory is a separate FastMCP service that wraps ViZDoom.

Expected local runtime:

1. PostgreSQL is running and `Backend/sql/schema.sql` has been applied.
2. `mcp-doom` is running on `MCP_DOOM_SSE_URL`, normally `http://localhost:8001/sse`.
3. FastAPI runs from `Backend/`.
4. The UI calls the HTTP API and subscribes to `/ws/runs/{run_id}` for live state.

Main backend layers:

```text
routers -> services -> repositories -> SQLAlchemy async models -> PostgreSQL
```

Key integrations:

- `omgifol` parses Doom-format WAD maps.
- Pillow renders static map overview PNGs.
- FastMCP client calls the Doom MCP server over SSE.
- Gemini can drive the agent and report generation; deterministic fallbacks are used when Gemini is unavailable.
- OpenCV and ffmpeg produce MP4 recordings.
- WeasyPrint renders PDF reports.

The backend and MCP server install a targeted warning filter before importing FastMCP entry points that transitively load Authlib JWT support. This suppresses the known third-party `authlib.jose` deprecation warning while leaving normal application errors visible.

## Configuration

Configuration is loaded in `app/core/config.py`. `Settings` manually reads `Backend/.env`, resolves relative storage paths under `Backend/`, and is cached through `get_settings()`.

Important settings:

- `DATABASE_URL` or `POSTGRES_*` values for PostgreSQL.
- `STORAGE_BASE`, `WAD_STORAGE_DIR`, `ANALYSIS_STORAGE_DIR`, `SCREENSHOT_STORAGE_DIR`, `RECORDING_STORAGE_DIR`, `REPORT_STORAGE_DIR`.
- `GEMINI_API_KEY`, `LLM_MODEL`, `LLM_THROTTLE_SECONDS`, `GEMINI_RETRY_MAX_DELAY_SECONDS`.
- `MCP_DOOM_SSE_URL`.
- `DEFAULT_RUN_TICKS`, `MAX_RUN_TICKS`, `LIVE_FRAME_FPS`, `RECORDING_TELEMETRY_STRIDE`.
- `CORS_ORIGINS`.

The backend passes `freedoom1` or `freedoom2` to MCP based on detected map names. It does not require an IWAD path in backend config.

## Database Schema

The schema is in `Backend/sql/schema.sql`. It is additive and can be re-applied with `make db-schema`.

### `wad_files`

Stores uploaded WAD metadata and a path to the file on disk.

Important fields:

- `original_filename`, `stored_path`, `file_size_bytes`, `sha256_hash`.
- `validation_status`, `validation_error`.
- `detected_maps`, such as `E1M1` or `MAP01`.
- `iwad_required`, derived from map naming (`E#M#` -> `freedoom1`, `MAP##` -> `freedoom2`).

Uploads are deduplicated by SHA-256. IWAD files and UDMF maps are rejected.

### `static_analysis_results`

Stores one row per `(wad_file_id, map_name)`.

Raw map-wide fields remain backward-compatible:

- Thing counts: `thing_count_total`, `thing_count_enemies`, `thing_count_items`, `thing_count_keys`, `thing_count_weapons`.
- Geometry counts: `linedef_count`, `sector_count`, `secret_sector_count`, `vertex_count`.
- Dimensions: `map_width_units`, `map_height_units`.
- Balance: `total_monster_hp`, `total_health_pickup_pts`, `total_armor_pickup_pts`, `hitscanner_percent`, `health_ratio`, `ammo_ratio`, `estimated_difficulty`.
- JSON: `enemy_breakdown`, `item_breakdown`.
- `map_overview_png_path`.

Current UI/report fields:

- `map_title`: optional title parsed from `MAPINFO` or `UMAPINFO`.
- `map_display_name`: title-aware UI label. Falls back to `<original_filename stem> - <map_name>`.
- `map_title_source`: `mapinfo`, `umapinfo`, or `fallback_filename`.
- `spawn_summary_by_skill`: JSON keyed by Doom difficulty `1` through `5`.

`spawn_summary_by_skill` preserves authored Doom skill flags. For each skill it reports spawnable enemy/item/resource counts, enemy and item breakdowns, ratios, and estimated difficulty for backend single-player mode. If a mapper places enemies only on medium skill, those enemies are not counted as spawned at skills 1, 2, 4, or 5.

### `test_runs`

Stores one autonomous QA session.

Important fields:

- `wad_file_id`, `static_analysis_id`, `map_name`.
- `difficulty_level`, `iwad_used`, `llm_model`, `max_ticks`.
- Lifecycle: `status`, `started_at`, `completed_at`, `duration_seconds`, `outcome`, `error_message`.
- Failure reporting: `failure_category`, `failure_stage`, `failure_summary`, `failure_diagnostics`.
- Final stats: `final_hp`, `final_armor`, `total_kills`, `total_deaths`, `secrets_found`, `total_items_collected`, `total_actions_taken`, `total_llm_calls`.
- Artifacts: `recording_mp4_path`, `report_pdf_path`.

Only one active run is allowed at a time.

### `game_events`

Stores the compact ordered gameplay/event trace.

Each row includes player state, event classification, `agent_decision_id`, `llm_reasoning`, `llm_input_summary`, and `action_taken`.

`action_taken` stores:

- `mcp_tool`: the tool requested by the agent decision.
- `mcp_executed_tool`: the actual MCP tool called.
- `mcp_params`.
- `mcp_service`.
- `mcp_input`.
- compact `mcp_output`, including `action_summary` when provided by MCP.
- warnings such as fallback parameter normalization or missing telemetry frames.

Trace API serializers also expose top-level computed fields:

- `mcp_tool`
- `mcp_executed_tool`
- `mcp_params`
- `mcp_action_summary`
- `mcp_stop_reason`

### `agent_decisions`

Stores the full LLM/MCP audit trail for lockstep control.

Each row includes:

- Run sequence number.
- Tick before and after the selected MCP tool.
- Compact JSON input sent to the LLM.
- Parsed LLM decision JSON and QA-facing `reasoning_summary`.
- MCP tool name, input JSON, output JSON, stop reason, and timing.
- Optional linked `game_event_id`.

Use `/runs/{run_id}/decisions` for the full paginated decision trace. `/runs/{run_id}/trace` remains the backwards-compatible gameplay trace.

### Other Tables

- `agent_position_trail`: downsampled movement samples from decision endpoints and MCP telemetry frames.
- `notable_event_screenshots`: screenshot files for notable moments.
- `defects`: detected findings, including `difficulty_spawn_mismatch` and `pwad_crash`; new rows include a stable `fingerprint`, first/last seen ticks, and occurrence count.
- `test_reports`: structured report fields plus generated PDF path and status.

## Static Analysis

`app/services/analysis_service.py` is responsible for WAD map detection, IWAD requirement detection, start validation helpers, map metadata extraction, spawn summaries, balance metrics, and overview PNG rendering.

Static analysis produces both raw THINGS counts and selected-skill spawn summaries. This is intentional:

- Raw counts tell authors what is present in the map data.
- Spawn summaries tell QA and reports what actually appears at each Doom difficulty.

The project currently preserves authored flags. It does not force enemies or items to spawn at a selected difficulty. If raw enemies/items are hidden by flags for a run difficulty, `DefectService` creates a `difficulty_spawn_mismatch` defect.

Example observed behavior:

- `thelonghallways.wad` / `E1M1` raw enemies: `8`.
- Difficulty 3 spawned enemies: `8`.
- Difficulty 5 spawned enemies: `0`.

## Run Execution

`RunService.create_run()` validates:

- No other run is active.
- WAD exists.
- `map_name` is present in `wad_files.detected_maps`.
- Map has a Player 1 or deathmatch start.
- Static analysis exists or can be generated.
- `max_ticks` is clamped to configured limits.

It then stores a pending run and starts `agent_run_task()`.

New QA runs use lockstep LLM control by default. The backend starts MCP with `async_player=False`, which puts ViZDoom in `PLAYER` mode. In this mode the game does pause while the LLM chooses; gameplay advances only when the backend executes the chosen MCP tool.

The run task:

1. Renders the lockstep QA prompt with selected-difficulty static analysis.
2. Starts MCP `start_game` with `wad`, `scenario_wad`, `map_name`, `difficulty`, `episode_timeout`, and `async_player=False`.
3. Calls `get_state`, plus non-advancing context helpers `get_threat_assessment` and `get_navigation_info`.
4. Creates an `agent_decisions` row and broadcasts `llm_start`.
5. Lets Gemini choose one tactical MCP tool. If Gemini is unavailable, rate-limited, or returns unusable JSON, deterministic fallback chooses visible combat, visible pickup collection, or exploration.
6. Applies backend guards so combat tools only target currently visible monsters and repeated failed targets are avoided.
7. Executes the selected tool, records MCP input/output, stop reason, decision timings, gameplay event, telemetry frames, notable screenshots, and MP4 frames.
8. Broadcasts typed WebSocket messages: `llm_decision`, `mcp_call_start`, `mcp_call_result`, `state`, `frame`, `defect`, and `report_status`.
9. Detects defects and generates a report when the run reaches completion, death, timeout, stuck stop, cancellation, or crash.

Lockstep recovery is explicit:

- Progress is tracked by coarse position cluster, kills, items, secrets, explored cells, and keys.
- Repeated identical progress signatures trigger bounded `retreat` or `explore` recovery actions.
- Repeated low-value `explore` calls that end at `max_tics` are capped at 80 tics and overridden into a QA probe burst: direct `take_action` turn/forward/USE checks plus bounded `retreat`.
- Repeated invisible combat targets are blacklisted for the run.
- Repeated combat actions with shots but no hits/kills escalate recovery.
- After the configured recovery limit or repeated low-value exploration limit, the run stops with outcome `stuck` instead of looping indefinitely.

Combat and pickup behavior is LLM-selected and MCP-executed:

- Normal backend QA runs use `get_state`, `explore`, `move_to`, `aim_and_shoot`, `strafe_and_shoot`, `retreat`, bounded `take_action`, `get_threat_assessment`, and `get_navigation_info`.
- Combat tools only fire at visible targets. If a requested target is not visible, the backend falls back to exploration and records the guard decision.
- Stored LLM/MCP traces contain normalized bounded inputs. For example, model requests for long exploration are clipped before both storage and MCP execution, so the UI sees the same params the tool received.
- Compound tools return telemetry frames so recordings and position trails show gameplay during the bounded tool execution, not only after each LLM decision.

## PWAD Crash Reporting

Load, startup, MCP disconnect, preflight, and runtime initialization failures are user-facing QA outcomes instead of bare backend failures.

Crash-run contract:

- Run detail has `status=failed`, `outcome=pwad_crash`, `failure_category=pwad_crash`, `failure_stage`, `failure_summary`, and `failure_diagnostics`.
- A `pwad_crash` defect is created even when zero gameplay actions were recorded.
- Report JSON and PDF are generated with crash evidence.
- Trace, events, and position endpoints return empty-but-valid payloads when gameplay never initialized.
- Recording returns a structured `404` response with `error=recording_not_available`, `failure_category`, and `failure_stage` when no video can exist.
- Raw technical diagnostics stay in `failure_diagnostics` and report evidence; the product-facing summary is that the PWAD crashed or could not initialize under the configured test environment.

## MCP Server

`mcp-doom` exposes ViZDoom through FastMCP.

Important tools used by the backend:

- `start_game`
- `get_state`
- `get_threat_assessment`
- `get_navigation_info`
- `explore`
- `move_to`
- `aim_and_shoot`
- `strafe_and_shoot`
- `retreat`
- `take_action`
- `stop_game`
- `list_wad_maps`

Async-player tools still supported by MCP, but not used for backend QA runs:

- `get_situation_report` returns screenshot, executor state, objective queue, strategy, recent events, game variables, filtered objects, exploration info, and `executor_progress`.
- `set_objective` queues an objective and supports `replace=true` to clear stale objectives during recovery.
- `set_strategy` adjusts aggression, retreat/collect thresholds, engagement range, collection range, and cover preference.

`executor_progress` includes objective age, recent progress counters, position spread, stuck phase/tics, stuck recovery count, last progress tic, and current target hints.

Compound and async tools return `action_summary` where possible so trace endpoints can expose `mcp_action_summary` and `mcp_stop_reason`.

The MCP server normalizes custom PWAD starts in a temporary runtime copy when a map has duplicate player starts or only deathmatch starts. It does not rewrite enemy or item skill flags.

Combat handling only fires at visible targets. If a requested target is no longer visible, combat tools return an `action_summary.stop_reason` of `target_not_visible`. Object lists are sorted with visible objects first, then by distance, so callers and tests prefer actionable targets instead of wall-blocked monsters.

The backend and MCP server suppress the current FastMCP/Authlib JWT deprecation warning at import time. This is a local compatibility filter for FastMCP 2.14.x and Authlib before Authlib 2.0; it can be removed once FastMCP migrates away from `authlib.jose`.

## Defect Detection

`DefectService` combines static-analysis checks with run telemetry checks.

Current defect sources include:

- `pwad_crash` when map load, startup, preflight, MCP disconnect, or runtime initialization fails.
- `difficulty_spawn_mismatch` when raw THINGS exist but skill or multiplayer flags hide them at the selected difficulty.
- `softlock_navigation` when a run times out or stops after repeated stuck events or negligible end-of-run movement.
- `ammo_starvation`, `health_deficit`, `repeated_death_location`, and `unreachable_secret`.
- Playthrough-observed issue strings captured from decisions.

Observed defects are normalized and de-duplicated. New inserts compute a stable fingerprint and update `occurrence_count` / `last_seen_tick` on repeat instead of creating duplicate rows with slightly different naming. Existing rows are still de-duplicated on read for `/runs/{run_id}/defects` and report generation.

## Reports

`ReportService` gathers run, analysis, event, decision, position, defect, and artifact data.

Reports are generated from Gemini JSON when available, merged with deterministic fallback defaults. If Gemini is unavailable or returns invalid data, the fallback report is used.

Report generation is difficulty-aware:

- Combat coverage uses `spawned_enemy_count` for the selected run difficulty.
- Raw enemy counts are still shown as map data.
- Hidden raw enemies/items are called out as skill-flag issues.
- Resource ratios come from `selected_skill_summary`.

Report voice is normalized before storage and rendering. Obvious blame phrases such as "the agent failed" or "the agent was unable" are rewritten to describe coverage and runtime behavior, for example "the automated playthrough did not reach combat coverage".

Crash reports are first-class QA evidence. They include WAD, map, selected difficulty, failure stage, raw runtime diagnostic, static-analysis availability, endpoint expectations, and why video or trace data may be unavailable by design.

Report generation uses a PostgreSQL advisory lock per run so concurrent `/report`, `/report/pdf`, and background generation requests do not race each other. `/report/status` returns `generating` for recent terminal runs while the background report is still being created.

Report JSON lists are normalized before storage and PDF rendering, so both string lists and object lists render without blank bullets.

PDF rendering uses WeasyPrint with:

- Explicit A4 page margins.
- Repeating table headers.
- Page-break avoidance for important blocks.
- Wrapped table cells.
- Pass/fail badges only for verdict keys.
- Rationale text rendered separately.
- Empty sections skipped.
- De-duplicated defect rows and a display cap so repeated findings cannot expand a PDF into dozens of pages.
- A decision trace table showing LLM/MCP sequence, ticks, tool, stop reason, and QA-facing reasoning summary.

Report API responses exclude `None` report fields.

## HTTP and WebSocket API

Health:

- `GET /health`
- `GET /health/gemini`

WADs and analysis:

- `POST /wads/upload`
- `GET /wads/maps`
- `GET /wads/maps?wad_file_id={id}`
- `GET /wads/{wad_id}`
- `GET /wads/{wad_id}/maps`
- `GET /wads/{wad_id}/analysis`
- `GET /wads/{wad_id}/map-png?map_name=E1M1`

Map payloads include display metadata, analysis status, overview URL, raw counts, and `spawn_summary_by_skill`.

Runs:

- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `DELETE /runs/{run_id}`
- `POST /runs/{run_id}/force-stop`
- `GET /runs/{run_id}/recording`

Run payloads expose `failure_category`, `failure_stage`, `failure_summary`, and `failure_diagnostics` when the result is a crash or runtime startup failure. `recording` streams MP4 when available; for `pwad_crash` before gameplay initialization, it returns a structured no-recording response.

Trace and findings:

- `GET /runs/{run_id}/trace`
- `GET /runs/{run_id}/decisions`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/events?type=normal,map_exit`
- `GET /runs/{run_id}/position-trail`
- `GET /runs/{run_id}/defects`

Reports:

- `GET /runs/{run_id}/report/status`
- `GET /runs/{run_id}/report`
- `GET /runs/{run_id}/report/pdf`

Report JSON omits meaningless null/empty sections while preserving explicit crash evidence and failure diagnostics.

WebSocket:

- `/ws/runs/{run_id}`

Live WebSocket messages are typed. Current message types include `llm_start`, `llm_decision`, `mcp_call_start`, `mcp_call_result`, `state`, `frame`, `defect`, `report_status`, and status updates. State messages include run status, health, armor, ammo, position, event type, QA-facing LLM reasoning, chosen MCP action, and optional notable screenshot.

## Verification Status

The current implementation has been checked with:

- Backend compile check: `PYTHONPATH=. .venv/bin/python -m compileall -q app` from `Backend/`.
- Backend test suite: `PYTHONPATH=. .venv/bin/pytest -q -p no:cacheprovider tests` from `Backend/` (`25 passed`).
- MCP full suite: `PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider tests` from `mcp-doom/` (`98 passed`).
- Local `make db-schema` applied the additive `agent_decisions`, `game_events.agent_decision_id`, and defect fingerprint schema.
- Lockstep smoke run `a58b4675-6f24-421f-81da-dac08e1297eb`: one LLM/MCP decision, one gameplay event, generated report JSON/PDF, and a 640x480 10 FPS MP4 with 61 frames.
- Live endpoint check for run `7365a61c-4b01-4a0f-9b9b-91fb4194c638`: health, run detail, trace, defects, report status, PDF download, recording download, and stuck events.
- Video/report review for run `7365a61c-4b01-4a0f-9b9b-91fb4194c638`: recording is a valid 81.3 second MP4; regenerated PDF is 3 pages, reports outcome `stuck`, and contains 2 de-duplicated defects instead of hundreds of repeated agent-observed rows.
- Endpoint sweep covering health, WADs, maps, analysis, map PNG, run validation, run creation, run detail/list, trace, events, position trail, defects, recording, reports, PDF, cancel/force-stop, and WebSocket connection.

Representative manual product matrix:

| WAD / map | Difficulty | Run | Observed result |
|-----------|------------|-----|-----------------|
| `thelonghallways.wad` / `E1M1` | 1 | `525722e4-06fd-4e39-8464-ceaceeeb5591` | Reproduced the prior circular-motion pattern and verified the new guard: after two low-value `explore` calls, trace switched to `take_action` turn/forward/USE probes and `retreat`, then stopped as `stuck` with report/PDF and a 640x480 10 FPS MP4 with 296 frames. |
| `LOWMEM.wad` / `E1M1` | 1 | `3d954366-ab06-4827-a75a-04d150be1387` | Startup preflight failed as `pwad_crash` with `failure_stage=startup`, zero decisions/actions, report/PDF present, and no recording expected. |
| `thelonghallways.wad` / `E1M1` | 3 | `b38da41d-e657-403c-a7c8-2590e4a438c0` | Lockstep fallback run produced decisions, events, recording, report, and selected-difficulty static context. |
| `thelonghallways.wad` / `E1M1` | 5 | `16af65cd-4744-4636-9842-8f2f87e1af1c` | Selected skill spawned zero enemies and produced `difficulty_spawn_mismatch`. |
| `DRKWRLD1.WAD` / `E1M1` | 3 | `9eca31ea-5502-40ff-a9eb-ce18e01890ba` | PWAD initialized under lockstep mode and produced decisions, trace, video, and report. |
| `LOWMEM.wad` / `E1M1` | 3 | `2817ac53-0bdb-41b4-8ecf-8e76cc6149b7` | Runtime initialization failed as `pwad_crash`; structured report/PDF were generated and no recording was expected. |
| `LOWMEM.wad` / `E1M2` | 3 | `8b0d81d1-0a65-42ef-b88e-cf6c94d98fd6` | Multi-map listing, analysis, lockstep run, trace, recording, JSON report, and PDF were available. |
| `deathmatch.wad` / `MAP01` | 3 | `c77fe3da-8dc6-4324-8c15-6c0a7826b385` | Doom II style map naming and lockstep report payloads were validated. |
| `MYHOME.wad` / `E1M1` | 3 | `a3bb1790-b982-4ccb-8110-4f7ef3d1d9ad` | Short lockstep run produced valid decision trace, JSON report, PDF, and MP4 recording. |
| MCP unavailable startup failure | 3 | `a3ba9534-b0a6-4d6e-804b-c14050aee345` | `status=failed`, `outcome=pwad_crash`, `failure_category=pwad_crash`, zero actions, structured empty trace/position endpoints, `pwad_crash` defect, JSON report, PDF, and structured no-recording response. |

Current operational limitations:

- The backend still allows only one active run at a time.
- Short `max_ticks` test runs often end as `timeout`; that is expected for endpoint verification and not a map-completion verdict.
- `LOWMEM.wad` / `E1M1` currently reproduces the `pwad_crash` path during lockstep startup, while `LOWMEM.wad` / `E1M2` runs normally.
