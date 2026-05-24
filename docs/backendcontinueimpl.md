# Backend Continuation Notes

This file replaces the original planning notes with the current implementation reality. Use the top-level `README.md` for setup and operation.

## Active Runtime Path

The active runtime path is lockstep:

1. `RunService.create_run()` validates the request, applies runtime config overrides, creates a `test_runs` row, and schedules `agent_run_task()`.
2. `agent_run_task()` in `run_loop.py` opens the WAD through `mcp-doom`, records frames, builds LLM input, calls Gemini, validates the decision through guard code, executes one MCP tool, and stores telemetry.
3. `run_guards.py` prevents repeated no-progress decisions, low-value loops, impossible combat retries, and stuck loops.
4. `run_memory.py` formats prior WAD/map memory at run start and persists new spatial events after completion.
5. `defect_service.py` detects static/runtime defects after the run.
6. `report_service.py` builds the report payload, renders HTML through Jinja2, and writes the PDF with WeasyPrint in a worker thread.

## Static Analysis

Static analysis is implemented in `analysis_service.py`. It uses `omgifol` for WAD parsing, then local Python logic for map features, skill summaries, enemy/resource metrics, and map PNG rendering. No separate difficulty-analysis repository is required.

## MCP Integration

`mcp-doom` is the simulator boundary. It uses the `vizdoom` package directly and exposes FastMCP tools over SSE for the backend.

Important modules:

- `server.py`: FastMCP tool declarations.
- `game_manager.py`: game lifecycle, compound actions, and stateful tool behavior.
- `game_setup.py`: WAD map discovery, player-start inspection, and isolated load preflight.
- `state.py`: screenshot, object, sector, depth, and variable extraction.
- `executor.py`: experimental async Director/Executor support.

## Experimental Director Path

Director/Executor code remains present because the MCP service supports an async player mode and tests cover director recovery helpers. It is not the product default. The graduate-project demo and evidence trail should use lockstep mode.

## Current High-Value Next Work

1. Docker/compose deployment files.
2. Worker queue for long report/analysis jobs.
3. Persistent task control for multi-replica backend operation.
4. PostgreSQL and artifact backup/restore scripts.
5. k6/Locust load tests.
6. Browser E2E fixture in CI with screenshot, video-frame, and PDF artifact capture.
