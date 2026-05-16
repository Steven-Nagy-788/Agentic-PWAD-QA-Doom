# Agentic PWAD QA Backend Implementation

This document describes the backend implementation for the Agentic PWAD QA Doom project as it exists in the `Backend/` application. It is intentionally detailed and implementation-oriented. Its purpose is to make the backend understandable without having to rediscover the architecture from source code.

The backend is a FastAPI application that accepts Doom PWAD uploads, analyzes maps statically, detects the correct IWAD base, starts autonomous test runs through the persistent `mcp-doom` service, asks Gemini for QA-oriented decisions, stores every trace event in PostgreSQL, streams live state and gameplay frames over WebSocket, records MP4 video, detects defects, and generates PDF QA reports.

## High-Level System

The backend lives in:

```text
Backend/
├── app/
│   ├── main.py
│   ├── core/
│   ├── models/
│   ├── prompts/
│   ├── repositories/
│   ├── routers/
│   ├── serializers/
│   ├── services/
│   └── utils/
├── scripts/
├── sql/
│   └── schema.sql
├── storage/
│   ├── wads/
│   ├── analysis/
│   ├── screenshots/
│   ├── recordings/
│   └── reports/
├── .env
├── .env.example
├── Makefile
└── requirements.txt
```

The adjacent `mcp-doom/` directory is a separate service. The backend does not spawn it per run. The expected runtime model is:

1. PostgreSQL is running.
2. The database schema has been applied from `Backend/sql/schema.sql`.
3. `mcp-doom` is already running as a persistent FastMCP SSE server.
4. The backend runs as FastAPI/Uvicorn.
5. The frontend calls the backend HTTP and WebSocket APIs.

The backend is designed around a layered structure:

```text
HTTP/WebSocket routers
    -> services
        -> repositories
            -> SQLAlchemy async ORM models
                -> PostgreSQL
```

The major external integrations are:

- PostgreSQL via SQLAlchemy async engine and `asyncpg`.
- Gemini via `google-genai`.
- `mcp-doom` via FastMCP `Client` over SSE.
- WAD parsing via `omgifol`.
- Map PNG rendering via Pillow.
- MP4/video and JPEG frame encoding via `opencv-python-headless`, followed by H.264 transcode through `ffmpeg`/`ffmpeg-python`.
- PDF generation via WeasyPrint.
- HTML templating via Jinja2.

## Runtime Configuration

Configuration is centralized in `app/core/config.py`.

The `Settings` class manually loads `Backend/.env` and reads environment variables from `os.environ`. This project is not using Pydantic settings for configuration. The settings object is cached with `@lru_cache` through `get_settings()`.

Important settings:

```env
APP_NAME=Doom Agentic Testing Backend
APP_ENV=development
DEBUG=false

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=doom_agentic_qa
POSTGRES_USER=doom_agentic
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql+asyncpg://...

STORAGE_BASE=/absolute/path/to/Backend/storage
WAD_STORAGE_DIR=/absolute/path/to/Backend/storage/wads
REPORT_STORAGE_DIR=/absolute/path/to/Backend/storage/reports
RECORDING_STORAGE_DIR=/absolute/path/to/Backend/storage/recordings
SCREENSHOT_STORAGE_DIR=/absolute/path/to/Backend/storage/screenshots
ANALYSIS_STORAGE_DIR=/absolute/path/to/Backend/storage/analysis

GEMINI_API_KEY=...
LLM_MODEL=gemini-2.5-flash
MCP_DOOM_SSE_URL=http://localhost:8001/sse

MAX_RUN_TICKS=35000
DEFAULT_RUN_TICKS=3000
LIVE_FRAME_FPS=2
CORS_ORIGINS=http://localhost:5173
```

Notes:

- `DATABASE_URL` uses `postgresql+asyncpg://`. A legacy `postgresql+psycopg://` value is normalized to `postgresql+asyncpg://` for safety, but psycopg is not required by this backend.
- Relative storage paths are resolved relative to the `Backend/` directory.
- `LLM_MODEL` is configurable. The current working default is `gemini-2.5-flash`.
- There is no backend `FREEDOOM2_WAD_PATH`. The backend passes `freedoom1` or `freedoom2` as the `wad` argument to `mcp-doom`.
- `MCP_DOOM_SSE_URL` points at the persistent MCP service, not a subprocess command.

## Database Setup

The database layer is in `app/core/database.py`.

It creates:

```python
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
Base = declarative_base()
```

Every HTTP request that needs the database receives an `AsyncSession` through the `get_db()` dependency. The session is closed at the end of the request.

The schema is defined in `sql/schema.sql`. The `Makefile` target `make db-schema` applies that SQL file using `psql`.

The schema creates `pgcrypto` so PostgreSQL can use `gen_random_uuid()`.

## Database Tables

### `wad_files`

Stores metadata for uploaded WAD files. The binary is stored on disk.

Important columns:

- `id`: UUID primary key.
- `original_filename`: file name from upload.
- `stored_path`: absolute path to the stored `.wad` file.
- `file_size_bytes`: upload size.
- `sha256_hash`: unique content hash used for deduplication.
- `uploaded_at`: upload timestamp.
- `validation_status`: `valid_pwad`, `invalid`, etc.
- `validation_error`: optional validation error.
- `detected_maps`: PostgreSQL text array of map names, such as `E1M1` or `MAP01`.
- `iwad_required`: `freedoom1` or `freedoom2`.

The `iwad_required` value is derived from detected map names:

- Any `E\dM\d` map uses `freedoom1`.
- Any `MAP\d{2}` map uses `freedoom2`.
- Unknown naming defaults to `freedoom2`.

### `static_analysis_results`

Stores one static analysis row per `(wad_file_id, map_name)`.

Important columns:

- Thing counts:
  - `thing_count_total`
  - `thing_count_enemies`
  - `thing_count_items`
  - `thing_count_keys`
  - `thing_count_weapons`
- Geometry counts:
  - `linedef_count`
  - `sector_count`
  - `secret_sector_count`
  - `vertex_count`
- Map size:
  - `map_width_units`
  - `map_height_units`
