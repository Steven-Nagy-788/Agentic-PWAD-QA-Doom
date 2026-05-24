# Agentic PWAD QA for Doom — System Architecture

## Overview

Agentic PWAD QA for Doom is an autonomous quality assurance system that takes custom Doom WAD files as input and produces professional QA reports. It uses Google Gemini 2.5 Flash as an AI agent to play through maps via ViZDoom, controlled through the Model Context Protocol (MCP). Every tick of gameplay, every LLM decision, and every MCP tool call is recorded, analyzed for defects, and compiled into a PDF report.

---

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend (Next.js 16 / React 19)"]
        F_WAD["WAD Library Page<br/>/wad/[id]"]
        F_HISTORY["Run History Page<br/>/history"]
        F_LIVE["Live Run View<br/>/run/[id]"]
        F_SETTINGS["Settings Page<br/>/settings"]
        F_HEALTH["Health Dashboard<br/>/health"]
    end

    subgraph Backend["Backend API (FastAPI, port 8000)"]
        API["FastAPI Routers<br/>(wads, runs, analysis,<br/>reports, settings, ws)"]
        RS["Run Service"]
        RL["Run Loop (Lockstep)"]
        WD["WAD Service"]
        AS["Analysis Service<br/>(OMGDF parser)"]
        GS["Gemini Service"]
        MCP_C["MCP Client Service"]
        COL["Collector Service"]
        DS["Defect Service"]
        RPT["Report Service<br/>(WeasyPrint PDF)"]
        MEM["Run Memory Service<br/>(cross-run learning)"]
        REC["Recording Service<br/>(OpenCV + ffmpeg)"]
        WS["WebSocket Service"]
        SV["Smoke/Health Service"]
    end

    subgraph Database["PostgreSQL (port 5432)"]
        DB[("SQLAlchemy async ORM<br/>13 tables")]
    end

    subgraph MCP_Server["MCP Doom Server (FastMCP, port 8001)"]
        MCP_SSE["SSE Transport"]
        GM["Game Manager"]
        VIZ["ViZDoom Instance"]
        EXEC["Executor/ Director"]
        NAV["Navigation System"]
        OBJ["Object & Threat System"]
    end

    subgraph LLM["LLM Layer"]
        GEMINI["Google Gemini 2.5 Flash<br/>(genai SDK)"]
    end

    subgraph Storage["File Storage"]
        FS_WAD["WAD files<br/>storage/wads/"]
        FS_REC["Recordings<br/>storage/recordings/*.mp4"]
        FS_SS["Screenshots<br/>storage/screenshots/"]
        FS_RPT["PDF Reports<br/>storage/reports/"]
        FS_AN["Analysis maps<br/>storage/analysis/*.png"]
    end

    Frontend -->|"HTTP REST (JSON)"| API
    Frontend -->|"WebSocket (JSON)"| WS
    API --> DB
    RS --> RL
    RL --> MCP_C
    RL --> GS
    RL --> COL
    RL --> REC
    RL --> WS
    MCP_C -->|"SSE / MCP protocol"| MCP_SSE
    GS -->|"HTTP (genai SDK)"| GEMINI
    REC --> FS_REC
    REC --> FS_SS
    WD --> FS_WAD
    WD --> AS
    RPT --> FS_RPT
    AS --> FS_AN
    DS --> DB
    SV --> MCP_C
    SV --> GEMINI
    MEM --> DB
```

### Component Descriptions

| Component | Technology | Role |
|---|---|---|
| **Frontend** | Next.js 16 (React 19) | Dashboard UI for uploading WADs, viewing run history, monitoring live runs, adjusting settings |
| **Backend API** | FastAPI (Python) | REST API + WebSocket server; orchestrates all QA run lifecycle |
| **PostgreSQL** | SQLAlchemy async | Persistent storage for all entities (WADs, runs, events, decisions, defects, reports, memory) |
| **MCP Doom Server** | FastMCP (Python) | Wraps ViZDoom as MCP tools; exposes game state, actions, and compound behaviors |
| **Gemini LLM** | Google Gemini 2.5 Flash | Decision-making agent; receives game state + screen capture, returns structured JSON decisions |
| **Recording Service** | OpenCV + ffmpeg | Captures gameplay frames into MP4 video with H.264 transcoding |

### Communication Protocols

- **Frontend ↔ Backend**: REST/JSON over HTTP (port 8000) for CRUD operations; WebSocket (port 8000) for live run streaming
- **Backend ↔ MCP Doom**: MCP protocol over SSE (Server-Sent Events) at `http://localhost:8001/sse`; `fastmcp` Python client library
- **Backend ↔ Gemini**: HTTPS using `google-genai` Python SDK (REST API)

