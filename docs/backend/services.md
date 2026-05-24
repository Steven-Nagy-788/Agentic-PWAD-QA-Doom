# Services Layer

The backend is organized into 20 service modules under `Backend/app/services/`. Each encapsulates a distinct domain concern.

---

## 1. AnalysisService (`analysis_service.py`)

**Purpose:** Static WAD file analysis — parses Doom map geometry, thing counts, difficulty estimation, and renders overhead map overviews.

Key methods:
- `analyze_wad(wad_file)` — Iterates all detected maps, calling `analyze_map` per map
- `analyze_map(wad_file, map_name)` — Builds a `StaticAnalysisResult` with counts, breakdowns, spawn summaries, and overview PNG
- `_enemy_breakdown(counts)` — Categorizes things by enemy type (name, HP, hitscanner flag)
- `_item_breakdown(counts)` — Categorizes by health/armor/ammo pickups
- `_spawn_summary_by_skill(editor)` — Generates per-difficulty spawn summaries (1-5)
- `_difficulty(...)` — Heuristic classification: easy/fair/hard/slaughter
- `_render_overview(wad_id, map_name, editor)` — Draws a 1024×1024 PNG of linedef geometry using Pillow

Helper functions: `detect_map_names`, `map_metadata_for_wad`, `map_bounds_for_wad`, `player_start_counts`, `thing_spawns_at_skill`, `selected_skill_spawn_summary`.

Uses `omg` (OMGifol) WAD parsing and `PIL` for image rendering.

---

## 2. WadService (`wad_service.py`)

**Purpose:** WAD file lifecycle — upload validation, SHA-256 deduplication, storage, retrieval, deletion with cascade.

Key methods:
- `upload(file)` — Reads upload, validates PWAD header, checks SHA-256 dedup, writes to disk, runs static analysis
- `get(wad_id)` — Fetch by ID or 404
- `list(limit, offset)` — Paginated listing
- `delete(wad_id)` — Cascade delete: fails if runs are active, removes overview PNGs, recordings, screenshots, database rows
- `maps(wad_id)` — Returns per-map metadata with analysis
- `map_png_path(wad_id, map_name)` — Returns path to overview PNG
- `schedule_reanalysis(wad_id)` — Spawns background reanalysis task

Validates: PWAD magic header, map presence, player start existence, rejects IWAD and UDMF.

---

## 3. RunService (`run_service.py`)

**Purpose:** Test run creation, cancellation, orchestration — the entry point that launches the agent loop.

Key methods:
- `create_run(data)` — Validates WAD/map/starts, probes MCP health, acquires advisory lock, creates `TestRun(..., status="pending")`, spawns `agent_run_task`
- `cancel(run_id)` — Cancels the asyncio task, force-stops MCP game, finalizes with `finalize_stopped_run`
- `force_stop_external_game()` — Connects to MCP and issues `stop_game`

Also includes the legacy **Director** async player mode: `_initial_strategy_decision`, `_initial_objective_decision`, `_execute_director_tool`, `_apply_director_recovery` — not used in the current lockstep loop.

Helper functions: `finalize_stopped_run`, `fail_orphaned_active_runs`.

---

## 4. RunLoop — `agent_run_task` (`run_loop.py`)

**Purpose:** The main agentic loop — the heart of the system. Runs as an asyncio task spawned by `RunService.create_run`.

The loop:
1. Connects to MCP, calls `start_game` (with `async_player=False`)
2. Enters a lockstep loop: get state → build LLM input → call Gemini → apply guards → execute MCP tool → collect events → check termination → throttle
3. On termination: finalizes recording, detects defects, persists spatial memory/hypotheses/knowledge, generates PDF report

Key helpers:
- `_situation_finished(state)` — Checks episode_finished/timeout/dead/next_map
- `_safe_context_tool(mcp, tool_name)` — Calls threat assessment/navigation info with error tolerance
- `_execute_tool(mcp, decision)` — Routes LLM decision to MCP tool call with parameter normalization
- `_recent_trace(db, run_id)` — Last 5 meaningful reasoning events for LLM context
- `_estimate_total_map_cells(analysis)` — Width×Height / `CELL_SIZE`