- Balance metrics:
  - `total_monster_hp`
  - `total_health_pickup_pts`
  - `total_armor_pickup_pts`
  - `hitscanner_percent`
  - `health_ratio`
  - `ammo_ratio`
  - `estimated_difficulty`
- JSONB breakdowns:
  - `enemy_breakdown`
  - `item_breakdown`
- `map_overview_png_path`: absolute path to generated overview PNG.

The table has a unique constraint on `(wad_file_id, map_name)`.

### `test_runs`

Stores one autonomous QA session.

Important columns:

- `wad_file_id`: uploaded WAD under test.
- `static_analysis_id`: analysis row for the selected map.
- `map_name`: selected map.
- `difficulty_level`: ViZDoom difficulty, checked between 1 and 5.
- `iwad_used`: selected base IWAD string, usually `freedoom1` or `freedoom2`.
- `llm_model`: model used for this run.
- `max_ticks`: run cap, default `3000`, clamped by service code.
- `status`: `pending`, `analyzing`, `running`, `completed`, `failed`, or `cancelled`.
- `started_at`, `completed_at`, `duration_seconds`.
- `outcome`: `map_completed`, `player_died`, `timeout`, `error`, or `cancelled`.
- `error_message`: failure detail.
- Final aggregate stats:
  - `final_hp`
  - `final_armor`
  - `total_kills`
  - `total_deaths`
  - `secrets_found`
  - `total_items_collected`
  - `total_actions_taken`
  - `total_llm_calls`
- Output paths:
  - `recording_mp4_path`
  - `report_pdf_path`

The backend enforces only one active run at a time because ViZDoom is effectively single-instance in this architecture.

### `game_events`

Stores the tick-by-tick trace. This is the most important runtime table.

Important columns:

- `run_id`.
- `tick_number`.
- `recorded_at`.
- Player state:
  - `player_x`
  - `player_y`
  - `player_angle`
  - `health`
  - `armor`
  - `ammo_bullets`
  - `ammo_shells`
  - `ammo_rockets`
  - `ammo_cells`
  - `kill_count`
  - `item_count`
  - `secret_count`
  - `weapon_selected`
- Agent decision:
  - `action_taken` JSONB
  - `llm_reasoning`
  - `llm_input_summary`
- Event classification:
  - `event_type`
  - `killed_enemy_type`
  - `damage_received`

`game_events` has a unique constraint on `(run_id, tick_number)`. It also has a partial index on notable events where `event_type != 'normal'`.

### `notable_event_screenshots`

Stores screenshots only for meaningful moments, not every tick.

Screenshots are saved on disk. The table stores:

- `run_id`
- `game_event_id`
- `screenshot_path`
- `captured_at`

Screenshots are currently captured for:

- `kill`
- `death`
- `damage_taken`

### `agent_position_trail`

Stores downsampled position samples for frontend path overlays.

The collector inserts one row every 10 ticks:

- `run_id`
- `tick_number`
- `x`
- `y`
- `health`

The full tick trace remains in `game_events`.

### `test_reports`

Stores structured QA report metadata and the generated PDF path.

Important columns:

- `run_id`, unique.
- Narrative report sections:
  - `report_purpose`
  - `test_items_summary`
  - `test_environment_summary`
  - `defect_summary_narrative`
  - plus additional QA-template fields that are present in the schema and ORM.
- JSON sections:
  - `hardware_spec`
  - `software_spec`
  - `objectives_planned`
  - `objectives_covered`
  - `objectives_omitted`
  - `pass_fail_summary`
  - `risk_areas`
  - `good_quality_areas`
- `pdf_path`
- `generation_status`
- `generation_error`

The current report service fills the core fields and produces a PDF with WeasyPrint.

### `defects`

Stores algorithmic and agent-observed defects.

Important columns:

- `run_id`
- `report_id`
- `severity`: 1 critical, 2 major, 3 minor, 4 trivial.
- `priority`: 1 high, 2 medium, 3 low.
- `resolution_status`: default `open`.
- `defect_type`
- `title`
- `description`
- `reproduction_steps`
- `detected_at_tick`
- `position_x`
- `position_y`
- `screenshot_id`
- `recommendation`

Agent-observed issues from Gemini responses are stored as `defect_type='agent_observed'`.

The table has a uniqueness constraint on `(run_id, defect_type, detected_at_tick)` so rerunning defect detection does not duplicate the same defect for the same run and tick.

## Application Startup

`app/main.py` creates the FastAPI application.

It configures:

- App title from settings.
- Debug mode from settings.
- CORS middleware.
- Routers:
  - WADs
  - Analysis
  - Runs
  - Reports
  - WebSocket trace

Startup behavior:

- Ensures these directories exist:
  - `storage/`
  - `storage/wads/`
  - `storage/analysis/`
  - `storage/reports/`
  - `storage/recordings/`
  - `storage/screenshots/`

Health endpoints:

- `GET /health`
  - Returns `{"status": "ok"}`.
- `GET /health/gemini`
  - Calls `GeminiService.probe_model()`.
  - Returns `status=ok` if the configured model works.
  - Returns `status=error` with the model and error string if not.
  - This endpoint intentionally avoids crashing the whole API when Gemini is unavailable.

## WAD Upload Flow

Endpoint:

```http
POST /wads/upload
```

Router:

```text
app/routers/wads.py
```

Service:

```text
app/services/wad_service.py
```

Repository:

```text
app/repositories/wad_repository.py
```

Serializer:

```text
app/serializers/wad_serializers.py
```

Upload logic:

1. Read uploaded bytes.
2. Validate binary header:
   - If file is too small, reject.
   - If first 4 bytes are `IWAD`, reject.
   - If first 4 bytes are not `PWAD`, reject.
   - If `TEXTMAP` appears in the binary, reject as UDMF unsupported.
3. Compute SHA-256.
4. Check `wad_files.sha256_hash`.
5. If an identical WAD already exists, return the existing database row.
6. Generate a UUID for the new WAD.
7. Save it to `storage/wads/{uuid}.wad`.
8. Parse map names with omgifol.
9. Reject if no supported maps are detected.
10. Detect `iwad_required`.
11. Insert the `wad_files` row with:
    - `validation_status='valid_pwad'`
    - `detected_maps`
    - `iwad_required`
