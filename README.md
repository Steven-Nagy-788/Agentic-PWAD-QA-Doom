# Agentic PWAD QA for Doom

Autonomous QA system for Doom PWAD maps. It uploads and analyzes a WAD, starts a ViZDoom run through an MCP server, lets a Gemini model choose high-level actions in a lockstep loop, records telemetry/video/evidence, detects map and agent-run defects, and generates an audit-ready PDF report.

This repository is a localhost-only proof of concept. It has no authentication, authorization, or multi-user ownership boundary. Do not expose its ports to an untrusted network.

Local development and Docker Compose operation are supported with PostgreSQL, FastAPI, FastMCP, ViZDoom, Gemini, and the Next.js frontend.

## What the System Does

The product is built around one QA workflow:

1. Upload a Doom PWAD.
2. Parse static map data with `omgifol` and custom Python analysis.
3. Select a map, difficulty, run length, and behavior profile.
4. Start a lockstep AI QA run.
5. Stream state, screenshots, decisions, progress, and defects to the UI.
6. Persist every decision, event, position, defect, token count, and artifact.
7. Generate an HTML/PDF QA report with evidence, coverage limits, video link, metrics, and defect details.

The project uses free Freedoom IWADs through ViZDoom by default. Original Doom assets are not required.

## Architecture

```text
Next.js frontend
    |
    | REST + WebSocket
    v
FastAPI backend
    |
    | SQLAlchemy async
    v
PostgreSQL audit database
    |
    +--> storage/ WADs, screenshots, MP4 recordings, PDFs, map PNGs
    |
    | FastMCP SSE
    v
mcp-doom service
    |
    v
ViZDoom + Freedoom/PWAD
    ^
    |
Gemini decision service
```

### Service Responsibilities

`Backend/` is the FastAPI application. It owns uploads, database models, static analysis, run orchestration, LLM calls, report generation, WebSocket broadcasts, settings, and audit APIs.

`mcp-doom/` is a separate FastMCP service. It owns ViZDoom startup, IWAD/PWAD loading, game state extraction, compound actions, navigation helpers, and the optional async executor/director path.

`frontend/` is the Next.js application. It provides upload, WAD detail, run start, run live monitor, reports, settings, and aggregate run views.

`Backend/storage/` contains local runtime artifacts. It is not source code and should be treated as generated data.

Supplemental docs:

- `docs/db schema.md`
- `docs/backend/`
- `docs/frontend/`
- `docs/operations/`
- `docs/historical/` for superseded reviews and implementation notes

## Core Design

### Lockstep AI Loop

The active production loop is lockstep:

1. Backend asks MCP for state/screenshot.
2. Backend builds compact current-state JSON plus a bounded same-run action ledger.
3. Gemini returns one structured MCP action.
4. Backend normalizes technical parameters and rejects malformed requests without inventing a replacement.
5. MCP executes the action and advances the game.
6. Backend records the decision, telemetry, video frame, cost, and progress.

This is slower than a fully autonomous real-time agent, but it is much easier to audit and defend in a QA context because every game advancement is tied to a stored decision and tool call.

### MCP Boundary

The backend does not directly press ViZDoom buttons. It calls MCP tools such as `start_game`, `get_state`, `explore`, `move_to`, `aim_and_shoot`, `strafe_and_shoot`, `retreat`, and `take_action`. That boundary keeps simulator code out of the API process and gives the decision trace clear action semantics.

### Persistence

PostgreSQL stores:

- `wad_files`
- `static_analysis_results`
- `test_runs`
- `agent_decisions`
- `game_events`
- `agent_position_trail`
- `defects`
- `test_reports`
- `notable_event_screenshots`
- `config_entries`
- `wad_spatial_memory`
- `wad_hypotheses`

Spatial cells and hypotheses are reviewer-only analytics. They are not injected into later gameplay decisions.

### Reports

Reports are rendered from `Backend/app/templates/report.html.j2` through Jinja2 and compiled with WeasyPrint. PDF rendering runs in a worker thread so the FastAPI event loop is not blocked by CPU-bound PDF work.

### MCP Executor

MCP-Doom retains its standalone async executor for direct MCP use. The backend product runtime is lockstep-only and does not include a Director adapter.

## Repository Layout