---

## 5. RunGuards (`run_guards.py`)

**Purpose:** Lockstep guard functions that intercept and override LLM decisions when quality or progress degrades.

Key functions:
- `_apply_lockstep_recovery(decision, state, navigation_info, lockstep_state)` — Stuck detection via progress signature; triggers QA probe burst or recovery explore
- `_guard_lockstep_decision(decision, state, lockstep_state, navigation_info)` — Blocks repeated action signatures, completed/failed object targets, out-of-ammo combat, invisible targets
- `_combat_target_is_visible(state, object_id)` — Validates monster visibility before combat tools
- `_update_lockstep_after_action(decision, mcp_call, lockstep_state)` — Updates progress score, signature counts, completed/failed object IDs, wasted combat counter
- `_lockstep_progress_metrics(lockstep_state)` — Exposes progress_score, coverage_percent, unvisited_quadrants
- `_lockstep_quality_flags(lockstep_state, recording_metadata)` — Builds quality_status + warnings
- `_lockstep_should_stop_as_stuck`, `_lockstep_stop_outcome` — Terminal stuck detection

Guard thresholds (from `run_constants.py`): `STUCK_RUN_ABORT_THRESHOLD=5`, `WASTED_COMBAT_ABORT_THRESHOLD=3`, `REPEATED_ACTION_ABORT_THRESHOLD=4`, `BLOCKED_DECISION_ABORT_THRESHOLD=6`, `LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD=2`, `LOW_VALUE_EXPLORE_STUCK_LIMIT=6`, `QA_PROBE_BURST_LIMIT=4`.

---

## 6. RunMemory (`run_memory.py`)

**Purpose:** Cross-run memory, spatial memory, hypotheses, and knowledge base — enables the system to learn across multiple runs of the same WAD/map.

Key methods:
- `recommend_behavior_profile(wad_file_id, map_name, ...)` — Switches from "thorough" to "fast" if last 10 thorough runs all ended stuck
- `build_cross_run_memory(...)` — Aggregates prior run outcomes, defect patterns, and warnings into a prompt
- `build_spatial_memory_briefing(...)` — Queries `WadSpatialMemory` for stuck/death/key/secret/starve cell clusters
- `build_hypotheses_briefing(...)` — Active `WadHypothesis` entries (BLOCKED_PATH, KEY_LOCATION, etc.)
- `build_knowledge_briefing(...)` — Versioned `WadKnowledgeBase` document text
- `persist_spatial_memory(run_id, ...)` — Aggregates cell-level event occurrence into `WadSpatialMemory` (upsert)
- `persist_hypotheses(run_id, ...)` — Matches/similarity-deduplicates LLM-generated hypotheses; persists new ones
- `update_knowledge_document(run_id, ...)` — Prepends run summary to knowledge base document (versioned, capped at 10K chars)

---

## 7. RunUtils (`run_utils.py`)

**Purpose:** Utility functions for the run loop — parameter normalization, state compaction, lockstep state management.

