# AGENTS.md — Agentic PWAD QA for Doom

Three services in one repo:

| Directory | Tech | Entrypoint | Start |
|-----------|------|------------|-------|
| `Backend/` | FastAPI + SQLAlchemy + asyncpg + Alembic + WeasyPrint + Google GenAI | `app/main.py` | `make run` (or `uvicorn ...`) |
| `mcp-doom/` | FastMCP 3.2 + ViZDoom 1.3 | `src/doom_mcp/server.py` | `.venv/bin/fastmcp run src/doom_mcp/server.py --transport sse --host 127.0.0.1 --port 8001 --path /sse` |
| `frontend/` | Next.js 16 + React 19 + Tailwind v4 + TanStack Query + Recharts + Vitest | standard App Router | `npm run dev` or `bun dev` |

## Commands

```bash
# Backend (from Backend/)
make install                # .venv + pip install -r requirements.txt
make db-init && make db-upgrade  # create DB + Alembic migrate (or make db-schema)
.venv/bin/python -m pytest -q     # 194 tests (as of 2026-05-24)

# MCP-Doom (from mcp-doom/)
pip install -e ".[dev]"       # editable install + pytest/pytest-asyncio
pytest -q                     # all tests (100)
pytest -k "not integration"   # unit only (no ViZDoom needed)
pytest -m integration         # integration only (needs ViZDoom runtime + display libs)

# Frontend (from frontend/)
npm test -- --run             # Vitest (18 tests)
npm run lint                  # ESLint
npm run build                 # Next.js production build
# Also works with: bun run test, bun run lint, bun run build
```

## Architecture

- **Lockstep loop**: Backend calls MCP `get_state` → builds LLM prompt → Gemini returns action → MCP `take_action` → record. Every game advance ties to a stored decision.
- **MCP boundary**: Backend never talks to ViZDoom directly. All game interaction is through MCP tools at `mcp-doom/src/doom_mcp/server.py`.
- **Director mode** (`executor.py`) exists but is **not** the active runtime path. The product uses lockstep.
- One active run at a time. PostgreSQL advisory lock prevents concurrent runs. Run tasks are process-local (`RUN_TASKS` dict) — cross-replica cancellation not supported.
- PDF reports render via WeasyPrint in a worker thread.

## Key Config

Backend reads `Backend/.env`. Critical vars:
- `GEMINI_API_KEY` — required for real LLM decisions (fallback deterministic otherwise)
- `MCP_DOOM_SSE_URL` — defaults to `http://localhost:8001/sse`
- `LLM_THROTTLE_SECONDS`, `GEMINI_RATE_LIMIT_CALLS_PER_MINUTE` — rate limiting
- `DEFAULT_RUN_TICKS`, `MAX_RUN_TICKS` — run length controls

Frontend defaults to REST via `/api/v1` (rewritten by `next.config.ts` to `localhost:8000`). WebSockets auto-detect `localhost:3000/3001` → `ws://localhost:8000/v1`. For non-local deployment, set `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_WS_BASE`.

## Gotchas

- **frontend/AGENTS.md** contains a Next.js version warning — preserve that file; it flags breaking API differences in Next.js 16 vs earlier versions.
- MCP integration tests (marked `@pytest.mark.integration`) require ViZDoom runtime (OpenGL, SDL). CI installs `libgl1 libsdl2-2.0-0` but pytest skips them automatically if ViZDoom is absent.
- The `pytest-asyncio` version in Backend is pinned to `1.3.0` (older). In mcp-doom, `asyncio_mode = auto` is set in `pyproject.toml`.
- `Backend/.env` and `Backend/.venv` are in `.gitignore`. Never commit them.
- `Backend/storage/` contains runtime artifacts (WADs, screenshots, recordings, PDFs) — not source code.
- No Docker or compose files exist yet (roadmap item).
- Frontend uses `@/` path alias (maps to `frontend/` root).
