# UI Components

All components are located in `frontend/components/` or `frontend/lib/components/`.

---

## 1. Shell (`app/shell.tsx`)

Application chrome that wraps every page. Renders a `NavBar` sidebar alongside page content in a CSS grid layout (`236px sidebar + 1fr content`). Uses `useSyncExternalStore` to detect client hydration and show a skeleton loading state (`AppLoadingShell`) during SSR to prevent layout shift.

**Accessibility:** Includes a skip-to-main-content link (`#main-content`).

### NavBar (`lib/components/shared.tsx`)

Sidebar with five navigation items. Active route is determined by `usePathname()`:

| Icon | Label | Active Match |
|------|-------|-------------|
| `FileArchive` | WADs | `/` or `/wad/*` |
| `History` | Runs | `/history` or `/run/*` |
| `HeartPulse` | Health | `/health/*` |
| `Cog` | Settings | `/settings/*` |
| `BookOpen` | Docs | `/docs/*` |

Responsive: `grid-cols-3` on mobile, `grid-cols-1` on `md:` and above.

---

## 2. MapCanvas (`components/MapCanvas.tsx`)

SVG-based interactive Doom map display.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `map` | `WadMap \| null \| undefined` | Map metadata for background image + bounds |
| `trail` | `PositionSample[]` | Player position trail dots + polyline |
| `events` | `TraceEntry[]` | Event markers (kill, death, item_pickup, secret_found) |
| `livePosition` | `{ x, y } \| null` | Current live position cursor |
| `className` | `string` | Additional CSS classes |

**Rendering:**
1. Background: map overview PNG (if available) or a CSS grid pattern fallback
2. Trail polyline (blue, `#2563eb`, 7px stroke, 78% opacity)
3. Trail dots (semi-transparent blue circles, r=5)
4. Start marker (green, r=11) and end marker (amber, r=12)
5. Event circles: red for kill, green for item_pickup, amber for other; death events render as an X
6. Live position marker (cyan, r=13, white stroke)
7. Focus ring (white + cyan concentric circles) for keyboard navigation

**Keyboard Navigation:** Arrow keys pan a focus circle by 15px increments within the 1024×1024 viewport. The SVG is `tabIndex={0}` with `role="application"`.

**Coordinate Projection:** `project()` maps game coordinates (map bounds from metadata or computed from point data) to the 1024×1024 SVG viewport with 20px margins, Y-axis inverted.

---

## 3. DecisionTimeline (`components/DecisionTimeline.tsx`)

Expandable historical LLM decision trace for completed runs.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `decisions` | `Decision[]` | Array of completed decisions |

Uses `<details>` / `<summary>` elements for native expand/collapse. Each entry shows:

- **Summary:** `#sequence tool_name`, tick range, stop reason/status
- **Metrics row:** LLM duration (ms), MCP duration (ms), input→output tokens, cost (USD)
- **Expanded:** Full reasoning text, latency breakdown, token counts, MCP input/output JSON (with scrollable `<pre>` blocks)

Max height of scroll container: 540px.

---

## 4. ReasoningLog (`components/ReasoningLog.tsx`)

Real-time or historical LLM reasoning feed with guard badges.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `decisions` | `LiveDecision[]` | Array of live decisions (from `useRunStream`) |
| `live` | `boolean` | If true, auto-scrolls to latest decision |

### GuardBadge

Inline component rendered inside each decision card:

| Status | Color Scheme |
|--------|-------------|
| `kept` | Green (`bg-green-100`, `text-green-800`, `border-green-300`) |
| `modified` | Yellow (`bg-yellow-100`, `text-yellow-800`, `border-yellow-300`) |
| `blocked` | Red (`bg-red-100`, `text-red-800`, `border-red-300`) |

### DecisionCard

Each card displays:
- Sequence number, guard badge, tool name (with tick number)
- Reasoning text
- Expandable "Show details" section with LLM latency, MCP latency, input/output tokens, cost, stop reason, MCP input/output JSON, LLM input/output JSON