12. Immediately run static analysis for all detected maps.
13. Commit the transaction.

Deduplication is content-based, not filename-based. Uploading the same bytes again returns the existing WAD row.

## Map List Endpoints

There are two map-list endpoints.

### All Maps

```http
GET /wads/maps?limit=100&offset=0
GET /wads/maps?wad_file_id={wad_id}
```

Returns every detected map across all uploaded WADs.

Query parameters:

- `wad_file_id`: optional UUID. When supplied, returns maps only for that WAD.
- `limit`: number of WAD records to scan when `wad_file_id` is not supplied. Default `100`, max `500`.
- `offset`: WAD pagination offset when `wad_file_id` is not supplied. Default `0`.

Pagination is applied at the WAD level, not the flattened map row level. This keeps maps from the same WAD together while preventing the endpoint from scanning the full upload history by default.

Response item shape:

```json
{
  "wad_file_id": "uuid",
  "map_name": "E1M1",
  "iwad_required": "freedoom1",
  "analyzed": true,
  "map_overview_png_url": "/wads/{wad_id}/map-png?map_name=E1M1"
}
```

Implementation:

- `WadRepository.list()`
- `WadService.all_maps()`
- `WadService._maps_for_wad()`

### Maps For One WAD

```http
GET /wads/{wad_id}/maps
```

Returns detected maps only for one WAD.

## Static Analysis

Endpoint:

```http
GET /wads/{wad_id}/analysis
```

Service:

```text
app/services/analysis_service.py
```

Constants:

```text
app/services/analysis_constants.py
```

Repository:

```text
app/repositories/analysis_repository.py
```

Serializer:

```text
app/serializers/analysis_serializers.py
```

Static analysis is run automatically during upload and can also be requested later. The service uses an upsert-style repository method, so rerunning analysis updates existing rows.

### Map Detection

`detect_map_names(wad_path)` uses:

```python
wad = WAD(wad_path)
names = [name.upper() for name in wad.maps.keys()]
```

The returned map names are sorted.

### IWAD Detection

`detect_iwad_requirement(map_names)` applies:

```text
E\dM\d  -> freedoom1
MAP\d{2} -> freedoom2
fallback -> freedoom2
```

This is stored on `wad_files.iwad_required` and later copied to `test_runs.iwad_used`.

### omgifol Parsing

`AnalysisService.analyze_map()` loads the WAD and constructs:

```python
editor = MapEditor(wad.maps[map_name])
```

It reads:

- `editor.things`
- `editor.vertexes`
- `editor.linedefs`
- `editor.sectors`

The service counts Thing types with `Counter(int(thing.type) for thing in editor.things)`.

### Thing Classification

Thing classification comes from `analysis_constants.py`.

The service uses:

- `ENEMY_TYPES`
- `ITEM_TYPES`
- `KEY_TYPES`
- `WEAPON_TYPES`

Enemy breakdown stores:

```json
{
  "IMP": {
    "count": 5,
    "hp": 60,
    "total_hp": 300,
    "hitscanner": false
  }
}
```

Item breakdown stores:

```json
{
  "STIMPACK": {
    "count": 3,
    "value": 10,
    "total": 30,
    "category": "health"
  }
}
```

### Geometry Metrics

The service stores:

- total linedefs
- total sectors
- total vertices
- secret sectors where `sector.type == 9`
- map width from vertex bounding box
- map height from vertex bounding box

Width and height are Doom map units:

```text
map_width_units = max_x - min_x
map_height_units = max_y - min_y
```

### Balance Metrics

The current implementation computes dmon-style fallback metrics directly from Thing counts:

- `total_monster_hp`
- `total_health_pickup_pts`
- `total_armor_pickup_pts`
- `hitscanner_percent`
- `health_ratio`
- `ammo_ratio`
- `estimated_difficulty`

The difficulty function is heuristic:

- More than 80 enemies adds 2 points.
- More than 30 enemies adds 1 point.
- Hitscanner percentage above 40 adds 1 point.
- Health ratio below 0.15 adds 1 point.
- Ammo ratio below 0.8 adds 1 point.

Score mapping:

- `0` -> `easy`
- `1` -> `fair`
- `2` or `3` -> `hard`
- `4+` -> `slaughter`

If a map has no monsters, ratios involving monster HP are `NULL`/`None`.

### Overview PNG Rendering

`AnalysisService._render_overview()` creates a 1024x1024 PNG using Pillow.

It:

1. Creates a black RGB image.
2. Computes vertex bounding box.
3. Scales the map into the image with 20 pixels of padding.
4. Draws linedefs in gray.
5. Attempts to draw secret linedefs in red if the linedef has a `secret` attribute.
6. Saves the image to:

```text
storage/analysis/{wad_id}_{map_name}_overview.png
```

Map overview PNGs are stored separately from gameplay screenshots. Gameplay screenshots remain in `storage/screenshots/`, while static analysis output lives in `storage/analysis/`.

Endpoint:

```http
GET /wads/{wad_id}/map-png?map_name=E1M1
```

Returns the PNG with `image/png`.

## Run Creation

Endpoint:

```http
POST /runs
```

Request body:

```json
{
  "wad_file_id": "uuid",
  "map_name": "E1M1",
  "difficulty_level": 3,
  "max_ticks": 3000
}
```

Service:

```text
app/services/run_service.py
```

Run creation logic:

1. Acquire a PostgreSQL advisory transaction lock:

   ```sql
   SELECT pg_advisory_xact_lock(42770001)
   ```

   This prevents concurrent requests from starting two ViZDoom sessions.

2. Fail orphaned active `pending` runs that were created but never started.
3. Query for active runs with status:
   - `pending`
   - `analyzing`
   - `running`
4. If an active run exists, return HTTP `409 Conflict`.
5. Fetch the WAD.
6. Validate that `map_name.upper()` is in `wad_files.detected_maps`.
7. Fetch or create static analysis for that map.
8. Clamp `max_ticks`:

   ```python
   max(1, min(requested_or_default, settings.max_run_ticks))
   ```