---

## 2. Lockstep AI Loop

The lockstep AI loop is the core gameplay cycle. The game is **paused** between LLM decisions — the agent must think, decide, and execute before the game advances.

```mermaid
sequenceDiagram
    participant RL as Run Loop
    participant MCP as MCP Doom<br/>(port 8001)
    participant GM as Gemini LLM
    participant DB as PostgreSQL
    participant REC as Recording Service
    participant WS as WebSocket
    participant GUARD as Lockstep Guards

    Note over RL: === GAME STARTED ===
    RL->>MCP: start_game(wad, map, difficulty)
    MCP-->>RL: OK
    RL->>DB: update run status="running"
    RL->>WS: broadcast(state=llm_start)

    loop Every lockstep iteration
        Note over RL: STEP 1: Get game state
        RL->>MCP: get_state(include_sectors, include_depth)
        MCP-->>RL: state + screenshot_png

        Note over RL: STEP 2: Tick/coverage tracking
        RL->>RL: _unique_lockstep_tick()
        RL->>RL: _track_visited_cell()
        RL->>REC: write_frame()

        Note over RL: STEP 3: Enrich context
        RL->>MCP: get_threat_assessment()
        RL->>MCP: get_navigation_info()
        MCP-->>RL: tactical intel
        RL->>DB: _recent_trace() (last 5 events)
        RL->>RL: build llm_input{state, threat, nav, trace, memory}

        Note over RL: STEP 4: Call Gemini
        RL->>WS: broadcast(type=llm_start, sequence)
        RL->>GM: decide(prompt + llm_input + screenshot)
        GM-->>RL: parsed decision{reasoning, mcp_tool, mcp_params}

        Note over RL: STEP 5: Post-processing
        RL->>RL: _merge_hypotheses()
        RL->>GUARD: _apply_lockstep_recovery()
        RL->>GUARD: _guard_lockstep_decision()
        GUARD-->>RL: guarded/modified decision
        RL->>DB: save AgentDecision(status=llm_complete)
        RL->>WS: broadcast(type=llm_decision, reasoning, tokens, cost)

        Note over RL: STEP 6: Execute MCP tool
        RL->>WS: broadcast(type=mcp_call_start)
        RL->>RL: _compute_dynamic_stride()
        RL->>MCP: call_tool(explore/aim_and_shoot/etc)
        MCP-->>RL: result_state + telemetry_frames

        Note over RL: STEP 7: Process results
        RL->>REC: write_frame() + telemetry frames
        RL->>GUARD: _update_lockstep_after_action()
        RL->>RL: _finalize_lockstep_decision()
        RL->>COL: collect() → GameEvent + AgentPositionTrail
        RL->>DB: save GameEvent + update AgentDecision
        RL->>WS: broadcast(type=llm_decision, mcp_call_result, progress)

        Note over RL: STEP 8: Check run-ending conditions
        RL->>RL: map_exit? → outcome="map_completed"
        RL->>RL: dead? → outcome="player_died"
        RL->>GUARD: _lockstep_should_stop_as_stuck? → outcome="stuck"
        RL->>RL: timeout/maxticks? → outcome="timeout"
        Note over RL: If none — throttle and loop

        RL->>RL: _compute_dynamic_throttle()
        RL->>RL: sleep(throttle_seconds)
    end

    Note over RL: === POST-RUN: Defect Detection & Report ===
    RL->>DS: detect_for_run(run)
    RL->>MEM: persist_spatial_memory()
    RL->>MEM: persist_hypotheses()
    RL->>MEM: update_knowledge_document()
    RL->>RPT: generate(run) → PDF
    RL->>WS: broadcast(report_status, defects)
```

### Lockstep State Machine

The `LockstepState` dict tracks per-run progress:

| Field | Purpose |
|---|---|
| `visited_cells` | Set of `(cx,cy)` cells visited for coverage tracking |
| `total_map_cells_estimate` | Pre-computed from static analysis |
| `completed_object_ids` | Map of object IDs successfully reached/collected |
| `failed_object_ids` | Map of object IDs that failed repeatedly |
| `out_of_ammo_targets` | Combat targets where ammo ran out |
| `action_signature_counts` | Recent action signatures to detect loops |
| `low_value_explore_total` | Count of explores that consumed budget without progress |
| `should_stop_stuck` | Flag set when lockstep recovery is exhausted |
| `progress_score` | Cumulative progress metric (arrivals, kills) |
| `hypotheses` | LLM-generated hypotheses about map issues |

### Behavior Profiles

Runs support different behavior profiles that tune the lockstep loop:

| Profile | Default Stride | Description |
|---|---|---|
| **thorough** | 60 tics | Conservative exploration; pauses to analyze frequently |
| **fast** | 150 tics | Optimizes for speed; longer explore actions between decisions |
| **exploit_focused** | 40 tics | Aggressively probes for edge cases and softlocks |

Profiles are stored in `Backend/app/core/behavior_profiles.py` and loaded per-run.

---

## 3. Data Flow for a Test Run

```mermaid
sequenceDiagram
    participant User as User/Developer
    participant F as Frontend
    participant API as Backend API
    participant AS as Analysis Service
    participant RL as Run Loop
    participant MCP as MCP Doom
    participant GM as Gemini LLM
    participant REC as Recording Service
    participant DS as Defect Service
    participant MEM as Run Memory Service
    participant RPT as Report Service
    participant DB as PostgreSQL
    participant FS as File Storage

    %% === PHASE 1: WAD UPLOAD & ANALYSIS ===
    User->>F: Upload WAD file
    F->>API: POST /v1/wads/upload
    API->>DB: Insert WadFile row (pending)
    API->>AS: analyze_wad(wad_file)
    AS->>FS: Save .png overview map
    AS->>DB: Insert StaticAnalysisResult<br/>(things, linedefs, sectors,<br/>enemy breakdown, skill spawns,<br/>map features, difficulty estimate)
    API-->>F: Return WadFile + detected maps

    %% === PHASE 2: CREATE RUN ===
    User->>F: Select map + difficulty + profile, click "Start Run"
    F->>API: POST /v1/runs
    API->>DB: Insert TestRun (status=pending)
    API->>MEM: build_cross_run_memory()
    API->>MEM: build_spatial_memory_briefing()
    API->>MEM: build_knowledge_briefing()
    API->>API: render_agent_prompt()
    API-->>F: Return run details

    %% === PHASE 3: AGENT PLAYS ===
    Note over API,F: Frontend opens WebSocket to /v1/ws/runs/{run_id}
    F->>API: WebSocket connect
    API->>RL: agent_run_task(run_id) [background asyncio task]
    RL->>MCP: start_game(wad, map, difficulty)
    MCP->>MCP: ViZDoom init
    MCP-->>RL: game ready

    loop Every lockstep iteration
        RL->>MCP: get_state()
        MCP-->>RL: state + screenshot
        RL->>GM: decide(state + screenshot)
        GM-->>RL: JSON decision
        RL->>MCP: execute tool (explore/aim/etc)
        MCP-->>RL: result state + telemetry
        RL->>REC: write_frame()
        RL->>DB: Insert GameEvent + AgentDecision + AgentPositionTrail
        RL->>F: WebSocket: llm_decision + mcp_call_result + frame
        Note over RL: End conditions checked each iteration
    end

    %% === PHASE 4: DEFECT DETECTION ===
    RL->>DS: detect_for_run(run)
    DS->>DS: _pwad_crash()
    DS->>DS: _difficulty_spawn_mismatch()
    DS->>DS: _repeated_deaths()
    DS->>DS: _ammo_starvation()
    DS->>DS: _health_deficit()
    DS->>DS: _softlock()
    DS->>DS: _unreachable_secrets()
    DS->>DS: _link_screenshots_to_defects()
    DS->>DB: Insert Defect rows

    %% === PHASE 5: CROSS-RUN MEMORY ===
    RL->>MEM: persist_spatial_memory()
    MEM->>DB: Upsert WadSpatialMemory cells
    RL->>MEM: persist_hypotheses()
    MEM->>DB: Insert/update WadHypothesis
    RL->>MEM: update_knowledge_document()
    MEM->>DB: Upsert WadKnowledgeBase

    %% === PHASE 6: REPORT GENERATION ===
    RL->>RPT: generate(run_id)
    RPT->>DB: Query all events, decisions, positions, defects
    RPT->>RPT: _build_metrics()
    RPT->>RPT: _call_gemini_or_fallback() → structured JSON
    RPT->>RPT: _render_pdf() via WeasyPrint
    RPT->>FS: Write PDF file
    RPT->>DB: Insert TestReport + update run.report_pdf_path
    RPT-->>RL: done
    RL->>F: WebSocket: report_status=complete

    %% === PHASE 7: VIEW RESULTS ===
    User->>F: View run page
    F->>API: GET /v1/runs/{run_id}
    F->>API: GET /v1/runs/{run_id}/defects
    F->>API: GET /v1/runs/{run_id}/decisions
    F->>API: GET /v1/runs/{run_id}/trace
    F->>API: GET /v1/runs/{run_id}/position-trail
    F->>API: GET /v1/runs/{run_id}/recording
    F->>API: GET /v1/runs/{run_id}/usage
    F->>API: GET /v1/runs/{run_id}/benchmark
    API-->>F: All data for dashboard
    User->>F: "Download PDF Report"
    F->>API: GET /v1/reports/{run_id}/pdf
    API-->>F: PDF file download
```

