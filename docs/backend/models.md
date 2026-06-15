# Backend Data Models

All ORM models inherit from `app.models.Base` (declarative base from SQLAlchemy). Located in `Backend/app/models/`.

## 1. `WadFile` — `wad_files`

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK, default uuid4 |
| `original_filename` | String(255) | NOT NULL |
| `stored_path` | String(512) | NOT NULL |
| `file_size_bytes` | Integer | NOT NULL |
| `sha256_hash` | String(64) | NOT NULL, unique |
| `validation_status` | String(32) | default 'pending' |
| `detected_maps` | ARRAY(String) | nullable |
| `iwad_required` | String(32) | nullable |
| `uploaded_at` | DateTime | default utcnow |
| `updated_at` | DateTime | onupdate utcnow |

Tracks uploaded PWAD files with SHA-256 deduplication.

## 2. `StaticAnalysisResult` — `static_analysis_results`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id, unique |
| `map_name` | String(16) | |
| `thing_counts` | JSONB | thing type id→count |
| `enemy_counts` | JSONB | enemy type→count |
| `item_counts` | JSONB | item type→count |
| `key_counts` | JSONB | key type→count |
| `weapon_counts` | JSONB | weapon type→count |
| `linedef_count` | Integer | |
| `sector_count` | Integer | |
| `vertex_count` | Integer | |
| `map_bounds` | JSONB | {min_x, max_x, min_y, max_y, width, height} |
| `total_monster_hp` | Integer | |
| `health_pickups_total` | Integer | |
| `armor_pickups_total` | Integer | |
| `hitscanner_pct` | Float | percentage of hitscanner monsters |
| `health_ratio` | Float | health_pickups / total_monster_hp |
| `ammo_ratio` | Float | ammo / total_monster_hp |
| `estimated_difficulty` | String(32) | easy/medium/hard |
| `enemy_breakdown` | JSONB | per-type detail |
| `item_breakdown` | JSONB | per-type detail |
| `spawn_summary_by_skill` | JSONB | per-skill (1-5) spawn tables |
| `map_overview_png_path` | String(512) | path to rendered PNG |
| `door_count` | Integer | |
| `lift_count` | Integer | |
| `teleporter_count` | Integer | |
| `key_required_count` | Integer | |

One per (wad, map). Populated by `AnalysisService.analyze_map()`.

## 3. `TestRun` — `test_runs`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id |
| `map_name` | String(16) | |
| `difficulty_level` | Integer | 1-5 |
| `iwad_used` | String(32) | freedoom1/freedoom2 |
| `llm_model` | String(64) | |
| `behavior_profile` | String(32) | thorough/fast/exploit_focused |
| `max_ticks` | Integer | |
| `seed` | Integer | nullable |
| `status` | String(32) | queued/pending/analyzing/running/... |
| `outcome` | String(32) | completed/player_died/pwad_crash/... |
| `started_at` | DateTime | |
| `completed_at` | DateTime | |
| `duration_seconds` | Float | |
| `error_message` | Text | nullable |
| `failure_category` | String(32) | pwad_crash/infrastructure/null |
| `failure_stage` | String(64) | |
| `failure_diagnostics` | JSONB | |
| `final_hp` | Integer | |
| `final_armor` | Integer | |
| `kill_count` | Integer | |
| `death_count` | Integer | |
| `secret_count` | Integer | |
| `item_count` | Integer | |
| `action_count` | Integer | |
| `llm_call_count` | Integer | |
| `recording_path` | String(512) | |
| `recording_metadata` | JSONB | frame count, FPS, etc. |
| `progress_metrics` | JSONB | per-metric progress snapshots |
| `agent_quality_flags` | JSONB | quality assessment flags |
| `environment_metadata` | JSONB | OS, Python, packages |
| `report_pdf_path` | String(512) | |
| `start_normalization` | String(32) | none/no_player_one/multi_player_one |

Central record for each QA run.

## 4. `GameEvent` — `game_events`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id |
| `tick_number` | Integer | factual game tic (not index) |
| `player_x` | Float | |
| `player_y` | Float | |
| `player_angle` | Float | |
| `player_health` | Integer | |
| `player_armor` | Integer | |
| `player_ammo` | Integer | |
| `kill_count` | Integer | |
| `item_count` | Integer | |
| `secret_count` | Integer | |
| `weapon_selected` | Integer | |
| `event_type` | String(32) | kill/item_pickup/death/damage/... |
| `killed_enemy_type` | String(64) | nullable |
| `damage_received` | Integer | default 0 |
| `action_taken` | JSONB | MCP tool call + params |
| `llm_reasoning` | Text | nullable |
| `llm_input_summary` | Text | nullable |

