# Agentic PWAD QA for Doom — Documentation Portal

Autonomous QA system that uploads Doom PWAD map files, runs ViZDoom through an MCP server, uses a Gemini LLM to make high-level gameplay decisions in a lockstep loop, records telemetry/video/evidence, detects defects, and generates PDF reports.

## Services

| Service | Directory | Tech | Entrypoint |
|---------|-----------|------|------------|
| Backend | `Backend/` | FastAPI + SQLAlchemy + asyncpg + Alembic + WeasyPrint + Google GenAI | `app/main.py` |
| MCP-Doom | `mcp-doom/` | FastMCP 3.2 + ViZDoom 1.3 | `src/doom_mcp/server.py` |
| Frontend | `frontend/` | Next.js 16 + React 19 + Tailwind v4 + TanStack Query | App Router |

## Documentation Map

### Backend (`docs/backend/`)

| Document | Description |
|----------|-------------|
| [Overview](backend/README.md) | Tech stack, architecture layers, project layout |
| [API Reference](backend/api.md) | All 42 HTTP/WS endpoints with paths and descriptions |
| [Data Model](backend/data-model.md) | 11 core record models and evidence semantics |
| [Full Models](backend/models.md) | All 13 SQLAlchemy ORM models with field types and constraints |
| [Routers](backend/routers.md) | All 10 API routers with endpoint details |
| [Services](backend/services.md) | Services catalog: active runtime, evidence, analytics |
| [Run Lifecycle](backend/run-lifecycle.md) | Lockstep loop: creation, iteration, completion |
| [Defect Detection](backend/defect-detection.md) | 7 post-run detectors, agent-observed defects, fingerprinting |
| [Prompts](backend/prompts.md) | LLM prompt templates: agent system prompt, report generation |
| [Migrations](backend/migrations.md) | Alembic migration history and schema evolution |

### MCP-Doom (`docs/mcp-doom/`)

| Document | Description |
|----------|-------------|
| [Overview](mcp-doom/README.md) | FastMCP + ViZDoom, 20 MCP tools, architecture |
| [Tools Reference](mcp-doom/tools.md) | Complete MCP tools with parameters and return types |
| [Game Manager](mcp-doom/game-manager.md) | GameManager lifecycle, compound actions, campaign mode |
| [Executor](mcp-doom/executor.md) | AutonomousExecutor: state machine, combat, exploration |
| [Navigation](mcp-doom/navigation.md) | NavigationMemory: grid cells, keys, doors, exploration |
| [State](mcp-doom/state.md) | State extraction: variables, objects, sectors, depth |
| [Objects](mcp-doom/objects.md) | Object database: 70+ Doom entity types with metadata |

### Frontend (`docs/frontend/`)

| Document | Description |
|----------|-------------|
| [Overview](frontend/README.md) | Tech stack, routing, project structure |
| [Pages](frontend/pages.md) | All 7 pages with data flow and components |
| [Components](frontend/components.md) | All 10 major UI components |
| [Hooks & API](frontend/hooks-api.md) | useRunStream hook and API client library |
| [Testing](frontend/testing.md) | Vitest unit tests and Playwright E2E tests |

### Operations (`docs/operations/`)

| Document | Description |
|----------|-------------|
| [Configuration](operations/configuration.md) | Env vars, DB overrides, behavior profiles |
| [Deployment](operations/deployment.md) | CI/CD pipeline, Docker Compose, GitHub Actions |
| [Monitoring](operations/monitoring.md) | Prometheus, Sentry, health endpoints, metrics |

### Cross-Cutting

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System architecture, lockstep runtime flow |
| [Abstract](abstract.md) | Academic abstract |
| [Database Schema](db%20schema.md) | Schema areas and constraints |
| [Testing](testing.md) | Centralized testing guide for all services |
| [Security](security.md) | Security model, limitations, credential management |

### Historical (`docs/historical/`)

| Document | Description |
|----------|-------------|
| [Backend Implementation](historical/backend-implementation.md) | Detailed implementation notes |
| [Backend Continuation Notes](historical/backend-continuation-notes.md) | Next work items |
| [LLM Cycle Improvements](historical/llm-cycle-improvements.md) | Ranked improvement roadmap |
| [Progress Report](historical/progress-report.md) | 2026-05-24 status |
| [Still To Be Done](historical/stillneed-to-be-done.md) | Backlog and gaps |
| [Technical Review](historical/technical-review-2026-05-24.md) | Code review findings |

## Quick Links

- [Root README](/README.md) — project-level overview and setup
- [AGENTS.md](/AGENTS.md) — AI agent quick reference
- [Docker Compose](/docker-compose.yml) — full-stack deployment
- [CI Workflow](/.github/workflows/ci.yml) — fast CI pipeline
- [E2E Workflow](/.github/workflows/full-e2e.yml) — full product E2E
