# Frontend Testing

## Vitest Unit Tests

Run: `npm test -- --run` or `bun run test`

### Component Tests: `components/__tests__/`

#### `MapCanvas.test.tsx` (130 lines, 9 tests)

| Test | Coverage |
|------|----------|
| Renders map image when available | Image element with correct src/alt |
| Shows grid background without image | Grid pattern visible |
| Renders trail dots | 3 circles with rgba fill color |
| Renders visited coverage cells | Semi-transparent green rects from comma-delimited keys |
| Renders event markers | Red=kill, green=item_pickup, black=death |
| Renders live position indicator | Cyan circle |
| Projects trail against map bounds | Coordinates scale correctly |
| Keyboard navigation | Has tabindex and role attributes |
| Contain fit mode | Squares to smallest dimension (ResizeObserver mock) |

#### `SkillHeatmap.test.tsx` (50 lines, 4 tests)

| Test | Coverage |
|------|----------|
| Renders 5 cells with correct counts | Per-skill enemy numbers |
| Shows loading skeleton | Animated pulse when no summary |
| Handles empty summary | Displays zeros gracefully |

#### `StatBar.test.tsx` (48 lines, 5 tests)

| Test | Coverage |
|------|----------|
| All labels present | HP, Armor, Ammo, Kills, Secrets, Tick rendered |
| Correct values | Via aria-labels |
| Total ammo computation | Sum of bullets+shells+rockets+cells |
| Null/missing defaults | 0 for undefined values |
| Partial ammo object | Handles missing ammo types |

### Hook Tests: `hooks/__tests__/`

#### `useRunStream.test.tsx` (199 lines, 7 tests)

| Test | Coverage |
|------|----------|
| Connects to correct WebSocket URL | `ws://localhost:8000/v1/ws/runs/abc-123` |
| Loads snapshot and connects | Fetches REST snapshot before WS open |
| Dedupes token totals | Replayed decisions merged by sequence |
| Invalid JSON handling | Error message without throwing |
| Visited cells from decision payload | Cell strings correctly read |
| Decisions array truncation | Capped at 500 entries |

### Test Infrastructure

- **Runner**: Vitest v4 with jsdom environment
- **Setup**: `vitest.setup.ts` imports jest-dom matchers, registers `afterEach(cleanup)`
- **Path alias**: `@/` resolves to frontend root (configured in vitest.config.ts)
- **Mock strategy**: Custom `MockWebSocket` class, stubbed `global.fetch` and `global.WebSocket`

## Playwright E2E Tests

Run: `npm run test:e2e` or `bun run test:e2e`

### `e2e/live-map.spec.ts` (147 lines, 1 test)

- **Setup**: Mock WebSocket via `page.addInitScript`, mock API routes via `page.route`
- **Test**: "live map is fully contained on first paint and after resize"
  - Verifies map canvas frame is square within viewport at 1280x800
  - Verifies responsive behavior at 390x760 (mobile viewport)

### Configuration (`playwright.config.ts`)

- Default URL: `http://127.0.0.1:3100`
- Auto-starts dev server (configurable via `PLAYWRIGHT_WEB_SERVER_COMMAND`)
- Desktop Chrome viewport, traces retained on failure
- 30s test timeout, 120s server startup

## Linting

Run: `npm run lint` or `bun run lint`

ESLint v9 flat config using `eslint-config-next/core-web-vitals` + `eslint-config-next/typescript`. Ignores `.next/`, `out/`, `build/`, `next-env.d.ts`.