Key functions:
- `get_behavior_profile(run)` — Resolves profile name aliases (speedrunner → fast, safety → thorough, exploit_hunter → exploit_focused)
- `_bounded_int`, `_bounded_float`, `_int_like` — Safe numeric coercers with defaults and bounds
- `_json_safe`, `_summary` — JSON-safe serialization helpers
- `_compact_state_for_llm(state)` — Strips screenshot/sectors, limits objects to 30, filters visible keys
- `_lockstep_state_snapshot`, `_structured_memory_snapshot` — Readable snapshots for LLM context
- `_initial_lockstep_state()` — Default lockstep state dict
- `_track_visited_cell(state, lockstep_state)` — Grid-based cell tracking using CELL_SIZE
- `_track_explored_sectors(state, nav_info, lockstep_state)` — Sector ID tracking from multiple sources
- `_merge_hypotheses(lockstep_state, decision)` — Deduplicates LLM hypotheses into state
- `_compute_dynamic_throttle(state, lockstep_state)` — Returns sleep seconds between decisions (combat=3s, low_health=6s, stuck=10s, default=12s)
- `_compute_dynamic_stride(state, lockstep_state)` — Telemetry stride (combat=1, stuck=5, default=3)
- `_normalize_mcp_params(tool, params)` — Validates and bounds MCP tool parameters per tool allowlist
- `_pwad_crash_fields`, `_infrastructure_failure_fields` — Structured failure metadata

---

## 8. RunTelemetry (`run_telemetry.py`)

**Purpose:** Telemetry frame processing — compound MCP tools return intermediate frames; this module extracts, records, and broadcasts them.

Key functions:
- `_pop_telemetry_frames(state)` — Extracts `telemetry_frames` from MCP result state
- `_record_telemetry_frames(run_id, tick, frames, collector, recorder)` — Processes each sample: records position, decodes PNG base64 frames, writes to recording, broadcasts live frames at `live_frame_fps`
- `_write_realtime_frame(recorder, frame, last_at)` — Writes frames with repeat counting for FPS matching
- `_broadcast_state(run, event, decision)` — Sends state payload (health, armor, ammo, position, event_type, reasoning) via WebSocket

---

## 9. RunConstants (`run_constants.py`)

**Purpose:** Central threshold values and tool categorization.

Constants:
- Tool sets: `COMPOUND_TELEMETRY_TOOLS`, `OBJECT_ID_TOOLS`, `COMBAT_TOOLS`, `PICKUP_OBJECT_TYPES`
- Guard thresholds: `STUCK_RUN_ABORT_THRESHOLD=5`, `WASTED_COMBAT_ABORT_THRESHOLD=3`, `LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD=2`, `LOW_VALUE_EXPLORE_STUCK_LIMIT=6`, `QA_PROBE_BURST_LIMIT=4`, `EXPLORE_MAX_TICS_UPPER=80`, `REPEATED_ACTION_ABORT_THRESHOLD=4`, `BLOCKED_DECISION_ABORT_THRESHOLD=6`
- Director constants: `DIRECTOR_POLL_SECONDS=1.25`, `DIRECTOR_STUCK_POLL_THRESHOLD=5`, `DIRECTOR_STUCK_RECOVERY_LIMIT=4`
- Categories: `PWAD_CRASH_CATEGORY="pwad_crash"`, `INFRASTRUCTURE_CATEGORY="infrastructure"`
- Button definitions: `TAKE_ACTION_BUTTONS`, `TAKE_ACTION_BINARY_BUTTONS`
- `CARDINAL_DIRECTION_ANGLES` (east=0, north=90, west=180, south=270)
- `OBJECT_ID_ALIASES` — Alternate param names per tool
- `TOOL_PARAM_ALLOWLIST` — Allowed params per tool
- `RUN_TASKS` — Global `dict[UUID, asyncio.Task]` tracking active run tasks

---

## 10. GeminiService (`gemini_service.py`)

**Purpose:** Google Gemini LLM wrapper with retry logic, rate limiting, JSON parsing, and deterministic fallback.

Key methods:
- `decide(system_prompt, llm_input, screenshot_png)` — Main lockstep decision entry point; 3 attempts with retry
- `decide_director(system_prompt, llm_input)` — Director mode decision entry point
- `probe_model()` — Smoke test: returns raw model response
- `parse_decision(text)` — Extracts JSON from markdown blocks/braces, validates tool against `ALLOWED_TOOLS`
- `parse_director_decision(text)` — Same for `DIRECTOR_TOOLS`
- `_fallback_decision(llm_input, reason)` — Deterministic fallback: nearest visible monster → combat, nearest visible pickup → move_to, out-of-ammo → weapon switch, unexplored direction → explore, unvisited quadrants → turn, else retreat
- `_fallback_director_decision(llm_input, reason)` — Director fallback: stuck recovery → explore, low health → retreat, low ammo → collect, monsters → set_strategy, idle → explore