Multiple rows may share the same `tick_number`. Ordered by `(tick_number, id)`.

## 5. `AgentDecision` — `agent_decisions`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id |
| `sequence_number` | Integer | |
| `tick_before` | Integer | tick at decision start |
| `tick_after` | Integer | tick after action executed |
| `status` | String(16) | success/error |
| `error_message` | Text | nullable |
| `llm_input_summary` | Text | |
| `llm_decision` | JSONB | parsed LLM response |
| `raw_llm_decision` | Text | raw LLM text |
| `reasoning_summary` | Text | |
| `mcp_tool` | String(64) | tool name |
| `mcp_input` | JSONB | tool parameters |
| `mcp_output` | JSONB | tool result |
| `mcp_stop_reason` | String(64) | |
| `guard_modified` | Boolean | whether guard system modified |
| `guard_reason` | String(256) | why guard intervened |
| `decision_source` | String(32) | llm/deterministic_fallback/guard |
| `llm_duration_ms` | Integer | |
| `mcp_duration_ms` | Integer | |
| `prompt_tokens` | Integer | |
| `completion_tokens` | Integer | |
| `cost_estimate` | Float | |

Complete audit trail of every LLM→MCP decision.

## 6. `Defect` — `defects`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id |
| `severity` | Integer | 1-4 (1=critical) |
| `priority` | Integer | 1-3 |
| `resolution_status` | String(16) | open/candidate/confirmed/false_positive |
| `defect_type` | String(64) | ammo_starvation/softlock/... |
| `fingerprint` | String(128) | dedup key |
| `title` | String(256) | |
| `description` | Text | |
| `reproduction_steps` | Text | |
| `detected_at_tick` | Integer | |
| `position_x` | Float | nullable |
| `position_y` | Float | nullable |
| `recommendation` | Text | |
| `first_seen_tick` | Integer | |
| `last_seen_tick` | Integer | |
| `occurrence_count` | Integer | default 1 |

Fingerprinted by `(defect_type, detected_at_tick)` for deduplication.

## 7. `TestReport` — `test_reports`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id, unique |
| `report_purpose` | Text | |
| `executive_summary` | Text | |
| `critical_issues` | JSONB | |
| `geometry_analysis_name` | Text | section 1 |
| `technical_performance_name` | Text | section 2 |
| ... | ~30 Text/JSONB fields | 14 QA sections |
| `objectives` | JSONB | |
| `coverage` | JSONB | |
| `evidence_matrix` | JSONB | |
| `qa_sections` | JSONB | |
| `recommendations` | Text | |
| `final_verdict` | Text | pass/fail/conditional |
| `pass_fail_summary` | JSONB | |
| `risk_areas` | JSONB | |
| `good_quality_areas` | JSONB | |
| `pdf_path` | String(512) | |
| `generation_status` | String(32) | pending/generating/completed/error |
| `generated_at` | DateTime | |

Generated by `ReportService` via Gemini LLM + WeasyPrint PDF rendering.

## 8. `AgentPositionTrail` — `agent_position_trail`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id |
| `tick_number` | Integer | |
| `x` | Float | |
| `y` | Float | |
| `angle` | Float | nullable |
| `health` | Integer | |
| `is_sentinel` | Boolean | internal boundary markers |

Sentinel rows are excluded from public queries. Used for trail rendering.

## 9. `ConfigEntry` — `config_entries`

| Field | Type | Notes |
|-------|------|-------|
| `key` | String(128) | PK |
| `value` | JSONB | NOT NULL |
| `updated_at` | DateTime | auto-update |

Runtime-configurable key-value store. Overrides environment defaults.

## 10. `NotableEventScreenshot` — `notable_event_screenshots`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id |
| `game_event_id` | UUID | FK → game_events.id |
| `screenshot_path` | String(512) | |

Links screenshots to notable game events.

## 11. `WadSpatialMemory` — `wad_spatial_memory`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id |
| `map_name` | String(16) | |
| `cell_x` | Integer | 256-unit grid |
| `cell_y` | Integer | |
| `event_type` | String(64) | |
| `occurrence_count` | Integer | |
| `last_seen_run_id` | UUID | |

Cross-run spatial memory for persistent map knowledge.

## 12. `WadHypothesis` — `wad_hypotheses`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id |
| `map_name` | String(16) | |
| `tag` | String(64) | auto-inferred category |
| `content` | Text | hypothesis text |
| `confidence` | Float | 0.0-1.0 |
| `confirmed_at` | DateTime | nullable |
| `refuted_at` | DateTime | nullable |

Cross-run hypothesis tracking. Tagged by `_infer_tag()` (texture/visual_glitch/etc).