9. Create `test_runs` row with:
   - selected WAD
   - selected static analysis
   - selected map
   - difficulty level
   - `iwad_used=wad.iwad_required`
   - `llm_model=settings.llm_model`
   - clamped `max_ticks`
   - `status='pending'`
10. Commit the row.
11. Start an in-process async task:

    ```python
    RUN_TASKS[run.id] = asyncio.create_task(agent_run_task(run.id))
    ```

12. Return immediately to the frontend.

The active-run guard was tested with simultaneous `/runs` requests. One request creates a run, and the other receives `409 Conflict`.

## Run Cancellation And Force Stop

Endpoints:

```http
DELETE /runs/{run_id}
POST /runs/{run_id}/cancel
POST /runs/{run_id}/force-stop
```

All three call the same `RunService.cancel()` method.

Cancel logic:

1. Fetch the run.
2. If no run exists, return `404`.
3. If an in-memory task exists and is still running:
   - cancel the task
   - wait up to 30 seconds
   - if timeout occurs, call MCP `stop_game`
4. If there is no running task:
   - if the run is already terminal and has a report, return it
   - otherwise call MCP `stop_game`
5. Call `finalize_stopped_run(..., outcome='cancelled')`.
6. Refresh and return the run.

`finalize_stopped_run()`:

- Reads the latest `game_events` row.
- Copies latest HP, armor, kills, secrets, and items into `test_runs`.
- Counts actions and LLM calls from event rows.
- Sets status to `cancelled`.
- Sets outcome to `cancelled`.
- Sets `completed_at`.
- Computes `duration_seconds` if `started_at` is available.
- Commits the run update.
- Runs defect detection.
- Generates a report.
- Commits again.

This means force-stopped runs still have computed data and reports.

## Agent Run Task

The core long-running function is:

```text
app/services/run_service.py::agent_run_task()
```

This function owns the autonomous run lifecycle.

### Startup

When the task starts:

1. It opens a fresh `SessionLocal()` database session.
2. Fetches the `TestRun`.
3. Fetches the WAD row.
4. Fetches the static analysis row.
5. Renders the agent system prompt.
6. Creates:
   - `CollectorService`
   - `RecordingService`
   - `GeminiService`
7. Opens `McpDoomClient()` as an async context manager.
8. Calls MCP `start_game`.

The MCP `start_game` call passes:

```json
{
  "wad": "freedoom1 or freedoom2",
  "scenario_wad": "/absolute/path/to/uploaded.wad",
  "map_name": "E1M1",
  "difficulty": 3,
  "episode_timeout": 3000,
  "screen_resolution": "RES_320X240",
  "render_hud": false,
  "window_visible": false
}
```

After MCP starts the game, the backend updates:

- `status='running'`
- `started_at=now()`

and commits.

### Per-Tick Loop

The loop runs:

```python
for tick in range(run.max_ticks):
```

Each loop:

1. Calls `mcp.get_state()`.
2. Converts screenshot PNG bytes to a frame array.
3. Normalizes game variables.
4. Fetches the last 5 trace entries.
5. Builds compact LLM input:

   ```json
   {
     "tick": 0,
     "game_variables": {},
     "objects": [],
     "episode_finished": false,
     "recent_trace": []
   }
   ```

6. Calls Gemini through `GeminiService.decide()`.
7. Executes the selected MCP tool.
8. Normalizes the MCP response.
9. Collects/persists a `game_events` row.
10. Optionally saves a screenshot for notable events.
11. Writes a frame to the MP4 recorder.
12. Broadcasts a WebSocket `state` message.
13. Broadcasts a throttled WebSocket `frame` message if enough time has passed.
14. Commits the DB work.
15. Checks terminal conditions:
    - map exit
    - player death
    - max ticks reached
16. Sleeps 1 second.

The 1-second sleep is the main LLM throttle. In practice, MCP compound tools may internally advance many game tics per backend loop.

### Terminal Conditions

The task stops when:

- event type is `map_exit`
- state has `level_completed`
- state has `next_map`
- health is `0` or below
- tick reaches `max_ticks`
- task is cancelled
- an exception occurs

Outcomes:

- `map_completed`
- `player_died`
- `timeout`
- `cancelled`
- `error`

### Finalization

In the `finally` block, the task:

1. Calls MCP `stop_game()`.
2. Finalizes the MP4 writer.
3. Stores `recording_mp4_path` if a video was written.
4. Sets terminal status.
5. Stores outcome and completion timestamp.
6. Computes duration.
7. Stores total actions and LLM calls.
8. Copies final player stats from the last event.
9. Commits.
10. Runs defect detection for completed/cancelled runs.
11. Generates a report.
12. Commits.
13. Broadcasts a terminal WebSocket state.
14. Removes the task from `RUN_TASKS`.

## MCP Client

The MCP integration is in:

```text
app/services/mcp_client_service.py
```

The client uses:

```python
from fastmcp import Client
```

It connects to:

```python
settings.mcp_doom_sse_url
```

Expected value:

```text
http://localhost:8001/sse
```

Exposed methods:

- `call_tool(name, params)`
- `start_game(wad, scenario_wad, map_name, difficulty, episode_timeout)`
- `get_state()`
- `stop_game()`

`normalize_mcp_state()` handles the different shapes FastMCP can return:

- raw lists
- content wrappers
- text JSON
- structured content
- image data with `mime_type`, `mimeType`, or `format`

It returns:

```python
tuple[dict[str, Any], bytes | None]
```

where the `bytes` value is an optional screenshot image.

## Gemini Service

Gemini integration is in:

```text
app/services/gemini_service.py
```

Allowed MCP tools:

- `get_state`
- `explore`
- `aim_and_shoot`
- `move_to`
- `strafe_and_shoot`
- `retreat`
- `get_threat_assessment`
- `get_navigation_info`
- `take_action`

`probe_model()`:

