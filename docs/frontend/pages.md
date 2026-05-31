# Pages & Data Flow

All pages are `"use client"` components using `@tanstack/react-query` for data fetching and `next/navigation` for routing.

---

## 1. WAD Library (`/` — `app/page.tsx`)

Lists all uploaded WAD files as a responsive card grid (`md:grid-cols-2`, `xl:grid-cols-3`).

**Data Fetching:**
- `GET /api/v1/wads` → `WadFile[]` — query key `["wads"]`
- Each card fetches its thumbnail: `GET /api/v1/wads/{id}/maps` → `WadMap[]` — query key `["wad-thumb", wadId]`

**User Actions:**
- Click a WAD card → `router.push(/wad/${wad.id})`
- Upload a new WAD via `UploadZone` (drag-and-drop or file picker, `.wad` only) → `POST /api/v1/wads/upload` (FormData). On success: invalidates `["wads"]` query, navigates to `/wad/{newId}`.

**Components:** `Metric`, `SkeletonRows`, `InlineError`, `UploadZone` (inline)

---

## 2. WAD Detail + Run Launcher (`/wad/[id]` — `app/wad/[id]/page.tsx`)

Two-column layout: left panel shows maps, right panel (sticky sidebar) is the run launcher.

**Data Fetching:**
- `GET /api/v1/wads/{id}` → `WadFile` — query key `["wad", id]`
- `GET /api/v1/wads/{id}/maps` → `WadMap[]` — query key `["wad-maps", id]`
- `GET /api/v1/settings/behavior-profiles` → `Record<string, BehaviorProfile>` — query key `["behavior-profiles"]`

**Run Launcher Controls:**
| Control | State | Description |
|---------|-------|-------------|
| Map selector | `selectedMap` | Click a map card to select; cyan border highlights active |
| Difficulty | `difficulty` | 5-button row (1–5), default 3 |
| Max ticks | `maxTicks` | Range slider (500–35,000, step 500), default 3,000 |
| Behavior profile | `behaviorProfile` | Dropdown from profiles API, fallback hardcoded options |
| Launch button | `startRun` | Disabled until a map is selected; shows "Launching" while pending |

**Launch:**
- `POST /api/v1/runs` with body `{ wad_file_id, map_name, difficulty_level, max_ticks, behavior_profile }` → `Run`
- On success: invalidates `["runs"]`, navigates to `/run/{run.id}`

**Components:** `MapCanvas`, `SkillHeatmap`, `Metric`, `SkeletonRows`, `InlineError`

---

## 3. Run Detail (`/run/[id]` — `app/run/[id]/page.tsx`)

Two modes based on `run.status`:

### Live Mode (`running` or `pending`)