### Run Outcomes

| Outcome | Meaning |
|---|---|
| `map_completed` | Agent reached the exit (level_completed or next_map) |
| `player_died` | Agent health dropped to 0 |
| `stuck` | Lockstep system detected no progress across repeated decisions |
| `timeout` | Episode timeout or max_ticks exceeded |
| `cancelled` | User manually cancelled via API |
| `pwad_crash` | WAD failed to initialize in ViZDoom |
| `error` | Infrastructure or tool error (MCP connect failure, timeout) |

### WebSocket Event Types

During a live run, the frontend receives these WebSocket messages:

| Type | When | Payload |
|---|---|---|
| `state` | Run start | Status + tick |
| `llm_start` | Before Gemini call | sequence_number, tick |
| `llm_decision` | After Gemini response | reasoning, mcp_tool, tokens, cost |
| `mcp_call_start` | Before MCP execution | tool, params |
| `mcp_call_result` | After MCP execution | stop_reason, duration |
| `progress` | After each action | coverage, score, metrics |
| `frame` | At live_frame_fps rate | JPEG base64 screenshot |
| `event` | On notable events | event type + reasoning |
| `defect` | After detection | defect_type, severity |
| `report_status` | Report generation | status (generating/complete/error) |
| `quality_summary` | Run end | progress_metrics, quality_flags |
| `recording_status` | Recording finalized | metadata, warnings |
| `status` | During throttle | phase, sleep_seconds |

---

## 4. Database Entity Relationships