- Requires `GEMINI_API_KEY`.
- Uses `google-genai`.
- Sends a tiny prompt: `Return ok.`
- Returns model and response.

`decide(system_prompt, llm_input)`:

- If no API key is configured, returns fallback `explore`.
- Sends the rendered system prompt plus current state JSON.
- Parses the model output as JSON.
- On any Gemini/API/parsing exception, returns fallback `explore` with the error summarized in `reasoning_summary`.

The fallback path is important because it lets long test runs continue even when Gemini is temporarily unavailable or rate-limited.

`parse_decision(text)`:

- Removes Markdown code fences if present.
- Extracts the first JSON object.
- Parses it.
- Validates `mcp_tool` against `ALLOWED_TOOLS`.
- Defaults unknown tools to `explore`.
- Ensures `mcp_params` is a dictionary.

Expected Gemini output:

```json
{
  "reasoning_summary": "brief explanation",
  "mcp_tool": "explore",
  "mcp_params": {},
  "observed_issue": null
}
```

## Agent Prompt

The prompt file is:

```text
app/prompts/agent_system_prompt.md
```

It is rendered by:

```text
app/services/prompt_service.py
```

Template values:

- `{map_name}`
- `{iwad_used}`
- `{difficulty_level}`
- `{estimated_difficulty}`
- `{thing_count_enemies}`
- `{enemy_breakdown_summary}`
- `{hitscanner_percent}`
- `{health_ratio}`
- `{ammo_ratio}`
- `{secret_sector_count}`
- `{map_width_units}`
- `{map_height_units}`
- `{total_health_pickup_pts}`

The prompt tells the model to act as a QA playtester and to:

- navigate the full map
- engage enemies tactically
- find secrets
- stress-test geometry
- preserve evidence
- prefer compound MCP tools
- report map design problems through `observed_issue`

Compound tools are preferred because raw single-tic actions are too slow when each LLM call is throttled.

If Gemini sets `observed_issue`, `CollectorService` creates a `defects` row with:

- `defect_type='agent_observed'`
- severity `2`
- priority `2`
- title `Agent-observed issue`
- description from the model
- current tick and position

## Collector Service

Runtime event collection is in:

```text
app/services/collector_service.py
```

Responsibilities:

- normalize game variables
- detect event type
- insert `game_events`
- insert `agent_position_trail` every 10 ticks
- insert agent-observed defects
- attach notable screenshots

### Variable Normalization

`normalize_variables(state)` accepts multiple key variants from MCP/ViZDoom:

- Position:
  - `POSITION_X`
  - `position_x`
  - `x`
- Angle:
  - `ANGLE`
  - `angle`
  - `player_angle`
- Health:
  - `HEALTH`
  - `health`
- Armor:
  - `ARMOR`
  - `armor`
- Ammo:
  - `AMMO0`, `ammo_bullets`, `bullets`
  - `AMMO1`, `ammo_shells`, `shells`
  - `AMMO2`, `ammo_rockets`, `rockets`
  - `AMMO3`, `ammo_cells`, `cells`
- Counts:
  - `KILLCOUNT`, `kill_count`, `kills`
  - `ITEMCOUNT`, `item_count`, `items`
  - `SECRETCOUNT`, `secret_count`, `secrets`
- Weapon:
  - `SELECTED_WEAPON`
  - `weapon_selected`

It also derives:

- `level_completed`
- `map_exit`

### Event Detection

`detect_event(current)` returns:

- `map_exit` if level completion/map exit is detected.
- `death` if health is 0 or below.
- `normal` for the first event if no previous state exists.
- `kill` if kill count increased.
- `secret_found` if secret count increased.
- `item_pickup` if item count increased.
- `damage_taken` if health decreased.
- `stuck` if position remains almost unchanged for 30 consecutive backend ticks.
- `normal` otherwise.

Damage amount is stored in `damage_received`.

## Recording Service

Recording is in:

```text
app/services/recording_service.py
```

It uses OpenCV headless.

The MP4 file path is:

```text
storage/recordings/{run_id}.mp4
```

OpenCV first writes an intermediate MPEG-4 Part 2 file:

```text
storage/recordings/{run_id}.source.mp4
```

On `finalize()`, the service transcodes that source file to browser-playable H.264:

```text
codec: h264 / libx264
pixel format: yuv420p
container: mp4
movflags: +faststart
```

The final served file is always expected at:

```text
storage/recordings/{run_id}.mp4
```

If `ffmpeg-python` is installed, the service uses it. If not, it falls back to the `ffmpeg` command-line binary. If both transcoding paths fail, the source file is returned as a last-resort recording rather than deleting evidence.

Important methods:

- `start_from_frame(frame)`
  - Creates a `cv2.VideoWriter`.
  - Writes the intermediate source file with `mp4v`, because that codec is broadly available in OpenCV builds.
  - Uses the actual frame dimensions.
- `write_frame(frame)`
  - Starts the writer lazily on the first frame.
  - Converts RGB to BGR for OpenCV.
  - Writes to MP4.
- `save_screenshot(frame, event_id)`
  - Saves PNG to `storage/screenshots/{event_id}.png`.
- `finalize()`
  - Releases the writer.
  - Transcodes the intermediate source to H.264.
  - Deletes the source file after successful transcode.
  - Returns the browser-playable path.

Helper functions:

- `png_bytes_to_frame(png_bytes)`
  - Decodes MCP screenshot PNG bytes into RGB numpy frame.
- `jpeg_b64(frame, max_width=480)`
  - Resizes wide frames.
  - Encodes JPEG at quality 70.
  - Returns base64 ASCII.

## WebSocket Live Feed

Router:

```text
app/routers/ws.py
```

Service:

```text
app/services/websocket_service.py
```

Endpoint:

```text
WS /ws/runs/{run_id}
```

Connection behavior:

- Accepts the WebSocket.
- Stores it in a `dict[str, set[WebSocket]]`.
- Keeps the connection alive by waiting for client text messages.
- Removes the connection on disconnect.

Broadcast behavior:

- `websocket_service.broadcast(run_id, payload)` sends JSON text to every connected client for that run.
- Dead sockets are removed automatically.

