# Testing Guide

## Quick Reference

| Service | Command | Coverage | Requirements |
|---------|---------|----------|-------------|
| Backend | `cd Backend && .venv/bin/python -m pytest -q` | ~200+ tests | PostgreSQL, `.venv` |
| MCP-Doom (unit) | `cd mcp-doom && pytest -q -m "not integration"` | ~50 tests | `.venv` with dev deps |
| MCP-Doom (all) | `cd mcp-doom && pytest -q` | ~100+ tests | ViZDoom runtime + display |
| Frontend | `cd frontend && npm test -- --run` | ~20 tests | Node 22+ / Bun |
| Frontend E2E | `cd frontend && npm run test:e2e` | 1 spec | Chromium, dev server |

## Backend Tests

Location: `Backend/tests/` (28 test files)

### Test Infrastructure

- **Runner**: pytest with `asyncio_mode = auto`
- **Database**: Fresh PostgreSQL (configurable via env vars)
- **Fixtures**: Shared `conftest.py` with `test_wad_path` fixture (minimal PWAD with 8 enemies)
- **Mocking**: Service-level mocks for Gemini, MCP, file system

### Test Categories

| File | Tests | Type | Coverage |
|------|-------|------|----------|
| `test_analysis_service.py` | ~12 | Integration | WAD parsing, map features, overview PNG |
| `test_analysis_metadata.py` | 4 | Integration | Spawn skills, metadata, selected skill |
| `test_collector_service.py` | 8 | Unit | Issue normalization, variable normalization |
| `test_defect_service.py` | 20+ | Integration | All 7 defect detectors, streak episodes |
| `test_gemini_service.py` | 12 | Unit | JSON parsing, decision parsing, fallback |
| `test_guard_thresholds.py` | 8 | Unit | Settings guard fields, threshold logic |
| `test_initial_schema_migration.py` | 1 | Unit | SQL statement splitting |
| `test_openapi_contract.py` | 1 | Unit | OpenAPI model fields |
| `test_path_security.py` | 3 | Unit | Path traversal prevention |
| `test_pattern_service.py` | 15 | Integration | Cross-run pattern analysis, clustering |
| `test_prompt_sanitize.py` | 6 | Unit | Prompt value sanitization |
| `test_recording_service.py` | 6 | Integration | Frame padding, telemetry, ffmpeg timeout |
| `test_report_build_llm_input.py` | 10 | Unit | LLM input assembly, field defaults |
| `test_report_merge_defaults.py` | 10 | Unit | Gemini merge behavior, edge cases |
| `test_report_parse_json.py` | 16 | Unit | Multi-strategy JSON parsing, fallback |
| `test_report_service.py` | 10 | Unit | Voice sanitization, evidence model, PDF |
| `test_report_status_router.py` | 3 | Unit | Status determination (missing/pending/error) |
| `test_run_loop.py` | 15+ | Integration | Lockstep loop, tool execution, PWAD crash |
| `test_run_memory.py` | 2 | Unit | Tag inference, persistence check |
| `test_run_tracking.py` | 1 | Unit | No-progress detection |
| `test_run_utils.py` | 20+ | Unit | State compaction, cell tracking, throttle, params |
| `test_runs_router.py` | 1 | Unit | Cell size convention |
| `test_smoke_service.py` | 2 | Integration | Health check, Gemini key missing |
| `test_trace_serializers.py` | 2 | Unit | Trace entry fields |
| `test_wad_service.py` | 10 | Integration | WAD CRUD, upload, delete, analysis |
| `test_websocket_service.py` | 1 | Integration | Message replay on connect |

## MCP-Doom Tests

Location: `mcp-doom/tests/` (11 test files)

### Test Infrastructure

- **Runner**: pytest with `asyncio_mode = auto` (set in `pyproject.toml`)
- **Markers**: `@pytest.mark.integration` for ViZDoom-dependent tests
- **Unit tests**: No ViZDoom needed, mock/pure logic
- **Integration tests**: Require ViZDoom runtime (OpenGL, SDL, display)

### Unit Tests (no ViZDoom)

| File | Tests | Coverage |
|------|-------|----------|
| `test_actions.py` | 7 | Button name→action mapping, validation |
| `test_executor_director_unit.py` | 2 | Objective queue, progress report |
| `test_navigation.py` | 10 | Grid cells, keys, breadcrumbs, doors, direction |
| `test_objects.py` | 7 | Object info lookup, monsters, items, fallback |
| `test_scenarios.py` | 4 | Scenario listing, config paths, validation |
| `test_server_integration.py` | 8 | Mock-based error handling |
| `test_state.py` | 7 | PNG conversion, relative angle, depth stats |
| `test_weapon_slots_unit.py` | 2 | Slot inventory, weapon selection |

### Integration Tests (need ViZDoom)

| File | Tests | Coverage |
|------|-------|----------|
| `test_game_manager.py` | 30+ | Full lifecycle, state, actions, campaign, WAD, compound actions, weapons, threat, navigation |
| `test_executor.py` | 16 | Executor start/stop, explore, fight, retreat, objectives, strategy, events |
| `test_e2e_navigation_fixes.py` | ~15 | Exploration, move_to, navigation info, coverage |

### Running

```bash
# Unit only (fast CI)
pytest -q -m "not integration"

# Integration only
pytest -q -m integration

# All tests
pytest -q
```

## Frontend Tests

Location: `frontend/` (4 test files)

### Vitest Unit Tests

See [Frontend Testing](frontend/testing.md) for full details.

| File | Tests | Coverage |
|------|-------|----------|
| `MapCanvas.test.tsx` | 9 | SVG rendering, trail, events, coverage, keyboard nav |
| `SkillHeatmap.test.tsx` | 4 | Heatmap cells, loading, empty state |
| `StatBar.test.tsx` | 5 | Stats display, ammo sum, null defaults |
| `useRunStream.test.tsx` | 7 | WebSocket connection, dedup, truncation |

### Playwright E2E

| File | Coverage |
|------|----------|
| `live-map.spec.ts` | Live map layout at desktop and mobile viewports |

## CI Pipelines

### Fast CI (`.github/workflows/ci.yml`)

| Job | Steps |
|-----|-------|
| **backend** | PostgreSQL 16 service, Python 3.12, install system pkgs (ffmpeg, libcairo), pytest, Alembic check |
| **mcp-doom** | Python 3.12, editable install, `pytest -m "not integration"` |
| **frontend** | Bun 1.3, install, Playwright Chromium, vitest, eslint, next build, Playwright e2e |
| **docker-build** | Build 3 images (backend, mcp-doom, frontend) |

### Full E2E (`.github/workflows/full-e2e.yml`)

Triggered: workflow_dispatch or nightly (cron `17 2 * * *`)

Steps:
1. Build and start Docker Compose stack
2. Wait for backend health (up to 90 attempts)
3. Run `/health/smoke`
4. Generate PWAD fixture from Freedoom via `scripts/extract_iwad_map.py`
5. Start deterministic run (180 ticks, fast profile, seed 42)
6. Wait for terminal status (240s timeout)
7. Verify PDF and MP4 artifacts
8. Upload all artifacts + compose logs

## Test Philosophy

- **Unit tests**: Pure logic, no external dependencies, fast
- **Integration tests**: Exercise real subsystems (DB, MCP, ViZDoom) with mocked boundaries
- **E2E tests**: Full stack validation in CI (scheduled, not on every push)
- **Deterministic seeds**: Runs with fixed seeds for reproducible testing
- **Coverage**: Focus on defect detection logic, run loop paths, data integrity
