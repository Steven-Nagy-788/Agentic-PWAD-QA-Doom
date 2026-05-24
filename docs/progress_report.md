# Progress Report

Generated: 2026-05-24.

This file records the implementation state after the current stabilization pass. The source of truth for setup and operation is the top-level `README.md`.

## Completed Core System

| Area | Status | Notes |
| --- | --- | --- |
| PWAD upload and validation | Done | Uploads persist WADs, detect maps, store hashes, and expose map lists. |
| Static analysis | Done | Uses `omgifol` plus custom Python logic for things, skills, map geometry, doors, locks, lifts, teleporters, balance ratios, difficulty, and map PNGs. |
| MCP ViZDoom boundary | Done | `mcp-doom` exposes FastMCP tools and isolates ViZDoom from the API process. |
| Lockstep run loop | Done | Backend pauses between decisions, sends structured state/screenshot to Gemini, guards the decision, executes one MCP action, and persists evidence. |
| WebSocket live stream | Done | Streams run status, frames, progress, decisions, defects, reports, and keepalive messages. |
| Recording | Done | MP4 artifacts and metadata are stored when gameplay initializes successfully. |
| Reports | Done | Jinja2 plus WeasyPrint PDF generation, with PDF rendering moved off the event loop. |
| Cross-run memory | Done | Stores and formats prior outcomes, defects, hypotheses, knowledge, and spatial cells for future runs. |
| Runtime settings | Done | Model, throttle, rate limit, cost rates, run lengths, FPS, recording, and behavior defaults are exposed through settings. |
| Behavior profiles | Done | `thorough`, `fast`, and `exploit_focused` profiles use matching throttle keys consumed by the run loop. |
| CI | Done | GitHub Actions covers backend, MCP, and frontend test/build jobs. |

## Tests

Local verification on 2026-05-24:

| Suite | Command | Result |
| --- | --- | --- |
| Backend | `cd Backend && .venv/bin/python -m pytest -q` | 194 passed |
| MCP | `cd mcp-doom && .venv/bin/python -m pytest -q` | 100 passed |
| Frontend | `cd frontend && bun run test && bun run lint && bun run build` | 18 passed, lint clean, build successful |
| Browser E2E | Production frontend on `127.0.0.1:3001`, backend on `127.0.0.1:8000`, MCP on `127.0.0.1:8001` | Live frame, reasoning, MCP input/output, recording, map trail, and PDF report verified |

Repository test inventory:

- Backend: 16 Python test files.
- MCP: 9 Python test files.
- Frontend app: 4 local component/hook test files.

## Recent Fixes

- Fixed behavior-profile throttle key mismatch.
- Fixed fallback import in `run_utils.get_behavior_profile()`.
- Fixed smoke test `scenario_wad=""` bug by passing `None`.
- Made Gemini model, request rate limit, and cost rates configurable.
- Lowered default LLM throttle from 12 seconds to 2 seconds.
- Allowed `LLM_THROTTLE_SECONDS=0` and `GEMINI_RATE_LIMIT_CALLS_PER_MINUTE=0` for paid-tier/no-local-limit operation.
- Added total map cell estimate, coverage percent, rolling new-cell count, and unvisited quadrants to lockstep metrics.
- Added persistent `wad_spatial_memory`, `wad_hypotheses`, and `wad_knowledge_base` schema.
- Persisted meaningful spatial events after runs and formatted them into the memory briefing.
- Prevented low-coverage secret non-discovery from becoming an `unreachable_secret` defect.
- Fixed report recording availability logic when a recording URL exists but quality status is not `ok`.
- Moved WeasyPrint PDF generation into `asyncio.to_thread`.
- Fixed frontend health probes to call root `/health` endpoints instead of versioned `/v1/health` paths.
- Added `/v1/ws/runs/{run_id}` WebSocket route and frontend direct-backend WebSocket inference for local `next dev`/`next start`.
- Fixed live-frame de-duplication so equal-length frames are not dropped.
- Added MCP input and MCP output to live WebSocket messages and expanded the latest live decision by default.
- Added static map bounds to map APIs and aligned frontend/report trail projection to the generated map PNG coordinate space.
- Made report trail overlays more legible with connected path, start marker, and end marker.
- Reduced report decision appendix size by sampling first/last decisions and truncating MCP JSON while keeping full traces in the API/database.
- Made MP4 recording use deterministic H.264 transcode instead of first attempting a noisy hardware encoder path.
- Added CI workflow.
- Split WAD setup/preflight helpers out of `mcp-doom/src/doom_mcp/game_manager.py` into `game_setup.py`.
- Replaced the one-line README with a full operating manual.

## Remaining Gaps

| Gap | Impact |
| --- | --- |
| Docker/compose deployment | New machines still need manual local setup. |
| Backup/restore | No scheduled `pg_dump` or artifact storage backup. |
| Load testing | No measured concurrency or long-run performance envelope. |
| Multi-replica run orchestration | `RUN_TASKS` is process-local, so cancel/control does not work across backend replicas. |
| Worker queue | Heavy report regeneration and analysis still live in the API service boundary. |
| Browser E2E in CI | Local browser E2E passed, but CI still needs a stable browser fixture and artifact capture. |
| Director product path | Async Director/Executor code exists but is experimental and not the active product loop. |

## Current Assessment

The architecture is defensible for a graduate project: it has a real simulator boundary, an auditable LLM loop, persistent telemetry, generated evidence, and tests around the critical paths. It is not yet production-deployable in the infrastructure sense because packaging, backups, load testing, and multi-replica task control are not implemented.
