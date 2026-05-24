# Agentic PWAD QA for Doom — Documentation

## Project Overview

**Agentic PWAD QA for Doom** is an autonomous quality assurance testing system for Doom PWAD (Patch WAD) files. It replaces manual map testing with an AI-driven pipeline that uploads custom maps, plays through them via ViZDoom, and produces professional audit-ready PDF QA reports.

The core testing loop uses a **Google Gemini** language model as an autonomous play-tester. The model observes the game state and screenshots through a structured MCP interface, selects high-level actions (explore, aim-and-shoot, strafe, retreat, etc.), and executes them in a lockstep loop. Every decision, game event, position, defect, and token cost is persisted to an auditable PostgreSQL database. The system then aggregates all evidence — video recordings, position trails, defect descriptions, coverage metrics, and screenshots — into a comprehensive QA report.

This project is built for modders, map authors, and QA engineers who need defensible, repeatable, and automated testing of Custom Doom maps without requiring a human to play through every corner of every map.

## System Architecture

The system is composed of three independent services connected through well-defined network boundaries:

- **[Backend](backend/)** — FastAPI application that orchestrates the entire QA workflow: WAD upload and static analysis, run lifecycle management, LLM decision service, defect detection, report generation, and WebSocket streaming. Owns the PostgreSQL database and all runtime artifacts.
- **[MCP Doom Server](mcp-doom/)** — FastMCP service that wraps ViZDoom. Exposes game state (screenshots, depth buffers, object lists, sector geometry, 37+ tracked variables) and named atomic actions as MCP tools. The backend never presses ViZDoom buttons directly — it calls semantic MCP tools like `explore`, `aim_and_shoot`, and `retreat`.
- **[Frontend](frontend/)** — Next.js App Router dashboard for uploading WADs, starting runs, monitoring live gameplay with streaming video and LLM reasoning, inspecting defects, viewing recordings, and downloading PDF reports.

For a detailed architectural description with diagrams, see the [Architecture Overview](architecture.md).

## Documentation Map

### Architecture

| Document | Description |
|---|---|
| [Architecture Overview](architecture.md) | High-level system architecture, service boundaries, data flow diagrams with mermaid |

### Backend Documentation

| Document | Description |
|---|---|
| [Overview](backend/README.md) | FastAPI backend layered architecture, tech stack, key design decisions |
| [API Reference](backend/api.md) | Complete REST and WebSocket API surface with endpoint tree diagram |
| [Data Model](backend/data-model.md) | All 13 SQLAlchemy ORM models, entity-relationship diagram, column reference |
| [Services Layer](backend/services.md) | 20 service modules: WAD analysis, run orchestration, MCP client, Gemini, recording, reporting |
| [Run Lifecycle & Agent Loop](backend/run-lifecycle.md) | Lockstep AI loop: state fetch, prompt construction, guard validation, action execution, telemetry |
| [Defect Detection](backend/defect-detection.md) | 7 detector algorithms, fingerprinting, deduplication, cross-run pattern analysis |

### Frontend Documentation

| Document | Description |
|---|---|
| [Overview](frontend/README.md) | Next.js 16 app structure, navigation tree, build proxy configuration |
| [Pages & Data Flow](frontend/pages.md) | All 7 pages with data fetching, live WebSocket streaming, useRunStream hook, API client |
| [Components](frontend/components.md) | All 10 major UI components: MapCanvas, ReasoningLog, DecisionTimeline, StatBar, and more |

### MCP Doom Server

| Document | Description |
|---|---|
| [Overview](mcp-doom/README.md) | FastMCP server architecture, module layout, ViZDoom integration |
| [Tools Reference](mcp-doom/tools.md) | Complete catalog of 20 MCP tools with parameters, return types, descriptions |
| [Game Manager & Executor](mcp-doom/game-manager.md) | Game lifecycle, compound actions, autonomous executor state machine, navigation memory |

### Operations

| Document | Description |
|---|---|
| [CI/CD Pipeline](operations/deployment.md) | GitHub Actions workflows, test stages, build verification |
| [Configuration](operations/configuration.md) | Environment variables, runtime settings, behavior profiles |
| [Monitoring & Health Checks](operations/monitoring.md) | Prometheus metrics, health endpoints, Sentry, failure categories |

## Quick Start

- **[Getting Started Guide](../README.md#backend-setup)** — Backend setup and first run from the project root README
- **[MCP Doom Setup](../README.md#mcp-doom-setup)** — Starting the ViZDoom MCP server
- **[Frontend Setup](../README.md#frontend-setup)** — Launching the Next.js dashboard
- **[First Manual Run](../README.md#first-manual-run)** — End-to-end walkthrough with curl commands

## Technology Stack

| Category | Technology |
|---|---|
| **Backend Framework** | Python 3.11+, FastAPI, Uvicorn |
| **MCP Framework** | FastMCP (Python MCP server SDK) |
| **Game Engine** | ViZDoom (Doom 2D reinforcement learning environment) |
| **LLM Provider** | Google Gemini (gemini-2.5-flash-lite default) |
| **Database** | PostgreSQL 14+, SQLAlchemy 2.0 (async), Alembic |
| **Frontend Framework** | Next.js 15+ (App Router), React 19, TypeScript |
| **PDF Reporting** | WeasyPrint, Jinja2 HTML templates |
| **Real-Time** | WebSocket (FastAPI WebSocket + frontend hooks) |
| **Video Recording** | FFmpeg (MP4 encoding from raw frames) |
| **Map Analysis** | omgifol (Python WAD parser) |
| **Testing (Backend)** | pytest, pytest-asyncio |
| **Testing (Frontend)** | Vitest, React Testing Library |
| **Testing (MCP)** | pytest, ViZDoom integration fixtures |
| **CI** | GitHub Actions |