```mermaid
erDiagram
    WadFile {
        uuid id PK
        string original_filename
        string stored_path
        bigint file_size_bytes
        string sha256_hash "UNIQUE"
        datetime uploaded_at
        string validation_status
        string validation_error
        string[] detected_maps
        string iwad_required
    }

    StaticAnalysisResult {
        uuid id PK
        uuid wad_file_id FK
        string map_name
        string map_title
        string map_display_name
        string map_title_source
        int thing_count_total
        int thing_count_enemies
        int thing_count_items
        int thing_count_keys
        int thing_count_weapons
        int linedef_count
        int sector_count
        int secret_sector_count
        int vertex_count
        int map_width_units
        int map_height_units
        int total_monster_hp
        int total_health_pickup_pts
        int total_armor_pickup_pts
        float hitscanner_percent
        float health_ratio
        float ammo_ratio
        string estimated_difficulty
        jsonb enemy_breakdown
        jsonb item_breakdown
        jsonb spawn_summary_by_skill
        string map_overview_png_path
        datetime created_at
    }

    TestRun {
        uuid id PK
        uuid wad_file_id FK
        uuid static_analysis_id FK "nullable"
        string map_name
        int difficulty_level "1-5"
        string iwad_used
        string llm_model
        string behavior_profile "thorough | fast | exploit_focused"
        int max_ticks
        string status "pending | analyzing | running | completed | failed | cancelled"
        datetime started_at
        datetime completed_at
        int duration_seconds
        string outcome "map_completed | player_died | stuck | timeout | pwad_crash | error"
        string error_message
        string failure_category
        string failure_stage
        string failure_summary
        jsonb failure_diagnostics
        string recording_mp4_path
        jsonb recording_metadata
        jsonb progress_metrics
        jsonb agent_quality_flags
        string report_pdf_path
        int final_hp
        int final_armor
        int total_kills
        int total_deaths
        int secrets_found
        int total_items_collected
        int total_actions_taken
        int total_llm_calls
        datetime created_at
    }

    GameEvent {
        int id PK "serial"
        uuid run_id FK
        int tick_number
        float player_x
        float player_y
        int player_angle
        int health
        int armor
        int ammo_bullets
        int ammo_shells
        int ammo_rockets
        int ammo_cells
        int kill_count
        int item_count
        int secret_count
        int weapon_selected
        uuid agent_decision_id FK "nullable"
        string event_type "normal | kill | death | damage_taken | item_pickup | secret_found | map_exit | stuck"
        int damage_received
        string llm_reasoning
        string llm_input_summary
        jsonb action_taken
        datetime created_at
    }

    AgentDecision {
        uuid id PK
        uuid run_id FK
        int sequence_number
        int tick_before
        int tick_after
        string status "started | llm_complete | complete"
        string reasoning_summary
        string mcp_tool
        jsonb mcp_input
        jsonb mcp_output
        string mcp_stop_reason
        jsonb llm_input_summary
        jsonb llm_decision
        int llm_input_tokens
        int llm_output_tokens
        float llm_cost_estimate_usd
        float llm_duration_ms
        float mcp_duration_ms
        uuid game_event_id FK "nullable"
        datetime created_at
    }

    AgentPositionTrail {
        int id PK "serial"
        uuid run_id FK
        int tick_number
        float x
        float y
        int health
        datetime created_at
    }

    NotableEventScreenshot {
        int id PK "serial"
        uuid run_id FK
        int game_event_id FK
        string screenshot_path
        datetime created_at
    }

    Defect {
        uuid id PK
        uuid run_id FK
        int severity "1=critical, 2=major, 3=minor"
        int priority "1=high, 2=medium, 3=low"
        string defect_type "pwad_crash | difficulty_spawn_mismatch | repeated_death_location | ammo_starvation | health_deficit | softlock_navigation | unreachable_secret | agent_observed_*"
        string fingerprint "dedup key"
        string title
        string description
        string recommendation
        int detected_at_tick
        float position_x
        float position_y
        int screenshot_id FK "nullable"
        int first_seen_tick
        int last_seen_tick
        int occurrence_count
        datetime created_at
    }

    TestReport {
        uuid id PK
        uuid run_id FK "UNIQUE"
        string generation_status "pending | generating | complete | error"
        string generation_error
        string report_purpose
        string intended_audience
        string problem_and_escalation
        string test_items_summary
        string test_environment_summary
        jsonb hardware_spec
        jsonb software_spec
        string variances_from_plan
        string defect_summary_narrative
        string defect_patterns
        jsonb pass_fail_summary
        jsonb risk_areas
        jsonb good_quality_areas
        string pdf_path
        datetime created_at
    }

    ConfigEntry {
        string key PK
        string value "runtime overrides"
    }

    WadSpatialMemory {
        uuid id PK
        uuid wad_file_id FK
        string map_name
        int cell_x
        int cell_y
        string event_type
        bigint occurrence_count
        uuid last_seen_run_id FK "nullable"
        datetime created_at
        datetime updated_at
        %% UNIQUE(wad_file_id, map_name, cell_x, cell_y, event_type)
    }

    WadHypothesis {
        uuid id PK
        uuid wad_file_id FK
        string map_name
        string tag "BLOCKED_PATH | KEY_LOCATION | RESOURCE_CACHE | VISUAL_GLITCH | ENCOUNTER_HOTSPOT | NAVIGATION_GAP"
        string content
        float confidence "0-1"
        datetime confirmed_at
        datetime refuted_at
        uuid last_seen_run_id FK "nullable"
        datetime created_at
        datetime updated_at
    }

    WadKnowledgeBase {
        uuid id PK
        uuid wad_file_id FK
        string map_name
        string document_text
        int version
        datetime created_at
        datetime updated_at
        %% UNIQUE(wad_file_id, map_name)
    }

    WadFile ||--o{ StaticAnalysisResult : "has many"
    WadFile ||--o{ TestRun : "has many"
    WadFile ||--o{ WadSpatialMemory : "has many"
    WadFile ||--o{ WadHypothesis : "has many"
    WadFile ||--o{ WadKnowledgeBase : "has many"

    StaticAnalysisResult ||--o{ TestRun : "referenced by"

    TestRun ||--o{ GameEvent : "has many"
    TestRun ||--o{ AgentDecision : "has many"
    TestRun ||--o{ Defect : "has many"
    TestRun ||--o{ AgentPositionTrail : "has many"
    TestRun ||--o{ NotableEventScreenshot : "has many"
    TestRun ||--|{ TestReport : "has one"
    TestRun ||--o{ WadSpatialMemory : "last seen in"
    TestRun ||--o{ WadHypothesis : "last seen in"

    GameEvent ||--o{ NotableEventScreenshot : "has screenshot"
    AgentDecision ||--|| GameEvent : "produces one"
    Defect ||--o{ NotableEventScreenshot : "illustrated by"
```

