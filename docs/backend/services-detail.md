# Backend Services — Detailed Reference

All services in `Backend/app/services/`. Organized by runtime phase.

## Active Runtime

### `run_loop.py` (~1400 lines) — Core Lockstep Loop

The heart of the system. `agent_run_task()` orchestrates a complete QA run:

1. **Initialization**: Load WAD + analysis from DB, start MCP game session, initialize recorder
2. **Lockstep iteration** (repeated until terminal):
   - Call MCP `get_state` → extract game variables, objects, depth, sectors
   - Update QA cell tracking in NavigationMemory
   - Project canonical payload: compact state + static analysis + memory + coverage
   - Build LLM input → request Gemini `decide()` 
   - Persist AgentDecision with source=llm
   - Validate parameters via guard system
   - Execute MCP tool (take_action, aim_and_shoot, move_to, explore, etc.)
   - Persist GameEvent with outcome
   - Broadcast via WebSocket (frame, state, decision, defect)
   - Detect defects live (agent-observed issues)
   - Check termination: tick exhaustion, no-progress stall, cancellation, player death
3. **Completion**: Finalize recording metadata, run defect detection, generate report, update test_run status/outcome

Key helpers: `execute_tool()` routes to appropriate MCP tool with parameter normalization, `_update_lockstep_after_action()` tracks progress.

### `run_tracking.py` (~200 lines) — Lockstep State & Guard Logic

- `_update_lockstep_after_action()`: Updates position history, progress metrics, quality flags
- `_lockstep_should_stop_as_stuck()`: Detects no-progress (8+ consecutive decisions with <1 cell of new exploration)
- `_lockstep_stop_outcome()`: Maps stop reasons to outcomes (player_died, pwad_crash, etc.)
- `_lockstep_progress_metrics()`: Computes coverage %, kill rate, survival time
- `_lockstep_quality_flags()`: Assesses agent quality (combat engagement, exploration, survival)
- Guard logic: Stuck detection, diversity monitoring (repeated same actions)

### `run_utils.py` (~500 lines) — Helpers

- `_compact_state_for_llm()`: Trims objects to ~20 nearest, removes depth, filters non-monster
- `_compact_context_for_llm()`: Compacts game variables, removes redundant fields
- `_build_llm_input()`: Assembles the full prompt payload
- `_build_same_run_memory()`: Creates action ledger from recent decisions
- `_compute_dynamic_throttle()`: Adjusts delay based on combat/low-health/stuck state
- `_compute_unvisited_quadrants()`: Coverage analysis for exploration hints
- `_normalize_take_action_params()`: Clamps delta values, removes unknown buttons
- `_track_visited_cell()`: 256-unit grid cell tracking
- `_sector_ids_from_state()`: Extracts sector IDs from game state
- `_merge_hypotheses()`: Cross-run hypothesis dedup
- Behavior profile selection: `get_behavior_profile()` returns profile config

### `gemini_service.py` (~350 lines) — LLM Integration

- `GeminiService.decide()`: Calls Gemini API via `google-genai` library
- Rate limiting: Semaphore (configurable concurrency) + per-minute token bucket
- Retry: Exponential backoff (3 attempts) on transient errors
- `parse_decision()`: Extracts structured decision from LLM JSON response
- Multi-strategy JSON parsing: Direct parse → code block extraction → brace matching
- `_fallback_decision()`: Deterministic fallback when Gemini unavailable (returns `explore` action)
- Cost estimation: Uses per-model token pricing constants
- `extract_json_balanced()`: Handles nested braces, markdown code blocks, trailing text

### `mcp_client_service.py` (~250 lines) — MCP Client

- `McpDoomClient`: SSE connection via `fastmcp` library
- `start_game()`: Calls MCP `start_game` tool with WAD + map + difficulty
- `get_state()`: Fetches current game state with screenshot
- `call_tool()`: Generic MCP tool call with timeout (30s default) and retry (3 attempts)
- State normalization: Fixes ViZDoom variable casing (e.g., `SELECTED_WEAPON` → `SELECTED_WEAPON`)
- Tool parameter normalization: Validates and clamps inputs
- `McpStartupError`: Raised when PWAD crashes during start_game (detected via missing player start)

### `run_service.py` (~200 lines) — Run CRUD

- `create_run()`: Validates WAD exists, checks no active run for same WAD, acquires advisory lock, schedules `agent_run_task`
- `cancel_run()`: Sets cancellation flag, task checks flag on each iteration
- `delete_run()`: Cascading cleanup (recording, screenshots, report files, DB records)
- `_schedule_run_task()`: Creates asyncio task, registers in process-local `RUN_TASKS` dict

## Evidence & Output

### `recording_service.py` (~250 lines) — Video Recording

- `RecordingService`: OpenCV-based frame capture
- Frame accumulation: Collects frames during run
- H.264 transcoding: Via ffmpeg subprocess (with timeout recovery)
- Screen capture: X11/Windows screen capture for headless display
- Metadata validation: Frame count, unique frames, FPS, gameplay seconds
- Crash handling: `expected_missing` mode for PWAD crash runs
- Telemetry sampling: Configurable stride for frame capture

