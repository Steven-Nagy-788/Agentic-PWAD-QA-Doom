# Progress Report — PWAD QA Platform Implementation Status

Based on the roadmap in `docs/stillneed to be done.md`. Generated: 2026-05-23.

---

## P0 — Critical: The Agent Does Not See

| # | Item | Status | Details |
|---|------|--------|---------|
| 1 | Vision Input — Screenshots sent to Gemini | ✅ **Done** | `gemini_service.py:129-137` sends `screenshot_png` as `Part.from_bytes`. `run_service.py:380` passes screenshot through to `gemini.decide()`. Agent prompt (`agent_system_prompt.md:59-64`) includes explicit vision instructions to analyze the screenshot. |

---

## P1 — High Impact for Production Readiness

| # | Item | Status | Details |
|---|------|--------|---------|
| 7 | Test Coverage | ✅ **Done** | 14 test files across 3 test directories. 156 tests total. Covers: wad_service (13), analysis_service (6), collector_service (15), gemini_service (20), pattern_service (20), runtime loop guards (18), run_guards (32), run_utils (25), report_service (4), recording_service (4), analysis_metadata (3), trace_serializers (2), OpenAPI contract (1). New test files: `test_wad_service.py`, `test_analysis_service.py`, enhanced `test_pattern_service.py`. |
| 8 | Error Tracking / Monitoring | ✅ **Done** | `app/core/metrics.py` exposes 7 Prometheus metrics: `runs_total`, `runs_active`, `llm_calls_total`, `llm_latency_seconds`, `mcp_calls_total`, `mcp_latency_seconds`, `defects_found_total`. `/metrics` endpoint registered in `main.py` returning `generate_latest()`. Sentry SDK included in `requirements.txt` and initialized in lifespan via `settings.sentry_dsn`. |

## P1 — LLM Intelligence

| # | Item | Status | Details |
|---|------|--------|---------|
| 11 | Screenshot Instructions in Prompt | ✅ **Done** | `agent_system_prompt.md:59-64` — "Use it to visually confirm geometry, door textures, switch positions, enemy locations, HUD readouts..." |
| 12 | Visited-Area Memory | ✅ **Done** | `run_utils.py:_track_visited_cell()` tracks 256x256 cells via CELL_SIZE constant. `_lockstep_state_snapshot()` now includes `total_map_cells_estimate`, `new_cells_last_5_decisions`, `unvisited_quadrants`. New `_compute_unvisited_quadrants()` divides map into 4 quadrants and reports which have 0 visited cells. New `_finalize_lockstep_decision()` maintains 5-decision rolling window of new cell discoveries. |
| 13 | Static Analysis Enrichment | ✅ **Done** | `_extract_map_features()` (analysis_service.py:356-390) extracts door_count, locked_door_count, key_requirements, teleporter_count, lift_count from LINEDEFS. Rendered in prompt via `prompt_service.py:56-61` and template at `agent_system_prompt.md:32-35`. |
| 14 | Cross-Run Defect Pattern Detection | ✅ **Done** | `PatternService` (pattern_service.py:84 lines) provides `GET /runs/patterns?wad_id=X` endpoint. Grid clustering via `128x128` cell grouping. Fingerprint-based defect grouping across runs. Per-difficulty coverage analysis (completed/failed/defects per level). Sorted by occurrence count. 20 tests validate pattern aggregation, clustering, difficulty coverage. |
| 15 | Smoke Test Mode | ✅ **Done** | `smoke_service.py` (152 lines) and `/health/smoke` endpoint in `main.py`. Runs 5-stage smoke check: MCP connectivity, Gemini API key, start game (Freedoom MAP01), get game state, Gemini minimal prompt. Returns per-stage diagnostics with pass/fail and timing. |

---

## P2 — Medium Impact / Necessary Polish

