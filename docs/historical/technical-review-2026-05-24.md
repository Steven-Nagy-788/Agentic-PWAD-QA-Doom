# Historical: Technical Review - 2026-05-24

## Scope

This review covers the implementation after the 2026-05-24 stabilization and product E2E pass. It includes code review, local automated tests, and a real product-path run using PostgreSQL, the FastAPI backend, the FastMCP Doom server, ViZDoom/Freedoom, Gemini, and the Next.js frontend.

## Test Results

| Suite | Result |
| --- | --- |
| Backend | `194 passed` via `cd Backend && .venv/bin/python -m pytest -q` |
| MCP | `100 passed` via `cd mcp-doom && .venv/bin/python -m pytest -q` |
| Frontend | `18 passed`, lint clean, production build successful via `bun run test && bun run lint && bun run build` |

## E2E Product Run

Environment:

- PostgreSQL: `127.0.0.1:5432`.
- MCP: `http://127.0.0.1:8001/sse`.
- Backend: `http://127.0.0.1:8000`.
- Frontend: production `next start` on `http://127.0.0.1:3001`.
- WAD: `antony.wad`, MAP01.

Validated product behavior:

- Root health endpoints returned OK for backend and MCP.
- Created a real run from the backend and opened it through the frontend.
- Live page connected over `ws://127.0.0.1:8000/v1/ws/runs/{run_id}`.
- Live page rendered Doom gameplay frames.
- Live page showed LLM reasoning, selected MCP tool, MCP input JSON, MCP output JSON, token/cost counters, and run stats.
- Completed/cancelled detail page showed aligned map trail overlay, token usage, latency benchmark, tool counts, defects, recording, and report status.
- Recording endpoint returned valid H.264 MP4: 640x480, 345 frames, 11.5 seconds for the E2E run.
- PDF endpoint returned a WeasyPrint PDF: 18 pages after appendix sampling and JSON truncation.
- Rendered PDF pages were visually inspected: executive summary, report metrics, trail overlay, event trace, and sampled LLM/MCP decision appendix.
- Decision API contains stored reasoning plus MCP input/output for traceability.

## Fixed Issues From Review

- Behavior profile throttle keys now match run-loop reads.
- `run_utils.get_behavior_profile()` fallback no longer imports a missing module-level setting.
- Smoke service no longer passes `scenario_wad=""`.
- WeasyPrint PDF rendering is off the event loop.
- Low-coverage secret non-discovery no longer becomes an `unreachable_secret` defect.
- Recording availability is represented correctly when a recording URL exists.
- LLM cost, model, throttle, and local rate-limit settings are configurable.
- Total map cell estimate, coverage percent, new-cell count, and unvisited quadrants are wired into lockstep metrics.
- Persistent WAD memory tables and run memory persistence are present.
- CI exists for backend, MCP, and frontend.
- Frontend health page now calls root `/health` endpoints.
- WebSocket route mismatch is fixed with `/v1/ws/runs/{run_id}`.
- Local production frontend WebSocket now connects directly to the backend instead of depending on Next rewrite WebSocket proxying.
- Live frame de-duplication now compares actual frame content instead of base64 length.
- Live decision stream now includes MCP input and MCP output.
- Map trail projection now uses static map bounds instead of trail-only bounds.
- Report appendix now samples decisions and truncates MCP JSON, avoiding oversized PDFs.
- Recording path now avoids the noisy hardware H.264 attempt and transcodes deterministically.

## Code Review Findings

No blocking runtime bugs remain from the original review list.

Residual non-blocking risks:

- No Docker/compose deployment yet.
- Active run task control remains process-local through `RUN_TASKS`; multi-replica backend deployment is not supported.
- Heavy report regeneration and heavier analysis should move to a worker queue before production use.
- Backup/restore and load testing are still missing.
- Browser E2E is manual/local; CI does not yet capture browser screenshots, video frames, or report PDFs.
- Director/Executor mode is experimental and should not be presented as the primary product loop.

## Product Review

The core product is now demonstrable: a user can start a run, watch gameplay live, see the agent's reasoning and tool calls, inspect the path overlay, play back the generated recording, and open a professional PDF report.

The strongest qualities are the audit trail, the MCP execution boundary, the lockstep decision trace, persistent telemetry, and the generated evidence package.

The main product limitation is run duration and cost. The model prompt is large and every decision is serialized for auditability. This is architecturally defensible for QA, but demos should use a short run length or a lower throttle, and longer coverage runs should be presented as overnight/benchmark jobs rather than instant interactions.

The reporting story is defensible. Short runs correctly report limited coverage; longer runs produce richer trail, defect, recording, and benchmark evidence. The PDF should remain an evidence summary, while the API/database remain the source of the full decision trace.