### Key Indexes

| Table | Index | Columns |
|---|---|---|
| `test_runs` | Primary lookup | `wad_file_id`, `status`, `created_at DESC` |
| `test_runs` | Map history | `(wad_file_id, map_name, created_at DESC)` |
| `game_events` | Run trace | `(run_id, tick_number)` |
| `wad_spatial_memory` | Cell lookup | `(wad_file_id, map_name)` |
| `wad_hypotheses` | Tag search | `(wad_file_id, map_name, tag)` |
| `agent_decisions` | Run decisions | `(run_id, sequence_number)` |

---

## 5. Key Subsystems

### 5.1 WAD Analysis Service (`Backend/app/services/analysis_service.py`)

Uses the `omg` library to parse WAD files at the binary level. For each map, it extracts:
- **Thing counts** by type (enemies, items, keys, weapons) with Doom-format spawn rules
- **Map geometry** (linedefs, sectors, vertices, bounds)
- **Secret sectors** (sector type 9)
- **Feature detection** (doors, locked doors, lifts, teleporters, key requirements)
- **Difficulty estimates** based on enemy count, hitscanner percentage, health/ammo ratios
- **Skill spawn analysis** — determines which things spawn at each difficulty level (1-5) considering skill flags and multiplayer flags

Output stored in `StaticAnalysisResult` with per-skill spawn summaries in `spawn_summary_by_skill` JSONB column.

### 5.2 MCP Doom Server (`mcp-doom/src/doom_mcp/`)

A FastMCP server exposing ViZDoom through MCP tools over SSE transport. Key tools:

| Tool | Type | Description |
|---|---|---|
| `start_game` | Control | Initialize ViZDoom with WAD/map/scenario |
| `get_state` | Observation | Full game state + screenshot PNG (sectors optional) |
| `take_action` | Atomic action | Execute raw button presses for N tics |
| `explore` | Compound | Autonomous exploration with wall avoidance |
| `aim_and_shoot` | Compound | Aim + fire at target |
| `strafe_and_shoot` | Compound | Strafe + fire (hitscan dodge) |
| `move_to` | Compound | Pathfind to object |
| `retreat` | Compound | Turn and run / backpedal |
| `get_threat_assessment` | Context | Tactical threat analysis |
| `get_navigation_info` | Context | Exploration grid + door tracking |
| `get_situation_report` | Context | Executor state summary (async mode) |
| `set_objective` | Director | Assign goals to autonomous executor |
| `set_strategy` | Director | Tune executor behavior parameters |

Compound actions (`explore`, `aim_and_shoot`, etc.) run many game tics internally (sub-millisecond simulation) and return telemetry frames at configurable strides. This avoids round-trip latency for every game tic.

The server supports two modes:
- **SYNC_PLAYER** (default): Game pauses between `take_action` calls — each action is an atomic decision
- **ASYNC_PLAYER** (optional): Game runs continuously at 35 Hz; agent uses `set_objective`/`set_strategy` to guide an autonomous executor

### 5.3 Gemini Service (`Backend/app/services/gemini_service.py`)

