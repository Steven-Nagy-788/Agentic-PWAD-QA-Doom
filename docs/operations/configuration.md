# Configuration

Three configuration layers exist — **environment variables** (`.env` file), **database overrides** (`config_entries` table via `/settings` API), and **behavior profiles** (hardcoded presets). Overrides merge on top of env defaults at runtime.

## Environment Variables

### Database

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `doom_agentic_qa` | Database name |
| `POSTGRES_USER` | `doom_agentic` | Database user |
| `POSTGRES_PASSWORD` | `doom_agentic_password` | Database password |
| `DATABASE_URL` | derived | Full asyncpg URL — auto-derived if unset, must be `postgresql+asyncpg://` or `sqlite+aiosqlite://` |

### Storage Paths

| Variable | Default | Description |
|---|---|---|
| `STORAGE_BASE` / `STORAGE_DIR` | `storage` | Root storage directory |
| `WAD_STORAGE_DIR` | `<STORAGE_DIR>/wads` | Uploaded PWAD files |
| `REPORT_STORAGE_DIR` | `<STORAGE_DIR>/reports` | Generated PDF reports |
| `RECORDING_STORAGE_DIR` | `<STORAGE_DIR>/recordings` | MP4 recordings |
| `SCREENSHOT_STORAGE_DIR` | `<STORAGE_DIR>/screenshots` | Screenshot captures |
| `ANALYSIS_STORAGE_DIR` | `<STORAGE_DIR>/analysis` | Analysis artifacts |

All paths are resolved relative to the project root unless absolute. Directories are created and writability-validated at startup.

### LLM

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `LLM_MODEL` | `gemini-2.5-flash-lite` | Model identifier |
| `LLM_THROTTLE_SECONDS` | `2.0` | Minimum seconds between LLM calls |
| `GEMINI_RATE_LIMIT_CALLS_PER_MINUTE` | `15` | Rate limit cap |
| `GEMINI_MAX_CONCURRENCY` | `1` | Max concurrent Gemini requests |
| `GEMINI_RETRY_MAX_DELAY_SECONDS` | `20.0` | Max exponential-backoff delay |
| `LLM_INPUT_COST_PER_MILLION` | `0.10` | Input token cost (USD per million) |
| `LLM_OUTPUT_COST_PER_MILLION` | `0.40` | Output token cost (USD per million) |

### MCP

| Variable | Default | Description |
|---|---|---|
| `MCP_DOOM_SSE_URL` | `http://localhost:8001/sse` | MCP SSE endpoint |
| `MCP_PROBE_TIMEOUT_SECONDS` | `3.0` | SSE connectivity probe timeout |
| `MCP_TOOL_TIMEOUT_SECONDS` | `30.0` | Per-tool-call timeout |

### App

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Doom Agentic Testing Backend` | Application title |
| `APP_ENV` | `development` | Environment label (`dev`, `production`, etc.) |
| `DEBUG` | `false` | Debug mode — sets CORS origins, enables dev routes |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `SENTRY_DSN` | — | Sentry DSN (optional, skipped if unset or missing package) |

### Recording

| Variable | Default | Description |
|---|---|---|
| `LIVE_FRAME_FPS` | `10.0` | Frame rate for live WebSocket streaming |
| `RECORDING_FPS` | `30.0` | Frame rate for saved MP4 recordings |
| `RECORDING_TELEMETRY_STRIDE` | `1` | Tick interval between telemetry samples |

### Run

| Variable | Default | Description |
|---|---|---|
| `MAX_RUN_TICKS` | `35000` | Hard cap on tick count per run |
| `DEFAULT_RUN_TICKS` | `3000` | Default tick limit per run |
| `DEFAULT_AGENT_BEHAVIOR` | `thorough` | Behavior profile name |
| `IWAD_USED` | `freedoom2` | IWAD identifier for test metadata |

## Database Overrides

Stored in the `config_entries` table (key-value pairs, JSONB values). Queried and merged on top of env defaults by `GET /settings`. Updated via `PATCH /settings`.

| Key | Type | Description |
|---|---|---|
| `llm_model` | `str` | Override LLM model identifier |
| `llm_throttle_seconds` | `float` | Override LLM throttle delay |
| `gemini_rate_limit_calls_per_minute` | `int` | Override Gemini rate limit |
| `llm_input_cost_per_million` | `float` | Override input token cost |
| `llm_output_cost_per_million` | `float` | Override output token cost |
| `max_run_ticks` | `int` | Override run tick cap |
| `default_run_ticks` | `int` | Override default run ticks |
| `live_frame_fps` | `float` | Override live stream FPS |
| `recording_fps` | `float` | Override recording FPS |
| `recording_telemetry_stride` | `int` | Override telemetry stride |
| `default_agent_behavior` | `str` | Override behavior profile |
| `iwad_used` | `str` | Override IWAD identifier |

All values are optional — only supplied keys override their env counterparts. Use `GET /settings/behavior-profiles` to list available behavior profiles.

## Behavior Profiles

Three hardcoded profiles in `app/core/behavior_profiles.py`.

| Profile | Default Stride | Combat Stride | Stuck Stride | Throttle (default) | Goal |
|---|---|---|---|---|---|
| `thorough` | 1 | 1 | 2 | 1.5 s | Methodical, every room, maximum coverage |
| `fast` | 5 | 2 | 10 | 0.4 s | Breadth-first, covers ground quickly |
| `exploit_focused` | 1 | 1 | 1 | 0.1 s | Aggressive boundaries, crash bugs, softlocks |

### THOROUGH

System prompt emphasizes slow exploration, checking every corner, interactable, and geometry seam. Low throttle in combat (0.5 s), high when stuck (2.0 s).

### FAST

Prioritises covering new cells over re-examining. Higher stride values skip ticks between actions. Fast throttle (0.1–0.8 s range).

### EXPLOIT_FOCUSED

Aggressive stress-testing: wall-hugging, spam-use, repeated boundary probing. Minimal delays (0.05–0.2 s) for maximum action frequency.
