# Frontend

Next.js App Router UI for Agentic PWAD QA.

## Responsibilities

- Upload PWAD files.
- Show WAD analysis and detected maps.
- Start/cancel runs with map, difficulty, run length, and behavior profile controls.
- Stream live run state over WebSocket.
- Show decisions, events, position trail, defects, usage, latency, recordings, and generated reports.
- Edit runtime settings exposed by the backend.

## Setup

Requires Node.js 22 or newer with npm, or Bun.

```bash
cd frontend
npm install
npm run dev
```

Or:

```bash
cd frontend
bun install
bun dev
```

Open `http://localhost:3000`.

## Backend Connection

The API client defaults to:

```ts
NEXT_PUBLIC_API_BASE ?? "/api/v1"
```

`next.config.ts` rewrites `/api/*` to `http://localhost:8000/*`, so local REST calls expect the backend at `http://localhost:8000`.

To bypass the rewrite, set:

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000/v1 npm run dev
```

Live run WebSockets use `NEXT_PUBLIC_WS_BASE` when set. In local development and local `next start`, the client automatically maps `localhost:3000` or `localhost:3001` to `ws://localhost:8000/v1/ws/runs/{run_id}` because Next's production server is not a reliable backend WebSocket proxy.

For a deployed reverse proxy, set:

```bash
NEXT_PUBLIC_API_BASE=/api/v1
NEXT_PUBLIC_WS_BASE=https://backend.example.com/v1
```

## Useful Commands

```bash
npm test -- --run
npm run lint
npm run build
PLAYWRIGHT_WEB_SERVER_COMMAND="npm run start -- --hostname 127.0.0.1 --port 3100" npm run test:e2e
```

```bash
bun run test
bun run lint
bun run build
PLAYWRIGHT_WEB_SERVER_COMMAND="bun run start --hostname 127.0.0.1 --port 3100" bun run test:e2e
```

## Main Screens

- `/` - WAD list, upload, recent runs.
- `/wad/[id]` - map list, static analysis, run creation.
- `/run/[id]` - run monitor, metrics, decisions, trace, defects, recording, report links.
- `/settings` - model, rate, cost, run, recording, and behavior defaults.

## Notes

This frontend is an operational dashboard, not a marketing page. Keep new UI dense, scannable, and tied to the QA workflow. Avoid hiding critical run state behind decorative layouts.