### State Message

State messages are sent every backend loop.

Shape:

```json
{
  "type": "state",
  "tick": 342,
  "status": "running",
  "health": 78,
  "armor": 50,
  "kills": 3,
  "ammo": {
    "bullets": 120,
    "shells": 20,
    "rockets": 0,
    "cells": 0
  },
  "position": {
    "x": -512.0,
    "y": 1024.0,
    "angle": 180
  },
  "event_type": "normal",
  "llm_reasoning": "reasoning summary",
  "action": {
    "mcp_tool": "explore",
    "mcp_params": {}
  },
  "screenshot_b64": null
}
```

`screenshot_b64` is only populated for:

- `kill`
- `death`
- `damage_taken`

Normal ticks do not include screenshots.

### Frame Message

Frame messages are separate from state messages.

Shape:

```json
{
  "type": "frame",
  "tick": 342,
  "mime_type": "image/jpeg",
  "frame_b64": "..."
}
```

Frame messages are throttled by `LIVE_FRAME_FPS`. This lets the frontend show the agent playing live without streaming full PNG images every tick.

## Trace APIs

Trace endpoints are in:

```text
app/routers/runs.py
```

### Paginated Trace

```http
GET /runs/{run_id}/trace?page=1&page_size=100
```

Returns `game_events` ordered by `tick_number`.

Response model:

```text
TraceEntryOut
```

Includes:

- player state
- event type
- `llm_input_summary`
- `llm_reasoning`
- `action_taken`
- damage/kill metadata

### Filtered Events

```http
GET /runs/{run_id}/events?type=kill,death,damage_taken
```

If `type` is omitted, it returns all events for the run.

If `type` is present, it filters `game_events.event_type`.

### Position Trail

```http
GET /runs/{run_id}/position-trail
```

Returns downsampled path points from `agent_position_trail`.

### Defects

```http
GET /runs/{run_id}/defects
```

Returns all defects for a run ordered by severity.

This endpoint is the frontend source for the dynamic defect table. The frontend should not parse the PDF to display defects.

## Recording And Report APIs

### Recording

```http
GET /runs/{run_id}/recording
```

Returns:

```text
video/mp4
```

The endpoint validates:

- run exists
- `recording_mp4_path` is set
- file exists on disk

### Report Metadata

```http
GET /runs/{run_id}/report
```

Returns `ReportOut`.

If no report exists yet, it generates one synchronously and commits it.

### Report PDF

```http
GET /runs/{run_id}/report/pdf
```

Returns:

```text
application/pdf
```

The endpoint validates:

- report exists
- `pdf_path` is set
- file exists on disk

## Defect Detection

Service:

```text
app/services/defect_service.py
```

`detect_for_run(run)` loads all events for a run and applies rule-based checks.

Current rules:

### Repeated Death Location

Detection:

- Group `death` events into approximate 50-unit coordinate buckets.
- If more than one death occurs in the same bucket, create a defect.

Defect:

- `defect_type='repeated_death_location'`
- severity 2
- priority 1

### Ammo Starvation

Detection:

- If bullets + shells + rockets + cells equals 0 for more than 60 consecutive events.

Defect:

- `defect_type='ammo_starvation'`
- severity 2
- priority 2

### Health Deficit

Detection:

- If health remains below 10 HP for more than 30 consecutive events.

Defect:

- `defect_type='health_deficit'`
- severity 3
- priority 3

### Softlock Navigation

Detection:

- Run outcome is `timeout`.
- At least 120 events exist.
- Movement over the final 120 events is less than 20 total units.

Defect:

- `defect_type='softlock_navigation'`
- severity 1
- priority 1

### Unreachable Secrets

Detection:

- Static analysis found one or more secret sectors.
- Runtime `secret_count` never increased above 0.

Defect:

- `defect_type='unreachable_secret'`
- severity 3
- priority 3

### Agent-Observed Issues

These are not detected in `DefectService`. They are inserted directly by `CollectorService` whenever Gemini returns a non-null `observed_issue`.

Defect:

- `defect_type='agent_observed'`
- severity 2
- priority 2

### Defect Deduplication

The database enforces:

```sql
UNIQUE (run_id, defect_type, detected_at_tick)
```

The repository uses PostgreSQL `ON CONFLICT DO NOTHING` for defect inserts. If defect detection runs more than once for the same completed or force-stopped run, the same rule at the same tick is not duplicated.

## Report Generation

Service:

```text
app/services/report_service.py
```

Prompt:

```text
app/prompts/report_generation_prompt.md
```

Report generation logic:

1. Check if a report already exists for the run.
2. Fetch the run.
3. Fetch static analysis.
4. Fetch defects.
5. Fetch all game events ordered by tick.
6. Select notable events where `event_type != 'normal'`, capped at the first 20.
7. Include first 5 ticks and last 5 ticks in the payload.
8. Call Gemini with a compact JSON summary, or fall back if Gemini is unavailable.
9. Render a simple HTML report through Jinja2.
10. Generate PDF through WeasyPrint.
11. Insert `test_reports`.
12. Update `test_runs.report_pdf_path`.

Current Gemini report prompt asks for JSON fields:

```json
{
  "report_purpose": "...",
  "test_items_summary": "...",
  "test_environment_summary": "...",
  "defect_summary_narrative": "...",
  "pass_fail_summary": {
    "map_navigation": "PASS or FAIL",
    "combat_engagement": "PASS or FAIL",
    "resource_balance": "PASS or FAIL",
    "secret_coverage": "PASS or FAIL"
  }
}
```

If Gemini fails, the fallback report includes:

- generic purpose
- map tested
- IWAD and model
- defect count
- map completion pass/fail

The generated PDF is saved to:

```text
storage/reports/{run_id}.pdf
```

## API Surface

### Health

```http
GET /health
GET /health/gemini
```

### WADs

```http
POST /wads/upload
GET /wads/maps?limit=100&offset=0
GET /wads/maps?wad_file_id={wad_id}
GET /wads/{wad_id}
GET /wads/{wad_id}/maps
GET /wads/{wad_id}/map-png?map_name=E1M1
```

