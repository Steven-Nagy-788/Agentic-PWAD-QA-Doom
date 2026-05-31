# Architecture

## Scope

Agentic PWAD QA Doom is a localhost-only proof of concept. It has no
authentication, tenant isolation, or multi-user ownership model. One run may be
active at a time because MCP-Doom owns a single ViZDoom episode.

## Services

| Service | Responsibility |
| --- | --- |
| `frontend/` | Next.js dashboard, upload flow, live run UI, reports, recordings |
| `Backend/` | FastAPI API, lockstep orchestration, evidence persistence, reports |
| `mcp-doom/` | FastMCP boundary around ViZDoom |
| PostgreSQL | WAD metadata, run evidence, reviewer analytics |

The backend never imports or controls ViZDoom directly. It invokes MCP tools
through `McpClientService`.

## Lockstep Runtime

The active runtime is the lockstep loop in `Backend/app/services/run_loop.py`:

1. Read factual game state through MCP.
2. Project a canonical current-state payload and bounded same-run action ledger.
3. Ask Gemini for one tool call, or use an explicitly labeled deterministic
   fallback if Gemini remains unavailable after retries.
4. Validate and normalize technical tool parameters.
5. Execute valid actions unchanged through MCP. Reject malformed actions with
   `invalid_params`; do not silently invent another gameplay action.
6. Persist the decision, factual MCP tic, action result, decision source, and
   telemetry.
7. Stop terminal episodes and prolonged no-progress runs.

Repeated factual game tics are valid for read-only and rejected decisions.
Decision sequence and database IDs provide ordering where tics match.

## Prompt Contract

The model receives a compact dynamic payload:

```json
{
  "game_tic": 0,
  "ticks_remaining": 0,
  "player": {},
  "weapon_state": {},
  "scene_objects": [],
  "threat_summary": {},
  "navigation": {},
  "coverage": {},
  "same_run_memory": {
    "older_milestones": {},
    "recent_actions": [],
    "aggregates": {},
    "budget": {}
  }
}
```

Same-run memory retains the latest detailed actions and deterministic summaries
of older actions within a configured character budget. Prior-run analytics are
not injected into gameplay prompts.

## Evidence And Reports

Raw decision inputs and MCP outputs remain persisted for auditability. Public
trail and report queries exclude sentinel telemetry rows. Reports derive factual
environment metadata and decision-source counts from stored evidence.

Reviewer-only analytics remain available by WAD and map: prior outcome counts,
spatial cells, persistent hypotheses, and recurring defects.

## MCP Executor

MCP-Doom retains its standalone async executor for direct MCP use. The backend
does not use the retired experimental Director adapter.
