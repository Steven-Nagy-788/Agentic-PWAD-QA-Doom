# Historical: Still Need to Be Done - Product Roadmap to Enterprise-Grade PWAD QA

This document outlines every gap, enhancement, and missing feature between the current POC and a production-ready QA platform that companies like Epic Games would trust, adopt, and love.

---

## P0 — Critical: The Agent Does Not See

### 1. Vision Input — Screenshots Are Captured but Never Sent to Gemini

**Status**: Partially wired. `gemini_service.py:129-137` *does* send the screenshot (`screenshot_png` bytes as a `Part.from_bytes`) in the multimodal path. However `run_service.py:380` calls `gemini.decide(prompt, llm_input, screenshot_png=screenshot_png)` — but the screenshot PNG from `get_state()` is passed through. **This actually works now** (verified). But the fallback path (line 142-152 synchronous `generate()` call) also has the screenshot code. So this is DONE for Gemini.

**What's missing**: The agent prompt (`prompt_service.py`) does not tell the LLM to *look at* the screenshot. The system prompt only includes structured state JSON. Without instructions to interpret the image, the LLM may ignore it or use it inconsistently.

**Fix**: Update `agent_system_prompt.md` and `render_agent_prompt()` to include explicit instructions:
- "You receive a screenshot of the current game frame. Use it to identify enemies, geometry, doors, switches, keys, pickups, and your position."
- "Pay attention to the HUD area (bottom of screen) for health, armor, ammo, and weapon."
- "Check for visible exit signs, key-locked doors (colored trim), and switch textures."

---

## P1 — High Impact for Production Readiness



### 7. Test Coverage is Minimal

**Current state**: 6 test files with ~765 lines total. Tests cover specific behaviors (guards, serializers, recording) but NOT the core run loop, WAD analysis, or critical failure paths.

**Uncovered areas**:
- `run_service.py:agent_run_task()` (1865 lines, 0 tests)
- `wad_service.py:upload()` (219 lines, 0 tests)
- `analysis_service.py:analyze_map()` (454 lines, 0 tests)
- `gemini_service.py:decide()` (404 lines, tested via guard tests only)
- `collector_service.py:collect()` (238 lines, 0 tests)
- All router endpoints except schemas
- Report generation with mock data
- Frontend components (0 component tests)

**Target**: >80% backend coverage. >50% frontend coverage (critical paths).

### 8. No Error Tracking / Monitoring

**Current state**: Standard Python logging to stdout. No structured error collection, no metrics.

**Enterprise requirement**: Sentry, Datadog, or OpenTelemetry for error tracking, performance monitoring, and alerting.

**Implementation**:
- Sentry SDK for automatic error capture with context (run_id, tick, decision sequence).
- Prometheus metrics: `runs_total`, `runs_by_outcome`, `llm_calls_total`, `llm_latency_seconds`, `mcp_calls_total`, `mcp_latency_seconds`, `active_runs`, `defects_found_total`.
- Health check endpoints with dependency status (Postgres, MCP, Gemini API key, storage writability).
- Alert when: run fails to start, LLM API is unavailable, storage is full, too many consecutive fallback decisions.
- Grafana dashboard for real-time QA pipeline observability.


## P1 — LLM Intelligence

### 11. Vision Input Is Already Wired — But Agent Prompt Needs Screenshot Instructions

**Status**: Already implemented in `gemini_service.py`. Both async and sync paths send the screenshot PNG to Gemini.

**What's missing**: Instructions in the agent prompt to *analyze* the screenshot.