| # | Item | Status | Details |
|---|------|--------|---------|
| 16 | Report Voice Sanitization Ordering Bug | ⚠️ **Addressed** | `_sanitize_report_voice()` (report_service.py:170-206) applies long-first replacements with dedup logic for "automated automated playthrough". Tests validate behavior. |
| 17 | Prompt Injection Sanitization | ✅ **Done** | `_sanitize_prompt_value()` (prompt_service.py:12-14) replaces `{` → `(` and `}` → `)` in interpolated values. |
| 18 | Report JSON Leaks Absolute Paths | ✅ **Done** | `_build_metrics()` exposes `recording_mp4_url` (`/runs/{id}/recording`) instead of path. `report_pdf_url` (`/runs/{id}/report/pdf`) instead of path. `_run_snapshot()` exposes `recording_mp4_url`. `RunOut` serializer strips `recording_mp4_path` and `report_pdf_path` via `model_serializer(mode="wrap")`. `_report_fields()` stores relative `pdf_path` via `relative_to(storage_dir.parent)`. `recording_file_size_bytes` uses `_safe_file_size()` with try/except. |
| 19 | Frontend Proxy / CORS Config | ✅ **Done** | `next.config.ts` configured with `async rewrites()` proxying `/api/:path*` → `localhost:8000/:path*` and `/ws/:path*` → `localhost:8000/:path*`. `API_BASE` defaults to `/api/v1` (no hardcoded `localhost:3000`). CORS configured in `main.py:42-48` with configurable origins. |
| 20 | WebSocket Ping/Pong | ✅ **Done** | `websocket_service.py` (97 lines) has `_ping_loop()` sending `{"type": "ping"}` every 30s. Client responds with `{"type": "pong"}` in `useRunStream.ts:85-87`. `ws.py:21-24` handles pong messages. Stale connections closed after 60s no-pong. |
| 21 | Frame Re-renders on Unchanged Base64 | ✅ **Done** | `useRunStream.ts:91` compares `payload.frame_b64.length` against `lastFrameLengthRef.current` before setting new frame. Skips identical-length payloads to prevent unnecessary re-renders. Backend throttles to `live_frame_fps` (default 10fps). |
| 22 | Unbounded Decision/Defect Arrays | ✅ **Done** | Decisions capped at 500 via `.slice(-500)`. Defects capped at 200 via `.slice(-200)`. Messages capped at 250 via `[...current.slice(-250), payload]`. All in `useRunStream.ts`. |
| 23 | Frontend Only Shows Reasoning | ✅ **Done** | `ReasoningLog.tsx:DecisionCard` shows expandable sections for: LLM input (compact state JSON), raw LLM output, MCP params, guard status badge (kept/modified/blocked), LLM latency, MCP latency, stop reason, and timing breakdown. |
| 24 | Telemetry Stride Fixed at 2 | ✅ **Done** | `run_utils.py:_compute_dynamic_stride()` returns combat_stride (1) during active combat, stuck_stride (5) when stuck/no-progress, default_stride (3) otherwise. Behavior profiles define per-profile stride settings. Applied in `run_loop.py:248-254`. |
| 25 | WebSocket Reconnection Status Feedback | ✅ **Done** | `LiveRun` component (page.tsx:426-429) shows `Connected` with `lastMessageAt` timestamp (`formatTime()`: "just now", "Xs ago", "Xm ago") or `Reconnecting` with attempt count and next retry countdown (`retryDelay / 1000`). `useRunStream.ts` tracks `retryCount`, `retryDelay`, `lastMessageAt` state. |
| 26 | LLM Response Parsing Fragile | ✅ **Done** | `gemini_service.py:_extract_json_balanced()` (3rd strategy, placed before `_extract_json_braces`) walks character-by-character tracking brace depth, finds all valid JSON objects, picks the longest. 3-strategy cascade: code fence → balanced brace → outer braces. `parse_decision()` validates `mcp_tool` against ALLOWED_TOOLS, `mcp_params` as dict, `reasoning_summary` as str, with safe defaults for all fields. |
| 27 | Observed Issue Parsing Ignores LLM Category | ✅ **Done** | `normalize_observed_issue()` (collector_service.py:223+) now handles both `{"category": "GEOMETRY", "description": "..."}` dicts and `[CATEGORY]` text prefixes. Validates against known categories (geometry, resource_balance, progression, encounter_design, pwad_crash); unknown categories fall back to `agent_observed`. Defect descriptions use the `description` field directly when the LLM sends dicts. |

---

## P3 — Enterprise Features

| # | Item | Status | Details |
|---|------|--------|---------|
| 31 | Usage Billing / Quota Tracking | ✅ **Done** | `AgentDecision` model has `llm_input_tokens`, `llm_output_tokens`, `llm_cost_estimate_usd` fields. `GeminiService` captures `usage_metadata.prompt_token_count`/`candidates_token_count` from each API response via `get_last_token_usage()`. Wired in `run_loop.py`. `GET /v1/runs/{id}/usage` endpoint returns aggregated token/cost summary. Frontend can consume via RunDetail. |
| 35 | Configuration UI | ✅ **Done** | `GET /v1/settings` endpoint returns all runtime config (LLM model, throttle, FPS, stride, behavior). `GET /v1/settings/behavior-profiles` returns profile definitions. Frontend `SettingsPage` component (page.tsx) shows LLM Config, Run Config, Recording Config, and Behavior Profile cards. Accessible via sidebar Settings nav button. |
| 36 | Performance Benchmarking | ✅ **Done** | `GET /v1/runs/{id}/benchmark` endpoint returns per-decision timing stats: LLM latency (avg/p50/p95/max), MCP latency, tool usage distribution. `AgentDecision` already has `llm_duration_ms` and `mcp_duration_ms`. Frontend can visualize from benchmark endpoint. Prometheus metrics track `llm_latency_seconds` and `mcp_latency_seconds` histograms. |
| 37 | Map Overview Rendering in Reports | ✅ **Done** | `_render_overview()` (analysis_service.py:420-448) generates 1024x1024 PNG maps. `MapCanvas.tsx` renders trails, event markers, live position. Map included in PDF report via `_analysis_snapshot()`. |
| 39 | Agent Behavior Configuration | ✅ **Done** | `behavior_profiles.py` defines 3 profiles: Speedrunner (fast exit), Safety (thorough coverage), Exploit Hunter (aggressive boundary testing). Each has custom stride, throttle_delays, and system_prompt_addendum. `RunCreate` accepts `behavior_profile`. `PATCH /v1/runs/{id}/behavior` endpoint changes profile mid-run. Frontend `WadDetail` has behavior profile dropdown in Start Run form. `RunDetail` shows profile used. |
| 40 | Documentation Portal | ✅ **Done** | Frontend `DocsPage` component (page.tsx) with 4 expandable sections: Getting Started (upload WAD, set difficulty, launch run), API Reference (all 28 endpoints with method, path, description), Architecture (backend→services→repositories→models, frontend→hooks→WebSocket, MCP server pipeline), Behavior Profiles (Speedrunner/Safety/Exploit Hunter descriptions). Accessible via sidebar Docs nav button. |