### Analysis

```http
GET /wads/{wad_id}/analysis
```

### Runs

```http
POST /runs
GET /runs?limit=100
GET /runs/{run_id}
DELETE /runs/{run_id}
POST /runs/{run_id}/cancel
POST /runs/{run_id}/force-stop
GET /runs/{run_id}/recording
```

### Trace

```http
GET /runs/{run_id}/trace?page=1&page_size=100
GET /runs/{run_id}/events?type=kill,death,damage_taken
GET /runs/{run_id}/position-trail
GET /runs/{run_id}/defects
WS /ws/runs/{run_id}
```

### Reports

```http
GET /runs/{run_id}/report
GET /runs/{run_id}/report/pdf
```

## Serializers

Serializers are Pydantic models in `app/serializers/`.

### `WadFileOut`

Includes:

- id
- original filename
- stored path
- file size
- SHA-256 hash
- validation status/error
- detected maps
- required IWAD
- upload timestamp

### `WadMapOut`

Includes:

- WAD ID
- map name
- required IWAD
- whether analysis exists
- overview PNG URL

### `StaticAnalysisOut`

Includes all static analysis columns plus `map_overview_png_url`.

### `RunCreate`

Input model for `POST /runs`.

Fields:

- `wad_file_id`
- `map_name`
- `difficulty_level`, default 3, range 1 to 5
- `max_ticks`, optional, minimum 1

### `RunOut`

Output model for run listing/detail/create/cancel.

Includes configuration, lifecycle state, outcome, aggregate stats, file paths, and timestamps.

### `TraceEntryOut`

Output model for game event trace rows.

Includes player variables, event type, LLM trace fields, action JSON, and damage metadata.

### `PositionTrailOut`

Output model for downsampled path rows.

### `ReportOut`

Output model for report metadata.

## Repositories

Repositories are thin database access wrappers. They intentionally keep business rules in services.

### `WadRepository`

Methods:

- `get_by_id`
- `get_by_hash`
- `list`
- `create`

### `AnalysisRepository`

Methods:

- `get_by_wad_and_map`
- `list_by_wad`
- `upsert`

### `RunRepository`

Methods:

- `create`
- `update`
- `get_by_id`
- `list`
- `get_active`

`get_active` returns the newest run with status `pending`, `analyzing`, or `running`.

Run lifecycle changes are made through `RunRepository.update()`. This includes setting `running`, terminal status/outcome, aggregate stats, recording path, and report path.

### `GameEventRepository`

Methods:

- `create_event`
- `create_position`
- `create_screenshot`
- `list_trace`
- `list_events`
- `list_position_trail`

### `DefectRepository`

Methods:

- `create`
- `list_by_run`

### `ReportRepository`

Methods:

- `get_by_run`
- `create`
- `update`

`ReportRepository.update()` exists for report lifecycle/status changes. The current report generation path creates the final report row after the PDF is rendered, but the update method is available for explicit `generating`/`failed` state handling.

## Makefile

The backend `Makefile` provides:

```text
make help
make venv
make install
make storage-dirs
make db-init
make db-schema
make run
make clean
```

Important behavior:

- `make install` creates `.venv`, upgrades pip, installs requirements, and creates storage directories.
- `make db-init` runs `scripts/init_db.sh`.
- `make db-schema` applies `sql/schema.sql` using values from `.env`.
- `make run` starts Uvicorn with reload on port 8000.

## Dependencies

Important Python dependencies in `requirements.txt`:

- `fastapi`
- `uvicorn`
- `SQLAlchemy`
- `asyncpg`
- `python-multipart`
- `omgifol`
- `pillow`
- `opencv-python-headless`
- `numpy`
- `google-genai`
- `fastmcp`
- `ffmpeg-python`
- `weasyprint`
- `Jinja2`
- `alembic`

OpenCV uses the headless package so the backend does not require GUI libraries.
Only `asyncpg` is required as the PostgreSQL driver. Sync psycopg drivers are not used.
The H.264 transcode path also requires the system `ffmpeg` binary to be installed.

## Expected Runtime Commands

### Start PostgreSQL Schema

```bash
cd Backend
make db-schema
```

### Start `mcp-doom`

From the `mcp-doom/` directory, the expected pattern is:

```bash
fastmcp run src/doom_mcp/server.py --transport sse --host 0.0.0.0 --port 8001 --path /sse
```

The backend expects the SSE URL:

```env
MCP_DOOM_SSE_URL=http://localhost:8001/sse
```

### Start Backend

