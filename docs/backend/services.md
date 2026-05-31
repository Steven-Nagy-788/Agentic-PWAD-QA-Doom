# Backend Services

## Active Runtime

| Service | Purpose |
| --- | --- |
| `run_loop.py` | Lockstep orchestration, prompt projection, MCP execution, persistence |
| `run_tracking.py` | Non-mutating progress tracking, runtime warnings, stall detection |
| `run_utils.py` | Canonical LLM payload, bounded same-run ledger, normalization helpers |
| `gemini_service.py` | Gemini tool-call parsing, retry handling, explicit deterministic fallback |
| `mcp_client_service.py` | FastMCP client boundary |
| `run_service.py` | Run creation, cancellation, status transitions |

Valid model actions are not rewritten by backend gameplay guards. Technical
validation may normalize numeric bounds, button payloads, and telemetry
controls. Malformed requests return `invalid_params`.

## Evidence And Output

| Service | Purpose |
| --- | --- |
| `collector_service.py` | Stores events, decisions, position telemetry, sentinel rows |
| `recording_service.py` | Builds retained MP4 recordings |
| `report_service.py` | Builds deterministic metrics, Gemini-assisted narrative, PDFs |
| `environment_service.py` | Collects factual runtime metadata |
| `smoke_service.py` | Runs guarded MCP smoke probes |

## Reviewer Analytics

| Service | Purpose |
| --- | --- |
| `run_memory.py` | Persists reviewer-only spatial cells and hypotheses |
| `pattern_service.py` | Aggregates repeated run patterns |
| `defect_service.py` | Detects map-author defects from evidence |

Reviewer analytics remain queryable from the WAD memory endpoint, but they are
not injected into future model decisions.
