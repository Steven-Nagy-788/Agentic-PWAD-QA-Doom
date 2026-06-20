# Backend Data Models

All ORM models inherit from `app.models.Base` (declarative base from SQLAlchemy). Located in `Backend/app/models/`.

## 1. `WadFile` — `wad_files`

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK, `gen_random_uuid()` |
| `original_filename` | String(255) | NOT NULL |
| `stored_path` | Text | NOT NULL, unique |
| `file_size_bytes` | BigInteger | NOT NULL |
| `sha256_hash` | String(64) | NOT NULL, unique |
| `uploaded_at` | DateTime(tz) | `func.now()` |
| `validation_status` | String(32) | NOT NULL, default `'pending'` |
| `validation_error` | Text | nullable |
| `detected_maps` | ARRAY(Text) | nullable |
| `iwad_required` | String(16) | NOT NULL, default `'freedoom2'` |

Tracks uploaded PWAD files with SHA-256 deduplication.

## 2. `StaticAnalysisResult` — `static_analysis_results`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id, ON DELETE CASCADE |
| `map_name` | String(16) | |
| `thing_count_total` | Integer | default 0 |
| `thing_count_enemies` | Integer | default 0 |
| `thing_count_items` | Integer | default 0 |
| `thing_count_keys` | Integer | default 0 |
| `thing_count_weapons` | Integer | default 0 |
| `linedef_count` | Integer | default 0 |
| `sector_count` | Integer | default 0 |
| `secret_sector_count` | Integer | default 0 |
| `vertex_count` | Integer | default 0 |
| `map_width_units` | Integer | nullable |
| `map_height_units` | Integer | nullable |
| `total_monster_hp` | Integer | nullable |
| `total_health_pickup_pts` | Integer | nullable |
| `total_armor_pickup_pts` | Integer | nullable |
| `hitscanner_percent` | Numeric(5,2) | nullable |
| `health_ratio` | Numeric(8,4) | nullable |
| `ammo_ratio` | Numeric(8,4) | nullable |
| `estimated_difficulty` | String(16) | nullable |
| `enemy_breakdown` | JSONB | default `{}` |
| `item_breakdown` | JSONB | default `{}` |
| `map_title` | Text | nullable |
| `map_display_name` | Text | nullable |
| `map_title_source` | String(32) | nullable |
| `spawn_summary_by_skill` | JSONB | default `{}` |
| `map_overview_png_path` | Text | nullable |
| `analyzed_at` | DateTime(tz) | `func.now()` |

Unique constraint: `(wad_file_id, map_name)`. One per (wad, map).

## 3. `TestRun` — `test_runs`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id, ON DELETE CASCADE |
| `static_analysis_id` | UUID | FK → static_analysis_results.id, ON DELETE SET NULL, nullable |
| `map_name` | String(16) | NOT NULL |
| `difficulty_level` | SmallInteger | NOT NULL, default 3, CHECK BETWEEN 1 AND 5 |
| `iwad_used` | String(64) | NOT NULL, default `'freedoom2'` |
| `llm_model` | String(128) | NOT NULL, default `'gemini-3.1-flash-lite'` |
| `behavior_profile` | String(32) | nullable, default `'thorough'` |
| `max_ticks` | Integer | NOT NULL, default 3000 |
| `seed` | Integer | nullable |
| `start_normalization` | JSONB | nullable |
| `status` | String(16) | NOT NULL, default `'pending'` |
| `started_at` | DateTime(tz) | nullable |
| `completed_at` | DateTime(tz) | nullable |
| `duration_seconds` | Integer | nullable |
| `outcome` | String(32) | nullable |
| `error_message` | Text | nullable |
| `failure_category` | String(32) | nullable |
| `failure_stage` | String(64) | nullable |
| `failure_summary` | Text | nullable |
| `failure_diagnostics` | JSONB | nullable |
| `final_hp` | SmallInteger | nullable |
| `final_armor` | SmallInteger | nullable |
| `total_kills` | SmallInteger | nullable |
| `total_deaths` | SmallInteger | nullable |
| `secrets_found` | SmallInteger | nullable |
| `total_items_collected` | SmallInteger | nullable |
| `total_actions_taken` | Integer | nullable |
| `total_llm_calls` | Integer | nullable |
| `recording_mp4_path` | Text | nullable |
| `recording_metadata` | JSONB | nullable |
| `progress_metrics` | JSONB | nullable |
| `agent_quality_flags` | JSONB | nullable |
| `environment_metadata` | JSONB | nullable |
| `report_pdf_path` | Text | nullable |
| `system_prompt_hash` | String(64) | nullable |
| `system_prompt_text` | Text | nullable |
| `created_at` | DateTime(tz) | `func.now()` |

