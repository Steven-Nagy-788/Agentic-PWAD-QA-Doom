# Run Lifecycle

## Creation

`RunService.create_run()` validates the requested WAD, map, difficulty, profile,
and tick budget. It uses the requested profile or configured default without
changing behavior based on earlier runs.

A PostgreSQL advisory lock and process-local task registry enforce one active
episode.

## Lockstep Iteration

Each loop iteration:

1. Reads normalized MCP state.
2. Updates visited QA cells using the shared `256` Doom-unit grid.
3. Projects the canonical model payload and bounded same-run ledger.
4. Requests one Gemini action.
5. Persists the explicit source: `gemini`, `deterministic_fallback`, or terminal
   source.
6. Validates technical parameters.
7. Executes valid MCP calls unchanged or records `invalid_params`.
8. Persists factual output, factual MCP tic, position, angle, warnings, and
   progress.
9. Broadcasts live state, ledger projection, and coverage cells.

Repeated factual tics are allowed. Stored row IDs preserve deterministic order.

## Completion

Terminal MCP state, cancellation, error, tick exhaustion, and prolonged
no-progress stalls finish a run. Tracking stops inconclusive stalls after the
configured threshold; it never injects a recovery action.

After the loop, the backend finalizes recording metadata, detects defects, and
generates the report. Reviewer spatial memory and hypotheses may be updated for
the WAD detail API, but are not sent to future agents.
