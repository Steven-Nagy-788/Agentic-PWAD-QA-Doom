# Architecture

## System Overview

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐
│ Frontend │◄──►│ Backend  │◄──►│ MCP-Doom │◄──►│ ViZDoom      │
│ Next.js  │    │ FastAPI  │    │ FastMCP  │    │ (Doom Engine)│
│ :3000    │    │ :8000    │    │ :8001    │    │              │
└──────────┘    └────┬─────┘    └──────────┘    └──────────────┘
                     │
                     ▼
              ┌──────────────┐    ┌──────────┐
              │ PostgreSQL   │    │ Gemini   │
              │ :5432        │    │ (Google) │
              └──────────────┘    └──────────┘
```

## Scope & Constraints

- **Localhost-only** proof of concept (no auth, no TLS)
- **Single active run** at a time (PostgreSQL advisory lock)
- **Process-local task registry** — cross-replica cancellation not supported
- **No worker queue** — runs execute in-process as asyncio tasks

## Four Services

| Service | Role | Technology |
|---------|------|------------|
| **Frontend** | Dashboards: WAD library, run launcher, live monitor, history, health, settings, docs | Next.js 16 App Router, React 19, Tailwind v4, TanStack Query |
| **Backend** | Core logic: REST API, WebSocket streaming, lockstep loop, LLM integration, static analysis, defect detection, PDF report generation | FastAPI, SQLAlchemy 2.0 async, asyncpg, Gemini API, WeasyPrint |
| **MCP-Doom** | Game server: Wraps ViZDoom as MCP tools, state extraction, compound actions, autonomous executor, spatial memory | FastMCP 3.2, ViZDoom 1.3, Pillow, NumPy |
| **PostgreSQL** | All persistence: WADs, runs, decisions, events, defects, reports, cross-run memory | PostgreSQL 16 with asyncpg |

## Lockstep Runtime Flow

```
1. READ STATE via MCP get_state
   └→ Game variables, objects, depth, sectors, screenshot
2. UPDATE QA cells
   └→ 256-unit grid tracking for coverage metrics
3. PROJECT CANONICAL PAYLOAD
   └→ Compact state + static analysis + cross-run memory + coverage
4. REQUEST GEMINI ACTION
   └→ Render prompt → call Gemini decide() → parse JSON
5. PERSIST DECISION SOURCE
   └→ AgentDecision record (decision_source = llm/deterministic_fallback/guard)
6. VALIDATE & NORMALIZE
   └→ Guard system: clamp params, filter invalid actions, detect loops
7. EXECUTE MCP TOOL
   └→ take_action / aim_and_shoot / move_to / explore / etc.
8. PERSIST OUTCOME
   └→ GameEvent with tick, state diff, action taken
9. BROADCAST
   └→ WebSocket: frame, state, decision, progress, defect
10. CHECK TERMINALS
    └→ Tick exhaustion, no-progress stall, cancellation, death, PWAD crash
```

### Iteration Rate

A full lockstep iteration (steps 1-10) takes approximately 2-6 seconds:
- MCP get_state: ~100-500ms
- Prompt rendering: <10ms
- Gemini API call: 1-4s (with throttling)
- MCP tool execution: 1-5 game tics (~35ms each)
- Persistence: ~50ms
- WebSocket broadcast: ~10ms

## MCP Boundary

A key architectural decision: **the Backend never talks to ViZDoom directly**. All game interaction is through MCP tools:

```
Backend ──SSE──► FastMCP ──► GameManager ──► ViZDoom ──► Doom Engine
```

This provides:
- Clean separation of concerns
- Network-transparent game interface
- Tool-level abstraction (compound actions like `aim_and_shoot`)
- Independent testability (mock MCP server)

## Prompt Contract

The LLM receives a compact, dynamic JSON payload each iteration:

```json
{
  "state": { "health": 100, "armor": 50, "ammo": 20, "weapon": 1, ... },
  "objects": [ { "name": "ShotgunGuy", "distance": 128, "health": 30, ... } ],
  "threats": [ { "name": "Demon", "distance": 200, "priority": 5, ... } ],
  "navigation": { "explored": 45, "total": 500, "pct": 9, "suggested": "north" },
  "memory": { "recent_actions": [...], "hypotheses": [...] },
  "coverage": { "visited": 45, "total": 500 },
  "tactical": { "situation": "exploring", "directives": [...] }
}
```

The LLM responds with:
```json
{
  "tool": "explore",
  "params": { "max_tics": 30, "stop_on_enemy": true },
  "reasoning": "Exploring northeast passage, no immediate threats",
  "observed_issues": []
}
```

## Evidence & Report Philosophy

- **Raw decision inputs persisted** — full LLM input, output, MCP input, MCP output for every decision
- **Sentinel rows** (`is_sentinel=True`) excluded from public API queries but kept for internal analysis
- **Cross-run memory** allows accumulating knowledge about a WAD/map across multiple runs
- **Reviewer analytics** (spatial memory, hypotheses, patterns) remain queryable but are NOT injected into future LLM prompts by default
- **PDF reports** combine LLM-generated narrative with computed metrics and defect evidence

## Thread Safety

- **Database**: async SQLAlchemy sessions (no thread sharing)
- **MCP**: Single game instance, sequential tool calls (no concurrent game access)
- **Executor**: GameManager's AutonomousExecutor runs on a daemon thread; paused during synchronous compound actions
- **Process-local**: `RUN_TASKS` dict in process memory — no cross-process coordination
- **Advisory lock**: PostgreSQL `pg_try_advisory_lock()` prevents concurrent runs at DB level

## Director Mode

An experimental "Director mode" exists (`executor.py` + `run_service_director_experimental.py`) but is **not** the active runtime path. The product uses lockstep (LLM decides every action). Director mode delegates continuous gameplay to the AutonomousExecutor and only consults the LLM for high-level strategy changes.