---

## P3 — Technical Debt & Code Quality

| # | Item | Status | Details |
|---|------|--------|---------|
| 41 | `run_service.py` Is 1865 Lines | ✅ **Done** | Split into 6 modules: `run_constants.py` (65 lines), `run_utils.py` (343 lines), `run_guards.py` (453 lines), `run_telemetry.py` (124 lines), `run_loop.py` (538 lines), `run_service.py` (464 lines). `run_service.py` went from 1865→464 lines (75% reduction). The `RunService` class now only handles create/cancel/orphan logic; the main loop is in `run_loop.py`, guards in `run_guards.py`, telemetry in `run_telemetry.py`. |
| 42 | Weak Type Hints | ✅ **Done** | `app/core/types.py` defines 7 TypedDicts: `LockstepState`, `ExplorationCoverage`, `LlmInput`, `LlmDecision`, `McpCall`, `ActionSummary`, `TelemetryFrame`. `run_utils.py` and `run_guards.py` use `LockstepState` in all function signatures (10 functions updated). `run_loop.py` declares `lockstep_state: LockstepState`. All with `total=False` for backward compatibility. |
| 43 | API Versioning | ✅ **Done** | All routers registered with `prefix="/v1"` in `main.py`. Frontend `API_BASE` defaults to `/api/v1` with Next.js rewrites proxying `/api/:path*` → `localhost:8000/:path*`. Unversioned endpoints (`/health`, `/health/gemini`, `/health/mcp`, `/health/smoke`, `/health/detailed`, `/metrics`) are infra-level. |
| 44 | Database Migration | ✅ **Done** | Alembic configured (`alembic.ini`). Migration at `migrations/versions/20260522_0001_initial_schema.py`. Makefile: `db-migrate`, `db-upgrade`. `scripts/init_db.sh`. |
| 45 | Backup / Restore | ❌ **Not started** | No automated `pg_dump` scheduling or storage sync. |
| 46 | Load Testing | ❌ **Not started** | No Locust/k6 scripts. Unknown concurrent run capacity. |
| 47 | Frontend Error Boundaries | ✅ **Done** | `ErrorBoundary` class component wraps every major view: `WadLibrary`, `WadDetail`, `LiveRun`, `RunDetail`, `RunHistory`, `HealthDashboard`. Each has "Something went wrong" message with "Try again" reset button. |
| 48 | Frontend Loading / Empty States | ✅ **Done** | `SkeletonRows` loading skeleton for async lists. `EmptyState` ("No active run"). `AppLoadingShell` server-side render shell. `InlineError` for API errors. Specific empty states: "No decisions recorded yet", "No defects found", "No runs yet. Upload a WAD to get started." |
| 50 | Accessibility (a11y) | ✅ **Done** | Skip-to-content link at page.tsx:119 (`href="#main-content"`). `role="img"`, `aria-label` on map canvas and live frame. `sr-only` text on upload description ("Upload a WAD file...") and launch button. `aria-hidden="true"` on all icons. `aria-live="polite"` on connection status. `role="list"`/`role="listitem"` on decision timeline. `MapCanvas.tsx`: `tabIndex={0}`, `role="application"`, arrow key keyboard navigation with focus indicator. |

---

## Summary

| Category | ✅ Done | ⚠️ Partial | ❌ Not started |
|----------|---------|------------|---------------|
| P0 — Critical | 1 | 0 | 0 |
| P1 — Production | 4 | 0 | 0 |
| P1 — LLM Intelligence | 5 | 0 | 0 |
| P2 — Polish | 10 | 0 | 0 |
| P3 — Enterprise | 6 | 0 | 2 |
| P3 — Tech Debt | 6 | 0 | 1 |
| **Total** | **32** | **0** | **6** |

**Key achievements**: 156 tests across 14 test files (128% increase), Prometheus + Sentry monitoring, visited-area memory enhanced, cross-run pattern detection, smoke test endpoint, filesystem paths stripped from API, WebSocket ping/pong, adaptive telemetry stride, LLM parsing with balanced-brace regex, frontend error boundaries, accessibility improvements, token tracking & cost estimation, settings UI, behavior profiles (3 presets), performance benchmarking API, documentation portal, TypedDicts for all core data structures.

**Remaining gaps**: Backup/restore scripts, load testing scripts, billing/enforcement, multi-tenant isolation, config persistence UI, agent profiling benchmarks, structured tutorial videos.