```
┌─────────────────────────────────────────────────────────┐
│  RunPage                                                 │
│  ┌─────────────── run.status ────────────────────────┐  │
│  │  running/pending → LiveRunContent                  │  │
│  │  completed/failed → RunDetailContent               │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**LiveRunContent** renders a full-height split layout:
- Left: game frame (base64 image from WebSocket) with connection status bar, token totals, defect badge, and cancel button
- Right: `ReasoningLog` (auto-scrolling live feed)
- Bottom: `StatBar` with live state

### Detail Mode (`completed`, `failed`, etc.)

**Data Fetching (9 parallel queries):**

| Query Key | Endpoint | Data | Polling |
|-----------|----------|------|---------|
| `["run", runId]` | `GET /runs/{id}` | `Run` | 5s |
| `["run-defects", runId]` | `GET /runs/{id}/defects` | `Defect[]` | — |
| `["run-decisions", runId]` | `GET /runs/{id}/decisions?page_size=500` | `Decision[]` | — |
| `["run-trail", runId]` | `GET /runs/{id}/position-trail` | `PositionSample[]` | — |
| `["run-events", runId]` | `GET /runs/{id}/events?type=kill,death,...` | `TraceEntry[]` | — |
| `["run-usage", runId]` | `GET /runs/{id}/usage` | `UsageStats` | — |
| `["run-benchmark", runId]` | `GET /runs/{id}/benchmark` | `BenchmarkStats` | — |
| `["run-report-status", runId]` | `GET /runs/{id}/report/status` | `ReportStatus` | 3s |
| `["run-maps", wadFileId]` | `GET /wads/{wadFileId}/maps` | `WadMap[]` | — (enabled once `run.data?.wad_file_id` is available) |

**Sections (top to bottom):**

1. **Header** — Map name, run ID, behavior profile, outcome badge, "Live" button to re-enter live mode
2. **Map + Metrics** — `MapCanvas` with trail + events, 6 key metrics (Duration, Actions, Final HP, Kills, Secrets, Defects)
3. **Token Usage** — LLM calls, prompt/completion/total tokens, cost, avg cost/decision, model
4. **Performance Benchmark** — LLM latency (avg, p50, p95, min, max, count), MCP latency, tools used breakdown
5. **Defects** — List with title, severity, description
6. **Decision Trace + Recording** — Two-column: `DecisionTimeline` (left) and MP4 video with PDF report download (right); recording URL is `${API_BASE}/runs/${runId}/recording`

---

## 4. Run History (`/history` — `app/history/page.tsx`)

Filterable, paginated table of past runs.

**Data Fetching:**
- `GET /api/v1/wads` → `WadFile[]` (for WAD name filter)
- `GET /api/v1/runs?limit=20&offset={n}&map_name=&outcome=&difficulty_level=&created_after=&created_before=` → `RunList`
- Auto-refetches every 10 seconds (`refetchInterval: 10_000`)

**Filters (6 inputs in a grid):**
- WAD name (client-side filter by wad_file_id matching filename)
- Map name, Outcome, Difficulty (server-side URL params)
- After / Before (date pickers, converted to ISO strings)

**Pagination:** Previous/Next buttons, range display ("Showing 1–20 of 150 runs").

**Table columns:** Map (clickable link), Outcome (badge), Difficulty, HP (sparkline), Created (date).

**Components:** `HealthSparkline`, `OutcomeBadge`

---

## 5. Health Dashboard (`/health` — `app/health/page.tsx`)

System health checks with auto-refresh every 10 seconds.

**Data Fetching (4 parallel, all polled at 10s):**
- `GET /{api_root}/health` → API status
- `GET /{api_root}/health/gemini` → Gemini LLM status
- `GET /{api_root}/health/mcp` → MCP Doom server status
- `GET /api/v1/admin/storage/stats` → Storage stats (raw JSON)

**Display:** Three health cards (API, Gemini, MCP) showing status badge + JSON data, plus a `<pre>` block with storage stats.

**Components:** `OutcomeBadge`

---

## 6. Settings (`/settings` — `app/settings/page.tsx`)

View and edit application settings, view behavior profiles.

**Data Fetching:**
- `GET /api/v1/settings` → `AppSettings`
- `GET /api/v1/settings/behavior-profiles` → `Record<string, BehaviorProfile>`

**Edit Mode:** Toggle with "Edit"/"Save"/"Cancel" buttons. Editable fields are rendered as `<input>` elements in place of read-only text. Uses `PATCH /api/v1/settings` to persist changes.

**Settings Cards (4 columns):**

| Card | Fields |
|------|--------|
| LLM Config | Model, Throttle (s), Rate limit, Input $/1M, Output $/1M |
| Run Config | Default ticks, Max ticks, Default behavior |
| Recording Config | Live FPS, Recording FPS, Telemetry stride |
| General | App name, Environment, IWAD (read-only except IWAD) |

**Behavior Profiles:** Grid of profile cards showing name, description, and throttle values. Recording stride is configured independently.

---

## 7. Docs (`/docs` — `app/docs/page.tsx`)

Interactive documentation with accordion sections.

Each `DocSection` is a bordered card with a toggle button. Only one section open at a time (controlled by `openSection` state).

**Sections:**
- **Getting Started** — 5-step guide to use the system
- **API Reference** — Full endpoint table with method, path, description; uses `API_BASE` for the prefix
- **Architecture** — Component overview with ASCII diagram
- **Behavior Profiles** — Thorough, Fast, Exploit-focused profile cards

**Components:** `DocSection`, `ApiEndpoint`, `DocProfileCard` (all inline)

---

## 8. useRunStream Hook (`hooks/useRunStream.ts`)

WebSocket management hook for live run monitoring.

```
RunStreamMessage types dispatched by WebSocket
══════════════════════════════════════════════

    ┌──────────┐
    │  frame   │ → Sets live frame base64 image (deduplicated by lastFrameRef)
    ├──────────┤
    │  state   │ → Updates live stat bar (health, armor, kills, secrets, ammo, tick)
    ├──────────┤
    │ llm_     │ → Adds LiveDecision to decisions array
    │ decision │   Accumulates token/cost totals
    ├──────────┤
    │ mcp_call │ → Patches the matching pending decision with
    │ _result  │   MCP output, stop reason, decision source, duration
    ├──────────┤
    │  defect  │ → Appends Defect to defects array (max 200)
    ├──────────┤
    │  ping    │ → Responds with pong (keep-alive)
    └──────────┘
