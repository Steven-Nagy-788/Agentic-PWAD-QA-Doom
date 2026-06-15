# Hooks and API Client

## `useRunStream` — Live Run WebSocket Hook

Located in `frontend/hooks/useRunStream.ts` (~442 lines). Central hook for live run monitoring.

### Return Value

| Field | Type | Description |
|-------|------|-------------|
| `connected` | boolean | WebSocket connected |
| `retryCount` | number | Current reconnect attempt |
| `retryDelay` | number | Current backoff delay (ms) |
| `lastMessageAt` | number | Timestamp of last message |
| `frame` | string | Base64-encoded game screenshot |
| `state` | RunStreamState | Telemetry (HP, armor, ammo, kills, secrets, pos, angle, tick) |
| `decisions` | LiveDecision[] | LLM decisions (capped at 500) |
| `defects` | Defect[] | Detected defects (capped at 200) |
| `tokenTotals` | SessionTokenTotals | Cumulative prompt/completion tokens + cost |
| `sameRunMemory` | SameRunMemory | Budget, recent actions, milestones, warnings |
| `visitedCells` | string[] | Coverage cell coordinates |
| `visitedCellSize` | number | Cell size in world units |
| `snapshot` | any | Initial REST snapshot |
| `phase` | RunStreamPhase | replay/streaming |
| `error` | string | Error message |

### WebSocket Messages

| Type | Direction | Payload |
|------|-----------|---------|
| `ping` | Server→Client | `{}` (respond with `pong`) |
| `pong` | Client→Server | `{}` |
| `replay_start` | Server→Client | Cached message replay begins |
| `replay_end` | Server→Client | Replay complete, live streaming starts |
| `frame` | Server→Client | `{ type: "frame", data: base64 }` |
| `state` | Server→Client | `{ type: "state", ...telemetry }` |
| `llm_start` | Server→Client | `{ type: "llm_start", sequence }` |
| `llm_decision` | Server→Client | Full decision with visited cells |
| `mcp_call_start` | Server→Client | `{ type: "mcp_call_start", tool, input }` |
| `mcp_call_result` | Server→Client | `{ type: "mcp_call_result", tool, output, duration }` |
| `progress` | Server→Client | Coverage progress metrics |
| `defect` | Server→Client | New defect detected |

### Behavior

- On mount: fetches initial REST snapshot from `/runs/{runId}/live-snapshot`, then opens WebSocket
- Reconnection: exponential backoff (1s, 2s, 4s, 8s, 16s, 30s cap)
- Decision dedup: merges by `sequence_number`
- Defect dedup: by `fingerprint`
- Token tracking: accumulates across all decisions

## API Client — `lib/api.ts` (~325 lines)

### Configuration

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1"
const API_ROOT = process.env.NEXT_PUBLIC_API_BASE ?? "/api"
const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE
```

### TypeScript Types

| Type | Use |
|------|-----|
| `WadFile` | WAD metadata with detected_maps, iwad_required |
| `WadMap` | Map metadata with static analysis summary |
| `SkillSummary` | Per-skill (1-5) enemy spawn counts |
| `Run` | Full run detail with status, outcome, metrics |
| `RunList` | Paginated run summary list |
| `TraceEntry` | Decision trace with MCP fields |
| `Decision` | AgentDecision with LLM/MCP details |
| `Defect` | Defect with severity, type, position |
| `PositionSample` | Trail point (x, y, health, tick) |
| `AppSettings` | All runtime settings |
| `UsageStats` | Token/cost usage |
| `LatencyStats` | LLM/MCP latency percentiles |
| `BenchmarkStats` | Performance benchmarks |
| `ReportStatus` | Report generation status |
| `BehaviorProfile` | Agent behavior profile description |
| `RecurringDefect` | Cross-run defect pattern |
| `MapMemory` | Cross-run memory for a map |

### Functions

| Function | Returns | Description |
|----------|---------|-------------|
| `apiGet<T>(path)` | `Promise<T>` | GET request to `${API_BASE}${path}` |
| `apiRootGet<T>(path)` | `Promise<T>` | GET request to `${API_ROOT}${path}` |
| `apiSend<T>(method, path, body?)` | `Promise<T>` | POST/PUT/PATCH/DELETE |
| `uploadWad(file)` | `Promise<WadFile>` | Multipart upload to `/wads/upload` |
| `assetUrl(path)` | `string` | Resolves relative asset paths |
| `websocketUrl(runId)` | `string` | Builds WS URL with localhost mapping logic |

### WebSocket URL Resolution

```
if WS_BASE is set → use WS_BASE
elif API_BASE is a full URL → derive from API_BASE
else (local dev with /api/ prefix) → map to ws://localhost:8000/v1/ws/runs/{run_id}
```

### Shared Components — `lib/components/shared.tsx` 

| Component | Props | Description |
|-----------|-------|-------------|
| `NavBar` | none | Sidebar navigation with 5 links + icons |
| `Metric` | `{ label, value }` | Key-value display |
| `OutcomeBadge` | `{ outcome }` | Color-coded status badge |
| `InlineError` | `{ message }` | Red error alert |
| `EmptyState` | `{ children }` | Centered placeholder |
| `SkeletonRows` | none | 3-row loading animation |

### HealthSparkline — `lib/components/HealthSparkline.tsx`

Inline SVG sparkline chart for HP over time.
- Accepts batch trail data or single-run data
- Polyline path with min/max normalization
- 64px wide, 24px tall default