```bash
cd Backend
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

or:

```bash
make run
```

## Tested Behavior

The backend has been tested with:

```text
/home/steven/Downloads/MYHOME.wad
```

Observed behavior:

- Upload/dedup works.
- Map detection found `E1M1`.
- IWAD detection selected `freedoom1`.
- Static analysis row was generated.
- Overview PNG was generated.
- `GET /wads/maps` returns the map.
- Invalid map run requests return `400`.
- Gemini health check succeeds when the configured model/key are available.
- Concurrent `/runs` requests produce one `201` and one `409`.
- `max_ticks=999999` clamps to `35000`.
- Run creation starts an async task and returns immediately.
- MCP `start_game` works with `wad=freedoom1` and `scenario_wad=<uploaded path>`.
- Game events include `llm_input_summary`, `llm_reasoning`, and `action_taken`.
- WebSocket emits:
  - `state`
  - throttled `frame`
  - terminal state
- MP4 recording endpoint returns `video/mp4`.
- MP4 recordings are transcoded to H.264/yuv420p for browser playback.
- Report PDF endpoint returns `application/pdf`.
- Force-stop/cancel returns a cancelled run, computes stats, and generates a report.

Known runtime note:

- Gemini can return `429 RESOURCE_EXHAUSTED` if the API quota/rate limit is hit. The backend catches this and uses fallback `explore` actions so the run can continue.

## Design Decisions

### One Active Run

Only one active run is allowed because the ViZDoom/MCP runtime is treated as one active game instance.

The backend enforces this in application code and with a PostgreSQL advisory transaction lock. The lock prevents a race where two clients call `/runs` at the same time.

### Persistent MCP Service

The backend connects to `mcp-doom` as a service over SSE. It does not launch or own the MCP server process.

This avoids:

- slow per-run startup
- fragile subprocess management
- confusing ownership of ViZDoom state

### Store Full Trace, Not Full Images

The database stores every tick's structured state and LLM decision. It does not store every screenshot.

Reasons:

- Thousands of PNG files per run would be wasteful.
- MP4 is better for playback.
- Notable screenshots are enough for defect evidence.
- WebSocket live frames are compressed JPEG and throttled.

### WebSocket Is Live-Only

The WebSocket is a live push channel. It broadcasts messages while `agent_run_task` is running. It is not the source of truth for historical or already-completed runs.

Frontend contract:

- Use `WS /ws/runs/{run_id}` only for an active live run.
- If the page loads after a run already completed, fetch run state through REST:
  - `GET /runs/{run_id}`
  - `GET /runs/{run_id}/trace`
  - `GET /runs/{run_id}/position-trail`
  - `GET /runs/{run_id}/defects`
  - `GET /runs/{run_id}/recording`
  - `GET /runs/{run_id}/report`
- Do not rely on a completed run's terminal WebSocket broadcast being replayed to late subscribers.

### Prompt File Is Editable

The system prompt is Markdown in `app/prompts/agent_system_prompt.md`, not hardcoded into Python. This makes it easy to tune the QA behavior without changing service code.

### Report Prompt Is Compact

The report service does not dump all ticks into Gemini. It uses compact run metadata and counts, with room to expand to notable events and selected tick samples.

## Current Limitations And Future Improvements

### Static Analysis

Current analysis uses omgifol and local fallback metrics. It does not currently shell out to or import the real `dmon` project. The field names and calculations are dmon-style, but the implementation is local.

Future work:

- Integrate actual dmon if available.
- Store raw dmon output.
- Improve ammo ratio calculations by weapon/ammo type.
- Improve enemy classification coverage.

### Report Completeness

The database schema supports many report sections, but the current `ReportService` fills the core sections only.

Future work:

- Populate every `test_reports` column from structured Gemini JSON.
- Include all defects in the PDF with better formatting.
- Add screenshots and map overview to the PDF.
- Include selected reasoning quotes from notable ticks.

### LLM Conversation Memory

The current loop sends the system prompt and current compact state every call, with the last 5 trace entries in `recent_trace`. There is no long conversation object persisted through Gemini.

Future work:

- Maintain a bounded conversation history in memory.
- Summarize long runs every N ticks.
- Add explicit tactical mode state such as `exploring`, `fighting`, `recovering`, or `stuck`.

### WebSocket Lifecycle

The WebSocket route waits for client messages to keep the connection open. Broadcasts are pushed from the run task. The channel is intentionally live-only; REST endpoints are the historical source of truth for completed runs.

Future work:

- Send periodic ping/status messages.
- Close sockets automatically after terminal run state.

### Testing

Current validation has been done with direct curl/Python scripts against the local service.

Future work:

- Add automated pytest integration tests.
- Add a fake MCP client for deterministic backend tests.
- Add a fake Gemini service for parser and loop testing.
- Add upload tests with tiny synthetic WAD fixtures.

## Troubleshooting

### `GET /health/gemini` returns model not found

Cause:

- `LLM_MODEL` is wrong or unavailable for the configured Gemini API version/key.

Fix:

- Use a currently available model such as `gemini-2.5-flash`.
- Restart the backend after changing `.env`.

### `/runs` returns `409 Conflict`

Cause:

- Another run is `pending`, `analyzing`, or `running`.

Fix:

- Wait for it to finish.
- Or call:

```http
POST /runs/{run_id}/force-stop
```

### `/runs/{id}/recording` returns `404`

Possible causes:

- Run has not produced a frame yet.
- Run failed before video writer started.
- `recording_mp4_path` is missing.
- File was deleted from disk.

### `/runs/{id}/report/pdf` returns `404`

Possible causes:

- Report generation has not run.
- `pdf_path` is missing.
- File was deleted from disk.

Try:

```http
GET /runs/{id}/report
```

which generates report metadata if missing.

### WebSocket has no frames

Possible causes:

- No frontend/client connected before the run completed.
- MCP did not return screenshot bytes.
- Run completed too fast.
- `LIVE_FRAME_FPS` is set too low.

### Gemini rate limit

Symptom:

- Trace rows contain reasoning like `Gemini call failed... 429 RESOURCE_EXHAUSTED`.

Behavior:

- Backend falls back to `explore`.
- Run continues.

Fix:

- Reduce run frequency.
- Use a key/project with more quota.
- Add stronger backoff logic in `GeminiService`.

## End-To-End Data Flow

Full happy path:

```text
POST /wads/upload
    -> validate PWAD
    -> SHA-256 dedupe
    -> save storage/wads/{uuid}.wad
    -> omgifol detects maps
    -> detect iwad_required
    -> insert wad_files
    -> analyze all maps
    -> insert static_analysis_results
    -> render overview PNG

GET /wads/maps?limit=100&offset=0
    -> frontend chooses map

POST /runs
    -> advisory lock
    -> ensure no active run
    -> validate map name
    -> clamp max_ticks
    -> create test_runs pending
    -> create asyncio task
    -> return run_id

agent_run_task
    -> connect MCP SSE
    -> start_game(wad, scenario_wad, map_name, difficulty)
    -> status running
    -> render system prompt
    -> loop:
        -> get_state
        -> Gemini decision
        -> MCP tool call
        -> collect game event
        -> write position trail every 10 ticks
        -> save notable screenshot
        -> write MP4 frame
        -> broadcast state
        -> broadcast throttled frame
    -> stop_game
    -> finalize MP4
    -> aggregate run stats
    -> defect detection
    -> report generation
    -> terminal WebSocket state

Frontend after run
    -> GET /runs/{id}
    -> GET /runs/{id}/trace
    -> GET /runs/{id}/position-trail
    -> GET /runs/{id}/recording
    -> GET /runs/{id}/report/pdf
```