Rate limiting: Local sliding-window throttle via `_throttle_local_rate` (calls/minute), concurrency semaphore (`gemini_max_concurrency`).

Token tracking: `get_last_token_usage()`, `estimate_llm_cost_usd(...)`.

---

## 11. CollectorService (`collector_service.py`)

**Purpose:** Per-tick event collection, state normalization, and defect creation during runs.

Key methods:
- `collect(run_id, tick, state, llm_input, decision, mcp_call)` — Normalizes game variables, detects event type, creates `GameEvent`, creates position trail entry, processes LLM-reported issues as defects
- `collect_position(run_id, tick_number, state)` — Lightweight position-only event (used by telemetry frames)
- `attach_screenshot(run_id, event, screenshot_path)` — Links notable event screenshot
- `detect_event(variables)` — Returns event type: map_exit, death, kill, secret_found, item_pickup, damage_taken, stuck, normal

Event detection uses delta comparison: `STUCK_DECISION_THRESHOLD=5` consecutive ticks without position change.

LLM-reported issues: `normalize_observed_issue(issue)` parses `[category] description` or dict format into `agent_observed_{category}` defect types. Duplicate suppression by type + tick proximity (±500 ticks, within 100 units).

---

## 12. DefectService (`defect_service.py`)

**Purpose:** Post-run defect detection — 7 detector algorithms (see [defect-detection.md](./defect-detection.md)).

Key methods:
- `detect_for_run(run)` — Orchestrates all 7 detectors in sequence, then links screenshots
- `_pwad_crash(run)` — Detects startup failure
- `_difficulty_spawn_mismatch(run, analysis)` — Content hidden by difficulty flags
- `_repeated_deaths(run_id, events)` — Spawn camping / unfair death traps
- `_ammo_starvation(run_id, events)` — Zero ammo for 61+ consecutive ticks
- `_health_deficit(run_id, events)` — HP < 10 for 31+ consecutive ticks
- `_softlock(run, events)` — Stuck/timeout with navigation failure
- `_unreachable_secrets(run, events, analysis)` — Secret sectors exist but none found at ≥60% coverage
- `_link_screenshots_to_defects(run_id)` — Attaches screenshot to defects by tick number matching

Helper: `_streak_episodes(events, predicate, minimum_length)` — Generic streak detector used by ammo/health detectors.

---

## 13. PatternService (`pattern_service.py`)

**Purpose:** Cross-run defect pattern analysis — groups defects by fingerprint across runs for the same WAD.

Key methods:
- `get_patterns(wad_id)` — Returns defect patterns (fingerprint groups with ≥2 occurrences), spatial clusters (128-unit cells), and difficulty coverage summary

Pattern deduplication key: `fingerprint` field, falling back to `defect_type:title`.

---

## 14. ReportService (`report_service.py`)

**Purpose:** PDF report generation using Jinja2 templates + WeasyPrint rendering.

Key methods:
- `generate(run_id)` — Acquires advisory lock, fetches run/analysis/defects/events/positions/decisions, calls `_call_gemini_or_fallback` for structured report JSON, renders PDF via WeasyPrint
- `_call_gemini_or_fallback(payload)` — Optionally uses Gemini to generate structured report JSON; falls back to `_fallback_report` which builds deterministic report from run metrics
- `_render_pdf(run_id, report_json, payload)` — Jinja2 template rendering → WeasyPrint HTML → PDF

Report sections (IEEE 829-inspired): test environment, hardware/software spec, objectives, pass/fail summary, risk areas, defect patterns, coverage evaluation, limitations.

Voice sanitization: `_sanitize_report_voice` replaces "agent" → "automated playthrough".