```text
.
|-- Backend/
|   |-- app/
|   |   |-- core/           # settings, DB, typed runtime structures
|   |   |-- models/         # SQLAlchemy models
|   |   |-- repositories/   # DB access wrappers
|   |   |-- routers/        # FastAPI routes
|   |   |-- serializers/    # Pydantic API schemas
|   |   |-- services/       # analysis, run loop, reports, memory, LLM, recording
|   |   `-- templates/      # PDF/HTML report templates
|   |-- migrations/         # Alembic migrations
|   |-- sql/schema.sql      # full schema bootstrap
|   |-- tests/              # backend unit/service tests
|   `-- storage/            # generated artifacts and uploaded WADs
|-- mcp-doom/
|   |-- src/doom_mcp/
|   |   |-- server.py       # FastMCP tool definitions
|   |   |-- game_manager.py # game lifecycle and tool behavior
|   |   |-- game_setup.py   # WAD parsing, map discovery, load preflight
|   |   |-- executor.py     # experimental async executor
|   |   |-- state.py        # screenshots, variables, sectors, objects
|   |   `-- objects.py      # Doom entity metadata
|   `-- tests/
|-- frontend/
|   |-- app/                # Next.js App Router pages
|   |-- components/         # UI primitives
|   |-- hooks/              # API/query/stream hooks
|   `-- lib/                # REST client and shared types
|-- docs/
`-- .github/workflows/ci.yml
```

## Prerequisites

Local development assumes Linux.

- Python 3.11 or newer
- PostgreSQL 14 or newer
- Node.js 22 or newer with npm, or Bun, for the frontend
- FFmpeg for MP4 recording
- WeasyPrint system libraries, normally installed by the Python wheel on modern Linux but may require Cairo/Pango packages on some distros
- ViZDoom runtime libraries: OpenGL and SDL, for example `libgl1` and `libsdl2-2.0-0`
- Gemini API key for real LLM decisions

On Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib ffmpeg libgl1 libsdl2-2.0-0
```

## Backend Setup

```bash
cd Backend
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `Backend/.env`:

```dotenv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=doom_agentic_qa
POSTGRES_USER=doom_agentic
POSTGRES_PASSWORD=
DATABASE_URL=

GEMINI_API_KEY=your_key_here
LLM_MODEL=gemini-2.5-flash-lite
MCP_DOOM_SSE_URL=http://localhost:8001/sse
LLM_THROTTLE_SECONDS=2
GEMINI_RATE_LIMIT_CALLS_PER_MINUTE=15
```

Set `POSTGRES_PASSWORD` to a generated local secret. Leave `DATABASE_URL` blank to derive it
from the `POSTGRES_*` fields, or provide a complete async SQLAlchemy URL.

Create the database and apply the schema:

```bash
make db-init
make db-upgrade
```

If Alembic is not desired for a clean local database, `make db-schema` applies `Backend/sql/schema.sql` directly.

Start the backend:

```bash
cd Backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Useful backend URLs:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/detailed`
- `http://127.0.0.1:8000/health/smoke`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/metrics`

## MCP Doom Setup

```bash
cd mcp-doom
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
python -c "import vizdoom; print(vizdoom.__version__)"
```

Start the MCP SSE server on the URL expected by the backend:

```bash
cd mcp-doom
.venv/bin/fastmcp run src/doom_mcp/server.py --transport sse --host 127.0.0.1 --port 8001 --path /sse
```

The MCP server supports both campaign maps and uploaded PWADs. For normal backend use, keep it running while the backend starts runs.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Or with Bun:

```bash
cd frontend
bun install
bun dev
```

Open `http://127.0.0.1:3000`.

The frontend defaults to REST through `/api/v1`. For local development on `localhost:3000` or `localhost:3001`, live WebSockets automatically connect directly to `http://localhost:8000/v1` because `next start` does not proxy backend WebSockets reliably. For non-local deployments, set:

```dotenv
NEXT_PUBLIC_API_BASE=/api/v1
NEXT_PUBLIC_WS_BASE=https://your-backend.example.com/v1
```

If the frontend and backend are served by one reverse proxy that supports WebSocket upgrades, `NEXT_PUBLIC_WS_BASE` can be omitted and the same-origin `/api/v1` path can be used.

## First Manual Run

With PostgreSQL, MCP, backend, and frontend running:

1. Open the frontend.
2. Upload a `.wad` file.
3. Wait for static analysis to finish and map names to appear.
4. Open the WAD detail page.
5. Select map, difficulty, run length, and behavior profile.
6. Start a run.
7. Watch decisions, state, progress, defects, and recording/report status.
8. Open the generated report PDF after completion.

The same path can be driven with curl:

```bash
curl -s -F "file=@/absolute/path/to/map.wad" http://127.0.0.1:8000/v1/wads/upload
curl -s http://127.0.0.1:8000/v1/wads/{wad_id}/maps
curl -s -X POST http://127.0.0.1:8000/v1/runs \
  -H "Content-Type: application/json" \
  -d '{"wad_file_id":"{wad_id}","map_name":"MAP01","difficulty_level":3,"max_ticks":3000,"behavior_profile":"thorough"}'
curl -s http://127.0.0.1:8000/v1/runs/{run_id}
curl -s http://127.0.0.1:8000/v1/runs/{run_id}/decisions
curl -s http://127.0.0.1:8000/v1/runs/{run_id}/defects
curl -L http://127.0.0.1:8000/v1/runs/{run_id}/report/pdf -o report.pdf
```

## API Surface

Main routes:

- `POST /v1/wads/upload`
- `GET /v1/wads`
- `GET /v1/wads/{wad_id}`
- `GET /v1/wads/{wad_id}/maps`
- `GET /v1/wads/{wad_id}/analysis`
- `GET /v1/wads/{wad_id}/map-png`
- `POST /v1/wads/{wad_id}/reanalyze`
- `POST /v1/runs`
- `GET /v1/runs`
- `GET /v1/runs/{run_id}`
- `DELETE /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/force-stop`
- `GET /v1/runs/{run_id}/trace`
- `GET /v1/runs/{run_id}/events`
- `GET /v1/runs/{run_id}/decisions`
- `GET /v1/runs/{run_id}/defects`
- `GET /v1/runs/{run_id}/position-trail`
- `GET /v1/runs/{run_id}/recording`
- `GET /v1/runs/{run_id}/report/pdf`
- `GET /v1/runs/{run_id}/usage`
- `GET /v1/runs/{run_id}/benchmark`
- `GET /v1/runs/compare`
- `WS /v1/ws/runs/{run_id}`
- `GET /v1/settings`
- `PATCH /v1/settings`
- `GET /v1/settings/behavior-profiles`
- `GET /health`, `/health/detailed`, `/health/mcp`, `/health/gemini`, `/health/smoke`

OpenAPI docs are available at `/docs` while the backend is running.

## Configuration

Static configuration comes from `Backend/.env`. Runtime overrides are also stored in `config_entries` and exposed through `/v1/settings`.

Important settings:

| Setting | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Required for real model decisions. Without it, deterministic fallbacks are used where implemented. |
| `LLM_MODEL` | Model name stored on each run. Current default is `gemini-2.5-flash-lite`. |
| `LLM_THROTTLE_SECONDS` | Cap on sleep between LLM decisions. Use `0` for no local sleep when paid limits allow it. |
| `GEMINI_RATE_LIMIT_CALLS_PER_MINUTE` | Local Gemini request limiter. Use `0` to disable local limiting. |
| `LLM_INPUT_COST_PER_MILLION` | Cost estimate input rate. |
| `LLM_OUTPUT_COST_PER_MILLION` | Cost estimate output rate. |
| `DEFAULT_RUN_TICKS` | Default run length when the request omits `max_ticks`. |
| `MAX_RUN_TICKS` | Hard cap for requested run length. |
| `DEFAULT_AGENT_BEHAVIOR` | Default behavior profile: `thorough`, `fast`, or `exploit_focused`. |
| `MCP_DOOM_SSE_URL` | Backend URL for the MCP SSE endpoint. |
| `RECORDING_FPS` | Target MP4 recording FPS. |
| `LIVE_FRAME_FPS` | WebSocket screenshot broadcast cap. |

Gemini pricing and rate limits change. Check the official Gemini pricing and rate-limit pages before presenting cost estimates publicly:

- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits

The defaults are intentionally editable because the correct values depend on the selected model, account tier, and billing mode.

## Behavior Profiles

Profiles tune throttle and prompt stance. Recording fidelity is controlled independently through `RECORDING_TELEMETRY_STRIDE`, which defaults to `1`.

- `thorough`: slower, coverage-oriented, default for defensible QA.
- `fast`: faster exploration and lower delays.
- `exploit_focused`: aggressive probing for stuck states, crashes, geometry issues, and progression failures.

Each profile must define throttle keys `combat`, `low_health`, `stuck`, and `default`, because those names are read by the lockstep loop.

## AI Memory

Gameplay decisions use same-run memory only. The prompt receives the latest detailed actions and deterministic milestones for older actions, capped by `SAME_RUN_LEDGER_MAX_CHARS`. Cross-run spatial cells, hypotheses, summary counts, and recurring defects remain available to reviewers on the WAD detail page but never influence the agent.

## Defect Detection Notes

The system records both static and runtime defects. It avoids labeling unfound secrets as unreachable unless coverage is high enough to support that conclusion. Below 60 percent coverage, missing secrets are treated as insufficient evidence rather than a map defect.

Important categories include:

- `pwad_crash`
- `softlock_navigation`
- `stuck_position`
- `resource_balance`
- `unreachable_secret`
- `agent_observed_*`

## Testing

Backend:

```bash
cd Backend
.venv/bin/python -m pytest -q
```

MCP:

```bash
cd mcp-doom
.venv/bin/python -m pytest -q -m "not integration"
xvfb-run -a .venv/bin/python -m pytest -q -m integration
```

Frontend:

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

Equivalent Bun commands:

```bash
cd frontend
bun run test
bun run lint
bun run build
PLAYWRIGHT_WEB_SERVER_COMMAND="bun run start --hostname 127.0.0.1 --port 3100" bun run test:e2e
```

CI is defined in `.github/workflows/ci.yml` and runs backend tests, fresh PostgreSQL Alembic checks, MCP unit tests, frontend Vitest/lint/build/browser checks, and Docker image builds. `.github/workflows/full-e2e.yml` is scheduled/manual and starts the Docker Compose stack, runs `/health/smoke`, uploads a generated PWAD fixture, creates a short run, and verifies PDF/recording artifacts.

Latest local verification on 2026-06-06:

- Backend: `183 passed`.
- Backend targeted report/path/outcome/smoke tests: `28 passed`.
- MCP unit: `51 passed, 57 deselected`.
- MCP generated-PWAD integration fixture: `1 passed` under `xvfb-run`.
- Frontend: `23 passed`, lint clean, production build successful.
- Browser E2E: Playwright live map layout test `1 passed` with production server override.

## Operational Constraints

- One active run is the supported operating mode.
- The backend uses a PostgreSQL advisory lock to prevent concurrent run creation.
- Active run tasks are stored in the process-local `RUN_TASKS` dictionary. This is correct for a single Uvicorn process but does not support canceling a run from another backend replica.
- Run cancellation across multiple backend replicas is not supported.
- Report PDF generation and WAD analysis use CPU-bound libraries. PDF generation is threaded; map analysis should remain off the event loop when called from async paths.
- Docker Compose binds host ports to `127.0.0.1` for local demonstration use.
- PR CI is deterministic and does not require paid Gemini calls; scheduled/manual full e2e uses `GEMINI_API_KEY` when the secret is configured and otherwise exercises deterministic fallback mode.

## Troubleshooting

`/health/detailed` is the fastest first check. It reports PostgreSQL, MCP, Gemini key presence, storage writability, and active run status.

MCP is unreachable:

- Confirm the MCP server is running on port 8001.
- Confirm `MCP_DOOM_SSE_URL=http://localhost:8001/sse`.
- Confirm no firewall or stale process owns the port.

ViZDoom fails to start:

- Install OpenGL/SDL libraries.
- Verify `python -c "import vizdoom"` inside `mcp-doom/.venv`.
- Check whether the PWAD has a valid map marker and player start.

No Gemini decisions:

- Confirm `GEMINI_API_KEY` is set in `Backend/.env`.
- If the key is intentionally absent, `/health/smoke` reports the Gemini probe as skipped and the run loop uses deterministic fallback behavior where implemented.
- Run `/health/gemini`.
- Lower `GEMINI_RATE_LIMIT_CALLS_PER_MINUTE` if the API returns rate-limit errors.

Frontend will not start:

- Install Node.js 22 and npm.
- Or install Bun and run `bun install` in `frontend/`.
- Confirm the backend CORS origins include `http://localhost:3000`.

Live run page reconnects forever or never shows video:

- Confirm the backend route `ws://127.0.0.1:8000/v1/ws/runs/{run_id}` accepts connections.
- For local `next start`, set `NEXT_PUBLIC_WS_BASE=http://127.0.0.1:8000/v1` if automatic local inference is not enough.
- Confirm the backend log shows WebSocket `101 Switching Protocols`, not `403`.
- Confirm the run is actually `running`; completed runs show the report/recording detail page instead.

Recording is missing:

- Confirm FFmpeg is installed.
- If the PWAD crashed before gameplay initialized, no recording can be produced.
- Use `/v1/runs/{run_id}` to inspect `recording_metadata` and failure fields.

## Roadmap

High-value remaining work:

- Worker queue for report regeneration and heavier analysis jobs.
- Multi-replica run orchestration with persistent task state.
- Backup/restore scripts for PostgreSQL and storage artifacts.
- Load testing with k6 or Locust.
- Frontend browser E2E tests once a Node runtime and a stable local test fixture are available.
- Benchmarks comparing behavior profiles, throttle settings, and model choices.

## License and Assets

The project uses Freedoom through ViZDoom for free IWAD coverage. Do not commit commercial Doom IWADs or third-party PWADs unless their licenses allow redistribution.