```

**Return values:**

| Property | Type | Description |
|----------|------|-------------|
| `connected` | `boolean` | WebSocket open state |
| `retryCount` | `number` | Current reconnection attempt |
| `retryDelay` | `number` | Current reconnection delay (ms) |
| `lastMessageAt` | `number` | Timestamp of last received message |
| `messages` | `RunStreamMessage[]` | Raw message log (last 250) |
| `frame` | `string \| null` | Base64 data URL of latest game frame |
| `state` | `RunStreamMessage \| null` | Latest state message payload |
| `decisions` | `LiveDecision[]` | Accumulated live decisions (last 500) |
| `defects` | `Defect[]` | Accumulated defects (last 200) |
| `tokenTotals` | `SessionTokenTotals` | Running totals: prompt, completion, total tokens, cost, decision count |

**Reconnection:** Exponential backoff starting at 1s, doubling with each attempt, capped at 30s. Tracks `retryCount` and `retryDelay` for UI display.

**Cleanup:** On unmount or `runId` change, the effect cancels any pending reconnect timer and closes the socket.

---

## 9. API Client (`lib/api.ts`)

Centralized HTTP client and TypeScript types.

**Types:** `WadFile`, `WadMap`, `SkillSummary`, `Run`, `RunList`, `TraceEntry`, `Decision`, `Defect`, `PositionSample`, `AppSettings`, `UsageStats`, `LatencyStats`, `BenchmarkStats`, `ReportStatus`, `BehaviorProfile`

**Client functions:**

| Function | Description |
|----------|-------------|
| `apiGet<T>(path)` | GET request via `API_BASE` prefix, `cache: "no-store"` |
| `apiRootGet<T>(path)` | GET request via `API_ROOT` (base path without `/v1`) |
| `apiSend<T>(path, init)` | Generic fetch with full `RequestInit` control, handles 204 No Content |
| `uploadWad(file)` | Creates `FormData`, POSTs to `/wads/upload` |
| `assetUrl(path)` | Resolves relative asset paths against `API_BASE`, passes through absolute URLs |
| `websocketUrl(runId)` | Builds WebSocket URL resolving through the same proxy logic as API calls |

**WebSocket URL resolution:** The `websocketBaseUrl()` function handles three scenarios:
1. Explicit `WS_BASE` env var
2. `API_BASE` starting with `http` — converts protocol to `ws:`/`wss:`
3. Relative `API_BASE` (`/api/v1`) with local frontend origin — rewrites port to 8000 and strips `/api` prefix to hit the backend directly

---

## Data Flow Diagrams

### Live Run WebSocket Data Flow

```mermaid
sequenceDiagram
    participant Browser as Frontend (React)
    participant WS as WebSocket (/api/v1/ws/runs/{id})
    participant API as FastAPI Backend
    participant MCP as MCP-Doom Server
    participant LLM as Gemini LLM

    rect rgb(240, 248, 255)
        Note over Browser,LLM: Run is pending/running — Live Mode
    end

    Browser->>WS: Connect (websocketUrl)
    WS-->>Browser: onopen → connected=true

    loop Every game tick
        MCP->>API: Game state + frame
        API->>WS: frame { frame_b64, mime_type }
        WS-->>Browser: onmessage → setFrame()
        API->>WS: state { health, armor, kills, ammo, tick }
        WS-->>Browser: onmessage → setState()
    end

    loop LLM Decision Cycle
        Note over API,LLM: Agent triggers LLM call
        API->>LLM: Send game context
        LLM-->>API: Reasoning + action
        API->>WS: llm_decision { reasoning, tool, tokens, cost }
        WS-->>Browser: onmessage → append decision, update token totals
        API->>MCP: Execute action via MCP tool
        MCP-->>API: Tool result
        API->>WS: mcp_call_result { output, stop_reason, decision_source, validation_rejection }
        WS-->>Browser: onmessage → patch decision with MCP output
    end

    alt Defect Detected
        API->>WS: defect { type, title, severity, tick }
        WS-->>Browser: onmessage → append defect
    end

    rect rgb(255, 245, 238)
        Note over Browser,LLM: Disconnect / Error
    end

    WS-->>Browser: onclose → connected=false
    Browser->>Browser: Exponential backoff reconnect (1s → 2s → 4s → ... → 30s max)
    Browser->>WS: Reconnect
    WS-->>Browser: onopen → connected=true, retryCount=0