---

## 15. RecordingService (`recording_service.py`)

**Purpose:** Gameplay video recording pipeline — OpenCV capture + ffmpeg H.264 transcoding.

Key methods:
- `write_frame(frame, game_tick)` — Writes a frame to the raw OpenCV `mp4v` writer with game-tick-based frame skipping
- `save_screenshot(frame, event_id)` — Saves a standalone PNG screenshot
- `finalize()` — Pads minimum frames if needed, releases writer, triggers `_transcode_h264`
- `_transcode_h264()` — Spawns ffmpeg to transcode raw `mp4v` → `libx264 yuv420p +faststart`
- `validate(path, outcome)` — Returns metadata with quality checks: frame count vs expected, unique frame ratio, resolution, transcode errors
- `metadata(path, outcome)` — Returns duration, FPS, game tick range, quality status

Helper functions: `png_bytes_to_frame` (CV2 decode), `jpeg_b64` (JPEG encode for WebSocket broadcast).

---

## 16. McpClientService (`mcp_client_service.py`)

**Purpose:** MCP protocol client for controlling Doom through mcp-doom.

Key methods:
- `start_game(wad, scenario_wad, map_name, difficulty, episode_timeout, async_player, ticrate)` — Starts a ViZDoom episode with retry
- `get_state()` — Returns parsed game state + screenshot PNG bytes
- `get_situation_report()` — Returns executor situation report
- `set_objective(...)` — Sets async player objective
- `set_strategy(...)` — Sets async player strategy parameters
- `stop_game()` — Stops the episode
- `call_tool(name, params)` — Generic MCP tool call with timeout

Connection: SSE-based FastMCP `Client` with exponential backoff retry (1s, 2s, 4s).

`normalize_mcp_state(result)` — Recursively extracts state dict and screenshot PNG from MCP `TextContent` / `ImageContent` responses.

---

## 17. WebSocketService (`websocket_service.py`)

**Purpose:** Real-time event broadcasting to frontend via WebSocket.

Key methods:
- `connect(run_id, websocket)` — Accepts connection, registers per-run connection set
- `disconnect(run_id, websocket)` — Removes connection
- `broadcast(run_id, payload)` — JSON-serializes and sends to all connections for a run (2s timeout per socket)
- `cleanup_run(run_id)` — Closes all connections for a completed run
- `handle_pong(websocket)` — Updates liveness timestamp

Background ping loop: pings every 30s, disconnects sockets unresponsive >60s.

Singleton instance: `websocket_service = WebSocketService()`.

---

## 18. SmokeService (`smoke_service.py`)

**Purpose:** System health smoke tests — validates MCP connectivity, game startup, state retrieval, and Gemini API.

Key methods:
- `run_smoke()` — Runs staged checks: MCP SSE → Gemini key → Start game (Freedoom MAP01) → Get state → Gemini probe → Cleanup

Each stage returns `{"label", "pass", "duration_ms", "detail" | "error"}`.

---

## 19. RunCompareService (`run_compare_service.py`)

**Purpose:** Side-by-side run comparison — compares two runs of the same WAD/map.

Key methods:
- `compare(run_a_id, run_b_id)` — Validates same WAD/map, compares defects (present in both / resolved / new), kills delta, coverage delta, resource delta (final HP, final ammo)

Defect comparison uses fingerprint-based set diff.

---

## 20. PromptService (`prompt_service.py`)

**Purpose:** System prompt rendering with template variable substitution.

Key functions:
- `render_agent_prompt(wad, analysis, run, cross_run_memory, spatial_briefing, knowledge_document)` — Reads `agent_system_prompt.md` template and replaces `{variable}` placeholders with sanitized values
- `report_prompt_path()` — Returns path to `report_generation_prompt.md`

Template variables include: map metadata, difficulty, enemy/item counts, key requirements, health/ammo ratios, cross-run memory, spatial briefing, knowledge document.