Indexes: `wad_file_id`, `status`, `created_at DESC`, `(wad_file_id, map_name, created_at DESC)`, `outcome`, `llm_model`.

Central record for each QA run.

## 4. `GameEvent` — `game_events`

| Field | Type | Notes |
|-------|------|-------|
| `id` | BigInteger | PK, autoincrement |
| `run_id` | UUID | FK → test_runs.id, ON DELETE CASCADE |
| `tick_number` | Integer | NOT NULL |
| `recorded_at` | DateTime(tz) | `func.now()` |
| `player_x` | REAL | NOT NULL |
| `player_y` | REAL | NOT NULL |
| `player_angle` | SmallInteger | NOT NULL |
| `health` | SmallInteger | NOT NULL |
| `armor` | SmallInteger | NOT NULL |
| `ammo_bullets` | SmallInteger | NOT NULL |
| `ammo_shells` | SmallInteger | NOT NULL |
| `ammo_rockets` | SmallInteger | NOT NULL |
| `ammo_cells` | SmallInteger | NOT NULL |
| `kill_count` | SmallInteger | NOT NULL |
| `item_count` | SmallInteger | NOT NULL |
| `secret_count` | SmallInteger | NOT NULL |
| `weapon_selected` | SmallInteger | NOT NULL |
| `action_taken` | JSONB | nullable |
| `llm_reasoning` | Text | nullable |
| `llm_input_summary` | Text | nullable |
| `event_type` | String(32) | NOT NULL, default `'normal'` |
| `killed_enemy_type` | String(64) | nullable |
| `damage_received` | SmallInteger | nullable |

Indexes: `run_id`, `(run_id, tick_number)`, partial `(run_id, event_type) WHERE event_type != 'normal'`.

Multiple rows may share the same `tick_number`. Ordered by `(tick_number, id)`.

## 5. `AgentDecision` — `agent_decisions`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id, ON DELETE CASCADE |
| `sequence_number` | Integer | NOT NULL |
| `tick_before` | Integer | nullable |
| `tick_after` | Integer | nullable |
| `game_event_id` | BigInteger | FK → game_events.id, ON DELETE SET NULL, nullable |
| `status` | String(16) | NOT NULL, default `'started'` |
| `error_message` | Text | nullable |
| `llm_input_summary` | JSONB | nullable |
| `llm_decision` | JSONB | nullable |
| `raw_llm_decision` | JSONB | nullable |
| `reasoning_summary` | Text | nullable |
| `mcp_tool` | String(64) | nullable |
| `mcp_input` | JSONB | nullable |
| `mcp_output` | JSONB | nullable |
| `mcp_stop_reason` | String(64) | nullable |
| `guard_modified` | Boolean | NOT NULL, default False |
| `guard_reason` | Text | nullable |
| `decision_source` | String(32) | NOT NULL, default `'gemini'` |
| `llm_duration_ms` | REAL | nullable |
| `mcp_duration_ms` | REAL | nullable |
| `llm_input_tokens` | Integer | nullable |
| `llm_output_tokens` | Integer | nullable |
| `llm_cost_estimate_usd` | REAL | nullable |
| `created_at` | DateTime(tz) | `func.now()` |

Unique constraint: `(run_id, sequence_number)`. Complete audit trail of every LLM→MCP decision.

## 6. `Defect` — `defects`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id, ON DELETE CASCADE |
| `report_id` | UUID | FK → test_reports.id, ON DELETE SET NULL, nullable |
| `severity` | SmallInteger | NOT NULL, CHECK BETWEEN 1 AND 4 |
| `priority` | SmallInteger | NOT NULL, CHECK BETWEEN 1 AND 3 |
| `resolution_status` | String(16) | NOT NULL, default `'open'` |
| `defect_type` | String(64) | NOT NULL |
| `fingerprint` | String(128) | nullable |
| `title` | String(255) | NOT NULL |
| `description` | Text | NOT NULL |
| `reproduction_steps` | Text | nullable |
| `detected_at_tick` | Integer | nullable |
| `position_x` | REAL | nullable |
| `position_y` | REAL | nullable |
| `screenshot_id` | UUID | FK → notable_event_screenshots.id, ON DELETE SET NULL, nullable |
| `recommendation` | Text | nullable |
| `first_seen_tick` | Integer | nullable |
| `last_seen_tick` | Integer | nullable |
| `occurrence_count` | Integer | NOT NULL, default 1 |
| `created_at` | DateTime(tz) | `func.now()` |