Wraps the `google-genai` SDK with:

- **Rate limiting**: Semaphore-based concurrency control + sliding window rate limiter (calls/minute)
- **Retry logic**: 3 attempts with exponential backoff; rate-limit-aware retry delays
- **JSON extraction**: Multiple strategies to extract valid JSON from LLM text output (code blocks, balanced braces, last-resort brace find)
- **Decision parsing**: Validates tool names against allowed set, normalizes parameters
- **Deterministic fallback**: When Gemini is unavailable/key is missing/rate limited, a rule-based `_fallback_decision()` picks targets based on visible monsters > visible pickups > weapon switch > USE interaction > unexplored direction > turn-and-retreat
- **Cost tracking**: Token usage is captured per-call and stored in `AgentDecision` rows

The system prompt is rendered from `Backend/app/prompts/agent_system_prompt.md` with static analysis data, cross-run memory, spatial memory briefing, and knowledge document injected as template variables.

### 5.4 Recording Service (`Backend/app/services/recording_service.py`)

- Captures gameplay frames as OpenCV `ndarray` → writes to `.source.mp4` (MP4V codec)
- Transcodes to H.264 with `ffmpeg` for browser-compatible output
- Frame deduplication via perceptual hashing (blake2b of 64×48 thumbnail)
- Tick-aware frame skipping to maintain target FPS
- Validation checks: frame count vs expected (based on game tics), unique frame ratio, minimum duration, resolution
- `save_screenshot()`: Captures individual frames for notable events (PNG, linked to `NotableEventScreenshot` table)

### 5.5 Defect Detection (`Backend/app/services/defect_service.py`)

Runs after each completed run, detecting:

| Defect Type | Detection Logic | Severity |
|---|---|---|
| `pwad_crash` | Run outcome is `pwad_crash` | 1 (Critical) |
| `difficulty_spawn_mismatch` | Skill flags hide enemies/items at chosen difficulty | 2-3 |
| `repeated_death_location` | Multiple deaths within 50-unit area | 2 |
| `ammo_starvation` | Zero ammo for 60+ consecutive ticks | 2 |
| `health_deficit` | HP below 10 for 30+ consecutive ticks | 3 |
| `softlock_navigation` | Repeated stuck events or timeout with <20 unit movement in final 30 events | 1 |
| `unreachable_secret` | Secret sectors exist but none found at >60% coverage | 3 |
| `agent_observed_*` | LLM self-reported issue via `observed_issue` field | 2 |

Defects also link to `NotableEventScreenshot` records for visual evidence in reports.

### 5.6 Cross-Run Memory System (`Backend/app/services/run_memory.py`)

Persists knowledge across multiple runs of the same WAD/map:

| Table | Purpose |
|---|---|
| `WadSpatialMemory` | Grid-cell-level event history (stuck cells, death cells, key locations, secret locations, resource starvation) — aggregated with occurrence counts |
| `WadHypothesis` | Persistent tags about map issues (BLOCKED_PATH, KEY_LOCATION, RESOURCE_CACHE, etc.) with confidence scores that increase with repeated observation |
| `WadKnowledgeBase` | Accumulated free-text document about a map, updated after each run with outcome, duration, defects |

On run start, these are queried and injected into the LLM prompt as structured context. This enables the agent to learn from previous runs: e.g., "avoid the north corridor, the last 3 runs got stuck there."

### 5.7 Report Generation (`Backend/app/services/report_service.py`)

Generates professional PDF QA reports using the UK Ministry of Defence DEF STAN 00-055 format:

1. **Data aggregation**: Queries all events, decisions, positions, defects for the run
2. **Metrics computation**: Event counts, movement distance, action distribution, coverage percentage, kill ratios, health/ammo ratios
3. **Gemini enhancement**: Sends compact run data to Gemini for narrative generation (falls back to deterministic template if unavailable)
4. **PDF rendering**: Uses `WeasyPrint` with `jinja2` HTML templates → PDF
5. **Storage**: PDF saved to filesystem; path stored in `TestReport` and `TestRun.report_pdf_path`

Report sections include: report purpose, test environment, hardware/software specs, pass/fail summary (navigation, combat, resources, secrets), defect summary, risk areas, and decision trace appendix.

---

## 6. API Endpoints