### `report_service.py` (~900 lines) — PDF Report Generation

- `ReportService.generate()`: Full report pipeline
- Report LLM input: Builds structured input from run data, defects, events, trace
- Gemini call: Via `_call_gemini_or_fallback()` with 60s timeout
- Multi-strategy JSON parsing: `_parse_report_json()` handles malformed LLM output
- Deterministic fallback: `_deterministic_report()` when Gemini unavailable
- PWAD crash report: `_pwad_crash_report()` for failed startups
- PDF rendering: Jinja2 template (`report.html.j2`) → WeasyPrint HTML→PDF
- Evidence model: `_build_evidence_model()` classifies findings by confidence
- Voice sanitization: `_sanitize_report_voice()` removes agent-blame phrases
- Merge defaults: `_merge_report_defaults()` merges LLM narrative with computed metrics

### `collector_service.py` (~120 lines) — Defect Collection

- `collect_observed_issues()`: Processes LLM `observed_issues` field from decisions
- `normalize_observed_issue()`: Handles string/dict/None/edge case formats
- `normalize_variables()`: Computes `usable_attack_ammo` from weapon state

### `environment_service.py` (~50 lines) — Environment Metadata

- Collects: Python version, OS, installed packages, hardware info
- Stored in `test_run.environment_metadata`

### `smoke_service.py` (~100 lines) — Health Check

- `SmokeService.check()`: Verifies MCP connectivity, Gemini API key, WAD loading, state reading, DB query
- Returns detailed per-component status
- Guarded during active runs (prevents interference)

### `websocket_service.py` (~200 lines) — Live Streaming

- `WebSocketService.connect()`: Registers client for a run
- `broadcast()`: Sends typed messages (frame, state, llm_decision, mcp_call, progress, defect)
- Message cache: Last N messages per run for replay on client reconnect
- Ping/keepalive: Periodic heartbeat
- Cleanup: Removes clients on disconnect or run end

## Reviewer Analytics

### `defect_service.py` (~500 lines) — Defect Detection

Post-run pipeline with 7 detectors:
1. **PWAD Crash**: Run that never started (severity 1, priority 1)
2. **Difficulty Spawn Mismatch**: Empty spawn at chosen difficulty (severity 2-3)
3. **Repeated Death Locations**: ≥2 deaths at same position (severity 2)
4. **Ammo Starvation**: ≥61 consecutive ticks with 0 usable ammo (severity 2)
5. **Health Deficit**: ≥31 consecutive ticks with HP < 10 (severity 2)
6. **Softlock**: stuck/timeout outcome with stuck events or negligible end movement (severity 2)
7. **Unreachable Secrets**: Requires 60%+ coverage, secrets not found (severity 3)

Each detector creates `Defect` records with fingerprint for dedup. Screenshot linking via `NotableEventScreenshot`.

### `run_memory.py` (~150 lines) — Cross-Run Memory

- `WadMemoryService`: Records spatial events and hypotheses across runs
- `record_event()`: Records cell-level events (death, kill, item pickup)
- `record_hypothesis()`: Stores agent observations with confidence
- `query_memory()`: Returns relevant memory for a (wad, map)
- `_infer_tag()`: Auto-categorizes hypotheses (texture, visual_glitch, gameplay, softlock, etc.)
- `_is_persistable_hypothesis()`: Confidence threshold filtering

### `pattern_service.py` (~150 lines) — Cross-Run Patterns

- `PatternService.get_patterns()`: Groups defects by fingerprint across runs
- Cell clustering: 256-unit grid for position-based grouping
- Difficulty coverage: Tracks which skill levels have been tested
- Outcome tracking: Run outcomes per map

### `analysis_service.py` (~300 lines) — WAD Static Analysis

- `analyze_wad()`: Orchestrates per-map analysis
- `analyze_map()`: Parses WAD via `omgifol`, extracts things/linedefs/sectors/vertices
- Spawn summaries: Per-skill (1-5) respecting Doom skill flags
- Difficulty estimation: Based on monster composition and density
- Health/ammo ratios: Pickup vs monster HP balancing
- Map features: Door/lift/teleporter/key detection from sector/linedef analysis
- Overview PNG: Renders minimap overlay

### `wad_service.py` (~150 lines) — WAD File Management

- Upload: SHA-256 validation, size limit, storage, async analysis
- Delete: Cascading cleanup of analysis data, runs, recordings
- Map listing: Reads WAD directory for map markers
- Map PNG serving: Returns overview PNG for map selector in frontend
- Reanalysis: Schedules reanalysis task

### `run_compare_service.py` (~80 lines) — Cross-Run Comparison

- `compare_runs()`: Compares two runs (defect overlap, metrics)
- `compare_wads()`: Aggregates across all runs for a WAD
- Position heat maps: Density-based trail comparison
- Difficulty coverage: Which skill levels have been tested