**Fix**: Update `docs/agent_system_prompt.md` (or wherever the system prompt template lives) with explicit vision instructions (see item #1 above).

### 12. Visited-Area Memory Is Basic

**Current state**: `lockstep_state.visited_cells` tracks coarse cell positions. `exploration_coverage.visited_cells_count` is sent to LLM. No total map cell estimate, no new-cells-last-5 metric.

**Enterprise requirement**: The LLM should understand spatial coverage: what fraction of the map has been explored, which quadrants are unvisited, which doors remain unopened.

**Implementation**:
- Add `total_map_cells_estimate` to `exploration_coverage` (from `analysis.map_width_units * map_height_units / (256*256)`).
- Add `new_cells_last_5_decisions` to track recent exploration rate.
- Add `unvisited_quadrants` (divide map into 4 quadrants, report which have 0 visited cells).
- Report `visited_doors` vs. `total_doors` from analysis data.

### 13. Static Analysis Not Enriched in Prompt

**Current state**: Agent prompt gets enemy counts, item ratios, map dimensions, secret count. Does NOT get: door locations, key types needed, teleporter locations, lift/crusher sectors, locked-door linedefs.

**Enterprise requirement**: The agent needs to plan key-hunting routes, find switches that open locked doors, identify teleporters.

**Implementation**:
- Extract from WAD's `LINEDEFS` (via omgifol): door sectors, key-locked lines (red/yellow/blue), teleporter things (type 39, 97), lifts.
- Pass to prompt template: `{door_count}`, `{locked_door_count}`, `{key_requirements}`, `{teleporter_count}`, `{lift_count}`.
- Send spatial hints: "The red key is in the northeast wing behind a yellow door."

### 14. No Cross-Run Defect Pattern Detection

**Current state**: Each run is analyzed independently. No aggregation across difficulty levels or runs.

**Enterprise requirement**: "This WAD always softlocks at sector 42 on skill 3+."

**Implementation**:
- `GET /runs/patterns?wad_id=X` endpoint.
- Cluster defect positions across runs using DBSCAN or grid clustering.
- Report per-difficulty coverage differences.
- Flag areas that consistently cause LLM failures.
- Highlight "always crashed here" sectors.

### 15. No Smoke Test Mode

**Current state**: No way to verify the full pipeline is healthy without uploading a custom WAD.

**Enterprise requirement**: `GET /health/smoke` that runs a known-good minimal test.

**Implementation**:
- `GET /runs/smoke` — runs against Freedoom IWAD MAP01 (built-in, no upload needed).
- Validates: MCP connectivity, game initialization, LLM API response, recording pipeline, report generation.
- Returns per-stage diagnostics with pass/fail and timing.
- Runs on a short budget (500 ticks).

---

## P2 — Medium Impact / Necessary Polish

### 16. Report Voice Sanitization Ordering Bug

**Current state**: `report_service.py:170-198` applies regex replacements sequentially. Longer patterns can compound. "agent" → "automated playthrough" then "automated playthrough was unable to" → "automated playthrough did not" but patterns also have "automated automated playthrough" → "automated playthrough" showing the double-replacement.

**Fix**: Reorder replacements longest-first. Use single-pass replacement tracking to prevent re-matching.

### 17. Prompt Injection Sanitization

**Current state**: `prompt_service.py:42` uses `str.replace("{" + key + "}", str(value))`. If a map name contains `{` or `}`, it corrupts the template.

**Fix**: Use `string.Template.safe_substitute()` or pre-validate/escape values that contain `{` `}`.

### 18. Report JSON Leaks Absolute Filesystem Paths

**Current state**: Report (and `RunOut`) exposes `recording_mp4_path`, `report_pdf_path`, etc. as absolute paths. In JSON API responses and WebSocket messages.

**Enterprise requirement**: Never expose internal filesystem paths. Use relative URLs instead.

**Fix**: Strip or relativize paths in serializers. Serve files through controlled endpoints (`/runs/{id}/recording`, `/reports/{id}/pdf`) only.

### 19. No Frontend Proxy — Separate CORS Config

**Current state**: Frontend runs on `:3000`, backend on `:8000`. CORS is open (`allow_origins=*` effectively in dev). No production proxy.

**Enterprise requirement**: Single origin. CORS is a security risk when left wide open.

**Fix**: Use Next.js rewrites to proxy `/api/` → backend in `next.config.ts`. Set strict CORS origins in production. Or deploy as a monolith.

### 20. Frontend WebSocket Has No Ping/Pong

**Current state**: `useRunStream.ts` reconnects on close with exponential backoff. But there is no ping/pong keepalive — idle connections may be silently dropped by load balancers.

**Enterprise requirement**: Long-lived WebSocket connections must be resilient.

**Fix**: Implement ping/pong in the backend (`ws.py`) every 30s. Client sends pong on `ping` message. If no response in 60s, close and reconnect.

### 21. Frontend Frame Re-renders on Unchanged Base64

**Current state**: `useRunStream.ts:71` sets `frame` state every time a `frame_b64` arrives, even if the base64 data is identical (e.g., when scene hasn't changed).

**Enterprise requirement**: No unnecessary React re-renders.

**Fix**: Compare `frame_b64` (or its length/hash) before setting state. Skip if identical.

### 22. Unbounded Decision/Defect Arrays in Frontend

**Current state**: `decisions[]` and `defects[]` in `useRunStream.ts` grow unbounded. After 10,000+ decisions, the frontend will crash from memory pressure.

**Enterprise requirement**: Memory-safe frontend for long runs.

**Fix**: Cap decisions at 500, defects at 200. Show "show all" link to fetch full history. Use windowing (virtual list) for long decision logs.

### 23. Frontend Only Shows Reasoning — Not Full Decision Context

**Current state**: `ReasoningLog.tsx` shows only `sequenceNumber`, `tick`, `tool`, `reasoning`, and `stopReason`. It does NOT show:
- The LLM input (state summary, objects, trace context)
- The full LLM output (the raw JSON decision before guard blocks)
- What was blocked/changed by the guard

**Enterprise requirement**: Debuggable decision trace for QA engineers.

**Fix**: Add expandable sections showing:
- Raw LLM input (compact state JSON, object list length, trace events)
- Raw LLM response JSON
- Guard modifications (green = kept, red = blocked, yellow = modified)
- MCP parameters sent vs. executed
- Timing breakdown: LLM latency vs. MCP latency vs. throttle

### 24. Telemetry Stride Is Fixed at 2 Tics

**Current state**: `recording_telemetry_stride: int = 2` in config. Hardcoded stride for telemetry sampling.

**Enterprise requirement**: Adaptive stride based on scene dynamism (more frames during combat, fewer during exploration).

**Fix**: Dynamic stride: 1 during combat, 3 during exploration, 5 while idle/stuck.

### 25. No WebSocket Reconnection Status Feedback

**Current state**: Frontend shows "Connected" / "Reconnecting" text. No detail on retry count, delay, or estimated recovery.

**Enterprise requirement**: Operators need to know when the connection is degraded.

**Fix**: Show retry attempt number, time until next retry, last successful message timestamp in connection status indicator.

---

## P2 — LLM Response Quality

### 26. LLM Response Parsing Still Fragile

**Current state**: `_parse_json_response()` tries block extraction → brace extraction. But the fallback to `_extract_json_braces` uses `find("{")` / `rfind("}")` which can match `{` in reasoning text.

**Enterprise requirement**: 99.9% parse success rate.

**Fix**: Add a third strategy: regex for `{.*}` with balanced braces. Add Pydantic validation of the parsed decision (typed fields, allowed values). Apply default values for missing fields instead of failing.

### 27. Observed Issue Parsing Ignores LLM Category

**Current state**: `normalize_observed_issue()` in `collector_service.py:217-224` parses `[CATEGORY]` prefix from the `observed_issue` text. But the LLM often sends a dict-like `{"category": "...", "description": "..."}` instead of plain text. These dicts get `str()`'d and the regex fails, producing generic `agent_observed_issue`.

**Enterprise requirement**: The agent should produce structured, categorized defect reports.

**Fix**: In `normalize_observed_issue()`, if `issue` is a dict, extract `category` and `description` directly. If it's text, fall back to the `[CATEGORY]` regex. Validate against known categories before falling back.

---

## P3 — Polish & Enterprise Features

### 31. No Usage Billing / Quota Tracking

**Enterprise requirement**: Track LLM API usage per tenant/team/project. Enforce monthly quotas. Show cost per run.

**Implementation**:
- Count tokens per LLM call (Gemini returns token counts).
- Store `llm_input_tokens`, `llm_output_tokens`, `llm_cost_estimate` per decision.
- Dashboard: "Total LLM cost this month: $42.17", "Avg cost per run: $0.83".


### 34. No Multi-Tenant / Project Isolation

**Current state**: Single workspace. All WADs, runs, and reports are visible to all users.

**Enterprise requirement**: Teams/projects with isolated data.

**Implementation**:
- Add `project_id` / `team_id` to WADs, runs, reports.
- API scoping: all queries filter by user's team.
- Create/switch teams in frontend.
- Super-admin can view all teams.

### 35. No Configuration UI

**Current state**: All configuration via `.env` file + env vars.

**Enterprise requirement**: In-app settings: LLM model selection, throttle config, CORS origins, default run parameters.

**Implementation**:
- Settings table in DB or config file watched for changes.
- UI: `/settings` page with sections for LLM, Storage, Runs, Notifications.
- No restart needed for most config changes.

### 36. No Performance Benchmarking

**Current state**: No metrics on how fast the system processes decisions.

**Enterprise requirement**: "Average LLM latency: 2.3s, average MCP latency: 0.8s, decisions per minute: 4.2."

**Implementation**:
- Store per-decision timing breakdowns (already partially stored).
- Dashboard visualization: latency over time, throughput by tool type, bottleneck analysis.
- Alert when LLM latency exceeds threshold (e.g., >10s average over 5 decision window).

### 37. No Map Overview Rendering in Reports

**Current state**: Map overview PNG is stored and exposed via API. But the PDF report does NOT include the map overview with player trail overlay.

**Enterprise requirement**: "Show me where the agent went and where it found defects."

**Implementation**:
- Render the map overview PNG in the PDF report.
- Overlay the player position trail as a colored path on the map.
- Mark defect locations with pins/icons.
- Mark deaths with X markers.


### 39. No Agent Behavior Configuration

**Current state**: Agent behavior is hardcoded in prompts and fallback logic.

**Enterprise requirement**: "Configure the agent to be aggressive vs. cautious", "Set exploration radius", "Prefer certain weapons".

**Implementation**:
- Agent profile presets: "Speedrunner" (aggressive, minimal backtracking), "Safety" (cautious, full coverage), "Exploit Hunter" (probes walls, tries glitches).
- Configurable parameters: aggression level, engagement range, exploration style (grid vs. random), weapon preference.
- Pass these into the system prompt and fallback logic.

### 40. No Documentation Portal

**Current state**: README + markdown files in `/docs`. No structured, searchable documentation.

**Enterprise requirement**: "How do I set up a CI pipeline? What does each MCP tool do? How do I interpret a report?"

**Implementation**:
- Next.js `/docs` route with MDX content.
- API reference auto-generated from OpenAPI schema.
- Video tutorials for onboarding.
- FAQ troubleshooting section.

---

## P3 — Technical Debt & Code Quality

### 41. `run_service.py` Is 1865 Lines — Needs Refactoring

**Current state**: A single monolithic file containing the run loop, all guard logic, telemetry handling, MCP execution, and more.

**Enterprise requirement**: Maintainable, testable code.

**Fix**: Split into:
- `run_loop.py` — core agent decision loop
- `run_guards.py` — lockstep guards and recovery
- `run_telemetry.py` — frame recording and broadcasting
- `run_utils.py` — state normalization, JSON helpers
- `run_constants.py` — constants and config

### 42. Weak Type Hints in Many Places

**Current state**: Many functions use `dict[str, Any]` where specific TypedDicts would improve safety. `mcp_params` is `dict` with no schema validation.

**Enterprise requirement**: Type-safe code that catches bugs at CI time.

**Fix**:
- Define TypedDicts for: `LLMInput`, `LLMDecision`, `LockstepState`, `McpCall`, `TelemetryFrame`.
- Add `mypy` to CI and resolve all type errors.
- Use Pydantic models for all inter-service data transfer.

### 43. No API Versioning

**Current state**: All endpoints are unversioned (`/runs`, `/wads`, etc.).

**Enterprise requirement**: Backward-compatible API evolution.

**Fix**: Prefix all routes with `/v1/`. Support redirect from unversioned to latest. Document breaking changes in migration guide.

### 44. Database Migration Is Manual

**Current state**: SQL schema in `/sql/schema.sql` and Alembic migrations exist but are not automatically applied on deploy.

**Enterprise requirement**: Zero-downtime migrations in CI/CD.

**Fix**: Alembic auto-generates migrations. CI runs `alembic upgrade head` before tests. Production deploys run migrations as a pre-deploy step.

### 45. No Backup / Restore

**Current state**: No automated backup of Postgres database or storage files.

**Enterprise requirement**: Point-in-time recovery for database. S3/Blob Storage archival for recordings and reports.

**Implementation**:
- Schedule `pg_dump` to S3 with 30-day retention.
- Sync `storage/` directory to S3/GCS.
- One-click restore from backup in admin UI.

### 46. No Load Testing

**Current state**: Never tested under load. Unknown how many concurrent runs the system can handle.

**Enterprise requirement**: SLA: 99.9% uptime, <5s LLM decision time P95, support 5 concurrent runs.

**Implementation**:
- Locust or k6 load tests: simulate concurrent run starts, telemetry streaming, report generation.
- Benchmark with known WADs at multiple difficulty levels.
- Publish results: max concurrent runs before degradation, bottleneck analysis.

### 47. Frontend Has No Error Boundaries

**Current state**: No React error boundaries. A crash in one component can take down the entire dashboard.

**Enterprise requirement**: Resilient frontend that survives component failures.

**Fix**: Add error boundaries around each major view (WadLibrary, LiveRun, RunDetail, HealthDashboard, etc.). Show "Something went wrong" with retry button.

### 48. Frontend Has No Loading / Empty States for Sub-Components

**Current state**: `SkeletonRows` serves as loading state for some lists. But DecisionTimeline, MapCanvas, HealthSparkline have no loading states.

**Enterprise requirement**: Professional UX with consistent loading skeletons.

**Fix**: Add loading skeletons for all async-dependent components. Add empty states ("No decisions recorded", "No defects found", "No run history") instead of blank space.

### 50. No Accessibility (a11y)

**Current state**: Basic semantic HTML, but no ARIA labels, keyboard navigation, color contrast audit, screen reader testing.

**Enterprise requirement**: WCAG 2.1 AA compliance.

**Fix**: Audit with axe-core. Add alt text to all images. Ensure keyboard navigation for all interactive elements. Fix color contrast for status badges and heatmap.

---