### WAD Management (`/v1/wads`)

| Method | Path | Description |
|---|---|---|
| POST | `/wads/upload` | Upload a WAD file (multipart) |
| GET | `/wads` | List all WADs |
| GET | `/wads/{id}` | Get WAD details |
| DELETE | `/wads/{id}` | Delete WAD + cascade |
| POST | `/wads/{id}/reanalyze` | Re-run static analysis |
| GET | `/wads/{id}/maps` | List maps in WAD |
| GET | `/wads/{id}/map-png?map_name=` | Get overview PNG |
| GET | `/wads/maps` | All maps across WADs |

### Run Management (`/v1/runs`)

| Method | Path | Description |
|---|---|---|
| POST | `/runs` | Create and start a test run |
| GET | `/runs` | List runs (filterable by wad, map, outcome, status, difficulty, date range) |
| GET | `/runs/{id}` | Get run details |
| DELETE | `/runs/{id}` | Cancel run |
| POST | `/runs/{id}/force-stop` | Force-stop run |
| PATCH | `/runs/{id}/behavior` | Change behavior profile mid-run |
| GET | `/runs/compare?run_a=&run_b=` | Side-by-side run comparison |

### Trace & Telemetry (`/v1/runs/{id}`)

| Method | Path | Description |
|---|---|---|
| GET | `/runs/{id}/trace` | Full ordered GameEvent trace (paginated) |
| GET | `/runs/{id}/events` | Filtered notable events |
| GET | `/runs/{id}/decisions` | LLM/MCP decision trace (paginated) |
| GET | `/runs/{id}/defects` | Detected defects |
| GET | `/runs/{id}/position-trail` | Position samples |
| GET | `/runs/{id}/recording` | MP4 video download |
| GET | `/runs/{id}/usage` | Token/cost summary |
| GET | `/runs/{id}/benchmark` | Latency breakdown |

### Reports (`/v1/reports`)

| Method | Path | Description |
|---|---|---|
| GET | `/reports/{run_id}/pdf` | Download PDF report |

### Health (`/v1/health`)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Basic health check |
| GET | `/health/gemini` | Gemini API probe |
| GET | `/health/mcp` | MCP SSE reachability |
| GET | `/health/smoke` | Full end-to-end smoke test |
| GET | `/health/detailed` | All dependencies + storage + active runs |

### WebSocket

| Path | Description |
|---|---|
| `/v1/ws/runs/{run_id}` | Live run stream (decision events, frames, progress) |

---

## 7. File Layout

```
Agentic-PWAD-QA-Doom/
├── Backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry point, lifespan, health checks
│   │   ├── core/
│   │   │   ├── config.py              # Settings (pydantic-settings)
│   │   │   ├── database.py            # SQLAlchemy async engine + session
│   │   │   ├── types.py               # LockstepState type alias
│   │   │   ├── behavior_profiles.py   # Profile definitions
│   │   │   └── metrics.py             # Prometheus metrics
│   │   ├── models/                    # SQLAlchemy ORM models (13 tables)
│   │   ├── repositories/              # Data access layer (8 repositories)
│   │   ├── routers/                   # FastAPI route handlers (7 routers)
│   │   ├── serializers/               # Pydantic response models
│   │   ├── services/                  # Business logic (19 services)
│   │   └── prompts/                   # LLM system prompt templates
│   ├── migrations/                    # Alembic migrations
│   └── tests/                         # Pytest test suite
├── mcp-doom/
│   └── src/doom_mcp/
│       ├── server.py                  # FastMCP server definition (18 tools)
│       ├── game_manager.py            # ViZDoom lifecycle + state management
│       ├── game_setup.py              # ViZDoom config builder
│       ├── actions.py                 # Action execution (take_action)
│       ├── state.py                   # State extraction + normalization
│       ├── objects.py                 # Game object enrichment DB
│       ├── scenarios.py               # Built-in scenario definitions
│       ├── navigation.py              # Grid-based exploration + stuck recovery
│       └── executor.py                # Autonomous director executor
├── frontend/
│   ├── app/                           # Next.js App Router pages
│   ├── components/                    # React components
│   ├── hooks/                         # Custom hooks (useRunStream)
│   └── lib/                           # API client, types, utilities
└── docs/
    └── architecture.md                # This document
```
