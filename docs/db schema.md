# Database Schema Notes

Alembic migrations are authoritative. The current schema stores:

| Area | Tables |
| --- | --- |
| Uploads and analysis | `wad_files`, `wad_maps`, `static_analyses` |
| Run evidence | `test_runs`, `agent_decisions`, `game_events`, `agent_position_trail` |
| Findings | `defects`, `notable_event_screenshots`, `test_reports` |
| Reviewer analytics | `wad_spatial_memory`, `wad_hypotheses` |

Important constraints:

- `game_events` intentionally allows repeated factual `(run_id, tick_number)`
  values. Use row `id` as the tie-breaker.
- `agent_position_trail.is_sentinel` marks internal rows that must not appear in
  public movement metrics.
- `agent_decisions.decision_source` records whether a decision came from Gemini
  or the explicit deterministic fallback.
- The generated `wad_knowledge_base` table was removed by migration
  `20260531_0008_llm_directed_runtime_cleanup`.