Unique constraints: `(run_id, defect_type, detected_at_tick)`, `(run_id, fingerprint)`.

## 7. `TestReport` — `test_reports`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id, ON DELETE CASCADE, unique |
| `report_purpose` | Text | nullable |
| `intended_audience` | Text | NOT NULL, default |
| `problem_and_escalation` | Text | nullable |
| `test_items_summary` | Text | nullable |
| `test_environment_summary` | Text | nullable |
| `hardware_spec` | JSONB | nullable |
| `software_spec` | JSONB | nullable |
| `variances_from_plan` | Text | nullable |
| `test_procedure_variances` | Text | nullable |
| `test_case_variances` | Text | nullable |
| `test_coverage_evaluation` | Text | nullable |
| `objectives_planned` | JSONB | nullable |
| `objectives_covered` | JSONB | nullable |
| `objectives_omitted` | JSONB | nullable |
| `uncovered_attributes` | Text | nullable |
| `test_process_changes` | Text | nullable |
| `defect_summary_narrative` | Text | nullable |
| `defect_patterns` | Text | nullable |
| `test_item_limitations` | Text | nullable |
| `dropped_features` | Text | nullable |
| `pass_fail_summary` | JSONB | nullable |
| `risk_areas` | JSONB | nullable |
| `good_quality_areas` | JSONB | nullable |
| `qa_sections` | JSONB | nullable |
| `evidence_matrix` | JSONB | nullable |
| `major_activities_summary` | Text | nullable |
| `activity_variances` | Text | nullable |
| `elapsed_time_seconds` | Integer | nullable |
| `total_actions_taken` | Integer | nullable |
| `report_model` | String(64) | nullable |
| `pdf_path` | String(512) | nullable |
| `generation_status` | String(32) | NOT NULL, default `'pending'` |
| `generation_error` | Text | nullable |
| `generated_at` | DateTime(tz) | nullable |
| `created_at` | DateTime(tz) | `func.now()` |

Generated by `ReportService` via Gemini LLM + WeasyPrint PDF rendering.

## 8. `AgentPositionTrail` — `agent_position_trail`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id, ON DELETE CASCADE |
| `tick_number` | Integer | NOT NULL |
| `x` | Float | NOT NULL |
| `y` | Float | NOT NULL |
| `angle` | Float | nullable |
| `health` | Integer | NOT NULL |
| `is_sentinel` | Boolean | NOT NULL, default False |

Sentinel rows are excluded from public queries. Used for trail rendering.

## 9. `ConfigEntry` — `config_entries`

| Field | Type | Notes |
|-------|------|-------|
| `key` | String(128) | PK |
| `value` | JSONB | NOT NULL |
| `updated_at` | DateTime(tz) | auto-update trigger |

Runtime-configurable key-value store. Overrides environment defaults.

## 10. `NotableEventScreenshot` — `notable_event_screenshots`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `run_id` | UUID | FK → test_runs.id, ON DELETE CASCADE |
| `game_event_id` | BigInteger | FK → game_events.id, ON DELETE CASCADE |
| `screenshot_path` | String(512) | NOT NULL |

Links screenshots to notable game events.

## 11. `WadSpatialMemory` — `wad_spatial_memory`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id, ON DELETE CASCADE |
| `map_name` | String(16) | NOT NULL |
| `cell_x` | Integer | NOT NULL |
| `cell_y` | Integer | NOT NULL |
| `event_type` | String(64) | NOT NULL |
| `occurrence_count` | Integer | NOT NULL, default 1 |
| `last_seen_run_id` | UUID | nullable |
| `created_at` | DateTime(tz) | `func.now()` |

Cross-run spatial memory for persistent map knowledge (256-unit grid cells).

## 12. `WadHypothesis` — `wad_hypotheses`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `wad_file_id` | UUID | FK → wad_files.id, ON DELETE CASCADE |
| `map_name` | String(16) | NOT NULL |
| `tag` | String(64) | NOT NULL |
| `content` | Text | NOT NULL |
| `confidence` | Float | NOT NULL, default 0.0 |
| `confirmed_at` | DateTime(tz) | nullable |
| `refuted_at` | DateTime(tz) | nullable |
| `created_at` | DateTime(tz) | `func.now()` |

Cross-run hypothesis tracking. Tagged by `_infer_tag()`.