```

### Page Navigation Flow

```mermaid
sequenceDiagram
    participant User as User
    participant React as Next.js Client
    participant API as Backend API
    participant WS as WebSocket

    Note over User,WS: WAD Library Navigation
    User->>React: Visit /
    React->>API: GET /api/v1/wads
    API-->>React: WadFile[]
    React-->>User: WAD card grid

    User->>React: Click WAD card
    React->>API: GET /api/v1/wads/{id}/maps
    API-->>React: WadMap[]
    React-->>User: Maps + run launcher sidebar

    Note over User,WS: Run Launch → Live View
    User->>React: Configure difficulty, ticks, behavior
    User->>React: Click "Launch"
    React->>API: POST /api/v1/runs { wad_file_id, map_name, ... }
    API-->>React: Run { id, status: "pending" }
    React->>WS: Connect WebSocket /api/v1/ws/runs/{id}
    WS-->>React: onopen → render LiveRunContent
    loop Live updates
        WS-->>React: frame, state, llm_decision, mcp_call_result, defect
        React-->>User: Game frame, stats, reasoning log, defects
    end

    Note over User,WS: Run Complete → Detail View
    WS-->>React: onclose (run finished)
    React->>API: GET /api/v1/runs/{id} (status: "completed")
    React->>API: GET /api/v1/runs/{id}/decisions, /position-trail, /usage, /benchmark, /defects
    API-->>React: All detail data
    React-->>User: Map with trail, metrics, token usage, benchmarks, defects, recording

    Note over User,WS: History Navigation
    User->>React: Visit /history
    React->>API: GET /api/v1/runs?limit=20&offset=0
    API-->>React: RunList
    User->>React: Apply filters (WAD, map, outcome, dates)
    React->>API: GET /api/v1/runs?limit=20&offset=0&map_name=...&outcome=...
    API-->>React: Filtered RunList
    User->>React: Click map name → /run/{id}
    React-->>User: Navigate to Run Detail

    Note over User,WS: Health / Settings / Docs
    User->>React: Visit /health
    React->>API: GET /api/v1/health, /health/gemini, /health/mcp, /admin/storage/stats
    API-->>React: Health status objects
    React-->>User: Health cards with auto-refresh

    User->>React: Visit /settings
    React->>API: GET /api/v1/settings, /settings/behavior-profiles
    API-->>React: AppSettings, BehaviorProfiles
    User->>React: Edit fields, click "Save"
    React->>API: PATCH /api/v1/settings { ... }
    API-->>React: Updated AppSettings
    React-->>User: Settings with saved values

    User->>React: Visit /docs
    React-->>User: Accordion documentation
    User->>React: Click section
    React-->>User: Expand/collapse section
```
