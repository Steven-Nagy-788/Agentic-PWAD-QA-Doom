# Agentic PWAD QA Doom — Frontend

Next.js 16 dashboard for launching, monitoring, and reviewing autonomous Doom WAD QA runs.

## Tech Stack

| Layer | Library |
|-------|---------|
| Framework | Next.js 16.2.6 (App Router) |
| UI Library | React 19.2.4 |
| Language | TypeScript 5 |
| Styling | Tailwind CSS v4 (PostCSS via `@tailwindcss/postcss`) |
| Data Fetching | `@tanstack/react-query` ^5.100.11 |
| Icons | `lucide-react` ^1.16.0 |
| Testing | Vitest ^4.1.7, `@testing-library/react` ^16.3.2, Playwright |
| Package Manager | bun |
| Fonts | Geist (Sans + Mono) via `next/font/google` |

## Page Routing

```
┌─────────────────────────────────────────────────────────────────┐
│                      Root Layout (layout.tsx)                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Providers (QueryClient)                                 │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │  Shell (sidebar nav + skip-link)                   │  │   │
│  │  │  ┌──────────────────────────────────────────────┐  │  │   │
│  │  │  │  <children />                                │  │  │   │
│  │  │  └──────────────────────────────────────────────┘  │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

                    Navigation Tree
                    ═══════════════

                         ┌──────────┐
                         │  / (WAD  │
                         │ Library) │
                         └────┬─────┘
                              │
                    ┌─────────▼─────────┐
                    │ /wad/[id]         │
                    │ (WAD Detail +     │
                    │  Run Launcher)    │
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼──────┐  ┌────▼─────┐  ┌──────▼───────┐
     │ /run/[id]     │  │ /history │  │ /health      │
     │ (Run Detail / │  │ (Run     │  │ (Health      │
     │  Live Run)    │  │ History) │  │ Dashboard)   │
     └───────────────┘  └──────────┘  └──────────────┘

     ┌──────────┐      ┌──────────┐
     │ /settings │      │ /docs    │
     │ (Settings)│      │ (Docs)   │
     └──────────┘      └──────────┘
```

## Key Features

- **Live WebSocket Streaming** — Real-time game frames, state updates, LLM decisions, and defect detection streamed directly to the browser during a run.
- **Interactive Map Canvas** — SVG-based Doom map overlay with player position trail, event markers (kills, deaths, item pickups), and keyboard-navigable focus ring.
- **Real-time Stats** — Live HP, armor, ammo, kills, secrets, and tick counter updated via WebSocket.
- **LLM Decision Timeline** — Expandable trace of every LLM decision with latency, token counts, cost estimates, and raw MCP input/output.
- **Defect Detection** — Color-coded defect badges (green/amber/red) with severity and description.
- **Skill Heatmaps** — Horizontal bar showing enemy counts per difficulty level (1–5) for each map.
- **Run Recording & PDF Reports** — MP4 recording playback and downloadable PDF report per run.
- **Responsive Sidebar** — Collapsible navigation with active route highlighting, mobile-friendly grid layout.

## Build Proxy

Defined in `next.config.ts` — all `/api/*` requests are rewritten to the backend at `http://localhost:8000`:

- `/api/:path*` → `http://localhost:8000/:path*`
- `/api/v1/ws/:path*` → `http://localhost:8000/v1/ws/:path*`

This eliminates CORS issues in development and keeps the API base URL clean.

## Developer Commands

```bash
bun dev          # Start Next.js dev server (port 3000)
bun build        # Production build
bun start        # Start production server
bun lint         # ESLint
bun test         # Vitest run
bun test:watch   # Vitest watch mode
```

## Project Structure

```
frontend/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx          # Root layout (Providers + Shell)
│   ├── providers.tsx       # QueryClient provider
│   ├── shell.tsx           # Sidebar navigation chrome (client)
│   ├── page.tsx            # WAD Library (/)
│   ├── wad/[id]/page.tsx   # WAD Detail + Run Launcher
│   ├── run/[id]/page.tsx   # Run Detail / Live Run
│   ├── history/page.tsx    # Run History
│   ├── health/page.tsx     # Health Dashboard
│   ├── settings/page.tsx   # Settings
│   └── docs/page.tsx       # Documentation portal
├── components/             # Shared React components
│   ├── MapCanvas.tsx       # SVG map with trail + events
│   ├── DecisionTimeline.tsx # Historical decision trace
│   ├── ReasoningLog.tsx    # Real-time LLM reasoning feed
│   ├── StatBar.tsx         # Live game stat bar
│   ├── DefectBadge.tsx     # Color-coded defect count
│   ├── SkillHeatmap.tsx    # Enemy count per difficulty
│   ├── ErrorBoundary.tsx   # Class-based error boundary
│   └── __tests__/          # Component tests
├── hooks/
│   ├── useRunStream.ts     # WebSocket hook with reconnection
│   └── __tests__/
├── lib/
│   ├── api.ts              # API client + TypeScript types
│   └── components/
│       ├── shared.tsx      # NavBar, Metric, OutcomeBadge, etc.
│       └── HealthSparkline.tsx  # Inline HP sparkline SVG
└── vitest.config.ts
```