When `live` is true, the latest decision is `defaultExpanded` and auto-scrolls into view.

---

## 5. StatBar (`components/StatBar.tsx`)

Live or completed game state display.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `state` | `StatBarState \| null \| undefined` | Current game state |

| Stat | Icon | Field |
|------|------|-------|
| HP | `Activity` | `health` |
| Armor | `Shield` | `armor` |
| Ammo | `Zap` | Sum of bullets + shells + rockets + cells |
| Kills | `Crosshair` | `kills` |
| Secrets | `Gauge` | `secrets` |
| Tick | `Gauge` | `tick` |

Each stat rendered as a bordered cell with uppercase label and bold value. Grid: `grid-cols-3` mobile, `md:grid-cols-6`.

---

## 6. DefectBadge (`components/DefectBadge.tsx`)

Color-coded defect count badge.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `count` | `number` | Defect count |
| `pulse` | `boolean` | Enable CSS `animate-pulse` |

| Count Range | Tone |
|-------------|------|
| 0 | Emerald (green) — `border-emerald-200 bg-emerald-50 text-emerald-800` |
| 1–2 | Amber (yellow) — `border-amber-200 bg-amber-50 text-amber-900` |
| ≥3 | Red — `border-red-200 bg-red-50 text-red-900` |

Renders with `AlertTriangle` icon from lucide-react. `aria-label` announces count for screen readers.

---

## 7. SkillHeatmap (`components/SkillHeatmap.tsx`)

Horizontal heatmap showing enemy counts per difficulty level (1–5).

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `summary` | `Record<string, SkillSummary> \| null \| undefined` | Spawn summary keyed by skill level |

Renders a 5-column grid. Each column shows the skill number and enemy count, with a background color intensity proportional to `enemies / max_enemies`. Color transitions from near-white (few enemies) to a blue-tinted shade:

```ts
heatColor(value) = rgb(245 - v*15, 247 - v*120, 238 - v*165)
```

When `summary` is null, renders a skeleton placeholder with `animate-pulse`.

---

## 8. ErrorBoundary (`components/ErrorBoundary.tsx`)

React class-based error boundary with fallback UI.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `children` | `ReactNode` | Child tree to guard |
| `fallback` | `ReactNode` | Optional custom fallback UI |

Default fallback: centered red card with error message and "Try again" button that resets `hasError` state. Logs to `console.error` with component stack via `componentDidCatch`.

---

## 9. HealthSparkline (`lib/components/HealthSparkline.tsx`)

Inline SVG sparkline of health points over time.

**Props:**

| Prop | Type | Description |
|------|------|-------------|
| `runId` | `string` | Run ID to fetch position trail |
| `fallback` | `number` | Fallback HP value if no trail data |

Fetches `/runs/{runId}/position-trail`, takes the last 80 samples, and renders a 128×36 SVG line chart with a cyan (`#0891b2`) stroke on a light gray baseline.

---

## 10. Shared Utility Components (`lib/components/shared.tsx`)

| Component | Props | Description |
|-----------|-------|-------------|
| `NavBar` | (none) | Sidebar navigation (see Shell above) |
| `Metric` | `{ label: string, value: string \| number }` | Bordered stat card with uppercase label |
| `OutcomeBadge` | `{ outcome?: string \| null }` | Color-coded run outcome badge (emerald = ok/completed, red = error/crash, amber = other) |
| `InlineError` | `{ message: string }` | Red error banner |
| `EmptyState` | `{ title: string }` | Centered empty state placeholder (50vh min-height) |
| `SkeletonRows` | (none) | Three animated pulse skeleton rows |
| `errorMessage` | `(error: unknown) => string \| undefined` | Extracts `.message` from `Error` instances |
| `formatBytes` | `(value: number) => string` | Human-readable byte sizes (B, KB, MB) |
| `formatTime` | `(ts: number) => string` | Relative time ("just now", "5s ago", "2m ago") |
