doom mcp services
Configure
Enabled
1. start_game
Start a new Doom game. Use scenario for built-in mini-scenarios, or wad+map_name for full campaign.
2. get_state
Get the current game state: screenshot + full structured data. Returns a screenshot image and game state dict containing: - game_variables: health, armor, position, angle, ammo, weapons, kills, etc. - objects: all entities with distance, angle_to_aim, type, threat level, HP - depth: spatial awareness (min/mean distance per screen region) - episode_finished, tic, total_reward Each object includes computed fields: - distance: units from player - angle_to_aim: degrees to turn to face it (positive=right, negative=left) Pass this value directly to TURN_LEFT_RIGHT_DELTA to aim at the object. - type/threat/attack_type/typical_hp/description: from enemy database - is_visible: whether currently on screen
3. take_action
Execute an action and return the resulting game state.
4. get_objects
Get all objects in the game world with enriched info. Each object includes: - distance from player, angle_to_aim (degrees to turn to face it) - type (monster/item/projectile/weapon/player/decoration) - threat level, attack type, typical HP, description - is_visible (on screen), screen bounding box if visible - raw position, velocity, angle
5. get_map
Get the automap (top-down view) of the level.
6. new_episode
Start a new episode in the current game. Resets the level while keeping the same configuration.
7. get_available_actions
Get the list of available action buttons with types and usage. Returns button names, whether each is binary or delta, sign conventions for delta buttons, and a usage example.
8. aim_and_shoot
Aim at an enemy and fire multiple shots. Handles aiming, firing, and weapon cooldown automatically. This is a compound action - it runs many game tics internally in milliseconds, so the player doesn't stand idle between LLM decisions. Typical workflow: get_state -> find enemy -> aim_and_shoot(enemy_id) -> assess result.
9. move_to
Move toward an object by ID. Handles pathfinding, turning, and stuck recovery automatically. This is a compound action - it runs many game tics internally in milliseconds. Typical workflow: get_state -> find object -> move_to(object_id) -> assess result.
10. explore
Explore the environment autonomously. Walks forward, avoids walls, scans for threats and items. This is a compound action - it runs many game tics internally in milliseconds. Uses depth buffer for wall avoidance and stuck detection for recovery. Typical gameplay loop: explore -> enemy_spotted -> aim_and_shoot -> explore -> item_found -> move_to.
11. strafe_and_shoot
Strafe laterally while firing at an enemy. Better than aim_and_shoot against hitscan enemies. This is a compound action - it runs many game tics internally in milliseconds. The player dodges left/right while keeping the target in the crosshair and firing.
12. retreat
Retreat from the current position. Turn and run or backpedal. This is a compound action - it runs many game tics internally in milliseconds.
13. get_threat_assessment
Analyze all visible threats and return prioritized tactical intelligence. No game tics are consumed. Call freely between actions to assess the situation. Returns: threat_level: Overall threat - "none", "low", "medium", "high", or "critical". threats: Sorted list of enemies with id, name, distance, angle_to_aim, attack_type, priority_rank, priority_score. incoming_projectiles: Active projectiles to dodge. tactical_advice: String list with prioritized recommendations. player_health, player_armor, selected_weapon_ammo.
14. get_navigation_info
Get spatial navigation intelligence. Tracks exploration across calls. No game tics are consumed. Call to check exploration progress, find unexplored areas, locate keys, and detect nearby doors. Returns: cells_explored: Number of 128-unit grid cells visited. explored_directions / unexplored_directions: Cardinal directions from current cell. suggested_direction: Best unexplored direction aligned with player facing. keys_found: Keys picked up this episode. known_key_locations: Visible keys not yet picked up. nearby_doors: Detected doors within 512 units. total_doors_found: All doors detected this episode.
15. get_situation_report
Get a situation report for directing the autonomous executor. Use this instead of get_state when the executor is running (async_player=True). Returns screenshot + compact summary of executor state, recent events, game variables, nearby objects, and exploration progress. The executor plays autonomously at 35 Hz. Use this tool every few seconds to monitor progress and decide whether to change objectives or strategy. Returns screenshot + dict with: executor_state: Current state (idle/exploring/fighting/collecting/retreating/moving_to). objectives: Current objective queue. strategy: Current strategy parameters. events: Recent events since last call (kills, damage, state changes, etc). game_variables: Health, ammo, position, etc. objects: Nearby filtered objects. exploration: Cells explored, directions, keys, doors.
16. set_objective
Set an objective for the autonomous executor. The executor will work toward this objective while handling combat and navigation autonomously. Higher priority objectives are executed first. Multiple objectives can be queued. Requires async_player=True (game started with autonomous executor).
17. set_strategy
Tune the autonomous executor's behavior. Requires async_player=True (game started with autonomous executor).
18. get_map_knowledge
Get accumulated map knowledge for strategic planning. Returns exploration data including position, cells explored, unexplored directions, known keys, doors, and current executor state/objectives. No game tics are consumed. Use for planning which areas to explore next.
19. stop_game
Stop the current game and release resources

Phase 1 — WAD upload + storage layer
Files to create:

app/routers/wads.py — POST /wads/upload (multipart form), GET /wads/{id}, GET /wads/{id}/map-png
app/services/wad_service.py — sha256 dedup logic, save binary to storage/wads/{uuid}.wad, validate WAD header (check PWAD magic bytes), reject UDMF maps
app/repositories/wad_repository.py — create_or_get_by_hash(), get_by_id()
app/serializers/wad_serializers.py — WadFileOut Pydantic schema

Libraries: python-multipart (FastAPI file upload), hashlib (stdlib, no install).

Phase 2 — Static analysis (omgifol + dmon)
Files to create:

app/services/analysis_service.py — this is where both libraries live

Inside analysis_service.py:

Call omgifol → extract thing counts by type, linedef/sector/vertex counts, secret sector count, map bounding box from vertex coordinates, list of map names (detected_maps)
Call dmon → monster HP totals, hitscanner %, health/ammo ratios, difficulty label
Call omgifol's drawmaps.py logic → render top-down map PNG, save to storage/screenshots/{wad_id}_{map}.png
Use Pillow here too — to post-process the map PNG (resize, add scale bar if needed)


app/repositories/analysis_repository.py — upsert_analysis(), get_by_wad_and_map()
app/routers/analysis.py — GET /wads/{id}/analysis


Phase 3 — Fork tetsuo-doom (PWAD support)
This repo lives outside your app/ folder. Suggested layout:
Agentic-PWAD-QA-Doom/
├── Backend/
│   └── app/
└── tetsuo-doom/        ← your fork, cloned here
Changes needed (≈12 lines total):
In tetsuo_doom/game_manager.py, modify start_game() to accept iwad_path: str = None and pwad_path: str. Call game.set_doom_game_path(iwad_path or DEFAULT_FREEDOOM2_PATH) then game.set_doom_scenario_path(pwad_path).
In tetsuo_doom/server.py, expose both params in the MCP start_game tool definition.
Your run_service.py will launch tetsuo-doom as a subprocess (asyncio.create_subprocess_exec) and communicate over the MCP stdio protocol. This keeps ViZDoom fully isolated from your FastAPI process.

Phase 4 — Agent loop + data collection (the core)
Files to create:

app/services/run_service.py — start_run(run_id) spawns an asyncio.create_task(agent_loop(run_id)), cancel_run(run_id) cancels it
app/services/agent_service.py — wraps Gemini 2.5 Flash. Each iteration: call get_state MCP tool → build prompt with game state → call Gemini → parse action → call step MCP tool. Throttle to 1 LLM call per second with asyncio.sleep.
app/services/collector_service.py — called inside the loop every tick. Reads ViZDoom game variables, detects event type (kill delta, health==0, item delta, position unchanged 30+ ticks), inserts game_events row. Every 10th tick, inserts agent_position_trail row.
app/repositories/game_event_repository.py
app/repositories/position_trail_repository.py

Libraries: google-generativeai (the Gemini SDK), asyncio (stdlib).

Phase 5 — Video recording + screenshots (OpenCV)
Files to create:

app/services/recording_service.py

On run start: cv2.VideoWriter(f'storage/recordings/{run_id}.mp4', cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)).
Each tick: writer.write(frame) where frame = game.get_screen_buffer() (already a numpy array — no ffmpeg, no screen capture, fully headless-safe).
On notable events (kill, death, secret): cv2.imwrite(f'storage/screenshots/{event_id}.png', frame), then insert notable_event_screenshots row.
On run end: writer.release(), update test_runs.recording_mp4_path.
Library: opencv-python.

Phase 6 — REST API + WebSocket live feed
Files to create:

app/routers/runs.py — POST /runs (create + start), GET /runs (list), GET /runs/{id}, DELETE /runs/{id} (cancel)
app/routers/ws.py — WebSocket /ws/runs/{id}. The collector_service publishes state to an asyncio.Queue per run; the WS handler reads from that queue and pushes JSON to the frontend each tick. Payload: {tick, hp, armor, ammo_bullets, kills, x, y, angle, event_type}.

Library: FastAPI's built-in WebSocket support (no extra install).

Phase 7 — Defect detection + report generation (post-run)
Files to create:

app/services/defect_service.py — queries game_events for the run, applies the 6 detection rules from the schema doc (repeated death location, stuck geometry, ammo starvation, health deficit, softlock, unreachable secrets). Inserts defects rows.
app/services/report_service.py — builds a large structured prompt from: static analysis data + aggregated game_events + defects list + run metadata. Calls Gemini once. Parses the JSON response into all 7 report sections. Renders an HTML template (Jinja2), then calls WeasyPrint to produce the PDF at storage/reports/{run_id}.pdf.
app/repositories/defect_repository.py, app/repositories/report_repository.py
app/routers/reports.py — GET /runs/{id}/report (returns metadata + PDF download link)

Libraries: WeasyPrint (HTML→PDF), Jinja2 (HTML templating), google-generativeai.

Phase 8 — React frontend
Separate repo or Frontend/ folder. Vite + React + Tailwind + recharts.
Pages and what goes on each:
Upload page — drag-and-drop WAD upload → calls POST /wads/upload → shows analysis results + map PNG → "Start Run" button with difficulty selector.
Live run page — connects to WS /ws/runs/{id} → renders live game state panel (HP bar, ammo, kills, current action/reasoning). Shows map PNG with real-time dot for agent position. When run ends, replaces live view with the recorded MP4.
Run history — reads recent_run_ids from localStorage → calls GET /runs/{id} for each → renders run cards (outcome, duration, kills, difficulty).
Run detail — recharts LineChart for HP over time (from game_events), ammo over time. Canvas overlay on the map PNG drawing the agent_position_trail path (color-coded green→red by HP). Defects table. Download buttons for MP4 and PDF report.
Libraries: recharts, Tailwind, native Canvas API for the path overlay (no extra lib needed — fetch position trail, draw polyline on canvas layered over the map PNG <img>).

File placement summary
LibraryLives inomgifolapp/services/analysis_service.pydmonapp/services/analysis_service.pygoogle-generativeaiapp/services/agent_service.py + report_service.pyvizdoomtetsuo-doom/ (forked, run as subprocess)opencv-pythonapp/services/recording_service.pyWeasyPrintapp/services/report_service.pyPillowapp/services/analysis_service.py (map PNG post-processing)Jinja2app/services/report_service.py (HTML report template)asyncpg + SQLAlchemyapp/core/database.py (already started)

What you do NOT need

No Celery — one asyncio.create_task per run, one game at a time
No vector DB — plain PostgreSQL queries by run UUID
No ffmpeg — OpenCV writes directly from the ViZDoom framebuffer
No Redis — use asyncio.Queue for the WebSocket live feed within the process

Start with Phase 1 and 2 — you can test WAD upload and static analysis without touching ViZDoom at all, which lets you validate the DB, serializers, and API independently first.You said: update this as it needs some refiningupdate this as it needs some refining 
remove this its already is controlled from the other repo which is tutso "FREEDOOM2_WAD_PATH (absolute path to freedoom2.wad installed with ViZDoom)"
i changed tutesto repo name to mcp-doom
also there is no place for the starting prompt also in my mind i wanted the pipline as static analysis and its data go to the llm inside the starting prompt and to how he would act and how the report he is going to write
also i want the final tics or time to be controlled from the ui which should be accepted from the endpoint but dont leave it open there is a max cause the tokens and so
also would this make us save the all the agent loop the output data and mcp calls and llm thought process and to can actually show it on the ui
also make sure this backedn when finalzied and connectedShow less9:29 AM2 / 2Claude responded: These are sharp refinements.These are sharp refinements. Let me think through each one before writing the plan update.
A few quick clarifications so the plan is exactly right:Good, I have everything I need. Here is the fully refined plan.

Phase 1 — WAD upload + storage layer
No changes from before. Files stay exactly as planned:

app/routers/wads.py
app/services/wad_service.py — sha256 dedup, save to storage/wads/{uuid}.wad, validate PWAD magic bytes, reject UDMF
app/repositories/wad_repository.py
app/serializers/wad_serializers.py


Phase 2 — Static analysis (omgifol + dmon)
No changes. app/services/analysis_service.py runs omgifol then dmon, renders the map PNG via omgifol's drawmaps logic, post-processes with Pillow. Results go to static_analysis_results via app/repositories/analysis_repository.py.
One addition: after analysis completes, the service also serializes the full analysis result into a structured dict that gets stored on the test_runs row (or passed forward). This exact dict is what gets injected into the starting prompt in Phase 3. No re-querying needed at game start.

Phase 3 — mcp-doom fork (PWAD support)
The repo is mcp-doom/ (renamed from tetsuo-doom), sitting alongside Backend/:
Agentic-PWAD-QA-Doom/
├── Backend/
│   └── app/
├── mcp-doom/          ← your fork
└── Frontend/
Changes to mcp-doom stay minimal — only game_manager.py and server.py, ~12 lines. FREEDOOM2_WAD_PATH stays entirely inside mcp-doom's own config, not touched by your backend. Your run_service.py passes only the pwad_path (the uploaded WAD's absolute disk path). mcp-doom resolves the IWAD itself.

Phase 4 — Starting prompt + agent loop
This is where the new pipeline thinking lands.
The starting prompt — app/prompts/
Create a folder app/prompts/ with a Jinja2 template file:
app/prompts/
└── agent_system_prompt.j2
This template gets rendered once at run start with the full static analysis data injected. It covers three things in one prompt:
Section A — Who you are and what you're doing. The agent is told it is a QA testing agent playing a Doom map. Its job is not just to survive — it is to explore every area, stress-test every encounter, find navigation problems, and gather data for a structured QA report.
Section B — The map briefing (from static analysis). The template injects: total enemy count by type, hitscanner percentage, estimated difficulty label from dmon, health/ammo balance ratios, total secret sectors, map dimensions. The agent goes in knowing the map is e.g. "hard difficulty, 47 enemies (60% hitscanners), 3 secrets, small map (512×768 units), ammo is tight." This shapes its behavior — it will play more cautiously on a hard map, prioritize secret-hunting, etc.
Section C — Report instructions. The agent is told exactly what the final QA report needs: which sections exist, what constitutes a defect (death at same location twice = severity 2, stuck geometry = severity 1, etc.), and that it should narrate its reasoning at each decision so the report has quotable reasoning chains.
The agent_service.py renders this template at run start, passes it as the system message to Gemini, and keeps it stable for the entire run (it's the system prompt, not re-sent each tick).
The agent loop — app/services/agent_service.py
Each iteration of the loop:

Call get_state via mcp-doom → receive structured game state JSON
Build the user message for this tick: current game state + recent event summary (last 5 events) + current tick number
Call Gemini 2.5 Flash with the system prompt (from template) + conversation history
Parse Gemini's response — it should contain: <reasoning> (chain of thought), <action> (the MCP tool call to make), optionally <observation> (what it noticed)
Execute the action via step mcp-doom MCP tool
Persist the full trace (see Phase 4b below)
asyncio.sleep(1) — throttle to 1 LLM call per second

Tick limit — controlled from the UI
POST /runs accepts a body like:
json{
  "wad_file_id": "uuid",
  "map_name": "MAP01",
  "difficulty_level": 3,
  "max_ticks": 5000
}
The backend enforces: max_ticks = min(requested_max_ticks, 10000). Hard ceiling is 10,000 ticks (~10 min). If the frontend sends nothing, default is 3,000. The run_service.py loop checks tick_number >= run.max_ticks each iteration and terminates cleanly, setting outcome = 'timeout'.
This means the test_runs table gets a max_ticks INTEGER NOT NULL DEFAULT 3000 column added.

Phase 4b — Full agent trace storage (new, replaces vague "persist data")
Every LLM decision tick gets a complete structured record inserted into game_events. The action_taken JSONB and llm_reasoning TEXT columns from the schema already exist, but now they carry the full trace:
action_taken stores:
json{
  "mcp_tool": "step",
  "mcp_params": {"MOVE_FORWARD_BACKWARD_DELTA": 10, "ATTACK": 1},
  "mcp_response_summary": "moved forward, no kill"
}
llm_reasoning stores the raw Gemini output — the full <reasoning> block including chain-of-thought. This is what gets quoted in the report ("At tick 342, the agent observed 3 enemies and chose to retreat: [reasoning]") and displayed in the UI trace panel.
A new field is also added to game_events: llm_input_summary TEXT — a compact snapshot of what was sent to Gemini that tick (game state JSON, compressed). This makes the trace fully reconstructable: input → reasoning → action → outcome.
On the non-LLM ticks (throttled ticks where the game runs but Gemini isn't called), action_taken, llm_reasoning, and llm_input_summary are all NULL. The collector still records the game variables (HP, position, ammo) every tick for the charts.

Phase 5 — Video + screenshots (OpenCV)
Unchanged. app/services/recording_service.py, cv2.VideoWriter from game.get_screen_buffer(). Notable event screenshots at kills, deaths, secrets found.

Phase 6 — REST API + WebSocket
POST /runs now accepts max_ticks in the body (validated, capped at 10,000).
The WebSocket payload at WS /ws/runs/{id} is extended to include the agent trace for the current tick:
json{
  "tick": 342,
  "hp": 45,
  "armor": 0,
  "ammo_bullets": 12,
  "kills": 3,
  "x": 1024.5,
  "y": -512.0,
  "event_type": "kill",
  "llm_reasoning": "I see an imp at close range. Shotgun is best here...",
  "mcp_tool": "step",
  "mcp_params": {"ATTACK": 1}
}
This is what feeds the live trace panel in the UI. The full reasoning is available live, not just after the run ends.
New endpoints:

GET /runs/{id}/trace — returns all game_events rows for a run (paginated), with full llm_reasoning and action_taken. Powers the post-run trace viewer.
GET /runs/{id}/events?type=kill,death,secret — filtered notable events only. Powers the summary view.


Phase 7 — Defect detection + report generation
Unchanged structurally. One important addition: the report prompt to Gemini now includes a sample of llm_reasoning chains from key moments in the run (the 10 most notable ticks by event type). This means the report can contain direct quotes from the agent's own reasoning — which is both academically interesting and makes the report feel alive rather than just a stats dump.
app/prompts/ gets a second template:
app/prompts/
├── agent_system_prompt.j2    ← primes the agent at run start
└── report_generation_prompt.j2  ← structures the post-run report call to Gemini

Phase 8 — React frontend
The UI now has a proper trace panel, connected to the backend:
Live run page:

Left panel: game frame (base64 from WebSocket or MJPEG stream)
Right panel: two tabs — Summary (HP bar, ammo, kills counter, event feed) and Agent trace (scrollable log of each LLM tick: reasoning text + action taken, auto-scrolls to latest)
Bottom: progress bar showing current_tick / max_ticks with a "Stop run" button that calls DELETE /runs/{id}
The tick limit slider/input is on the Upload → Start Run screen, with the UI capping display at 10,000 and a note explaining why

Run detail page (post-run):

The trace panel becomes a full scrollable log fetched from GET /runs/{id}/trace
Toggle between "Notable events only" (from the filtered endpoint) and "Full trace"
Each trace entry: tick number, event type badge, game state snapshot, full reasoning block, action taken
The map PNG with the position trail canvas overlay
recharts HP/armor/ammo over time

CORS: app/main.py includes CORSMiddleware with allow_origins=["http://localhost:5173"] (Vite dev default) and later the production origin. The frontend calls http://localhost:8000 directly — no proxy needed for now.

Updated file tree (additions highlighted)
app/
├── prompts/
│   ├── agent_system_prompt.j2       ← NEW: static analysis injected here
│   └── report_generation_prompt.j2  ← NEW: structures post-run report call
├── routers/
│   ├── wads.py
│   ├── analysis.py
│   ├── runs.py                      ← POST accepts max_ticks (capped at 10,000)
│   ├── ws.py                        ← extended payload with llm_reasoning
│   └── reports.py
├── services/
│   ├── wad_service.py
│   ├── analysis_service.py
│   ├── run_service.py               ← enforces max_ticks ceiling
│   ├── agent_service.py             ← renders agent_system_prompt.j2, runs loop
│   ├── collector_service.py         ← stores full trace per tick
│   ├── recording_service.py
│   ├── defect_service.py
│   └── report_service.py            ← renders report_generation_prompt.j2
├── repositories/
│   ├── wad_repository.py
│   ├── analysis_repository.py
│   ├── run_repository.py
│   ├── game_event_repository.py     ← stores llm_input_summary + full trace
│   ├── position_trail_repository.py
│   ├── screenshot_repository.py
│   ├── defect_repository.py
│   └── report_repository.py
├── serializers/
│   ├── wad_serializers.py
│   ├── run_serializers.py           ← RunCreate includes max_ticks field
│   ├── game_event_serializers.py    ← TraceEntry schema for /runs/{id}/trace
│   └── report_serializers.py
└── core/
    ├── config.py
    └── database.py

What the game_events table gains (schema delta)
Add one column to what the schema doc already defines:
sqlllm_input_summary TEXT  -- compact JSON snapshot of what was sent to Gemini this tick
And test_runs gets:
sqlmax_ticks INTEGER NOT NULL DEFAULT 3000

Build order recommendation

P1 + P2 first — test WAD upload and static analysis with no ViZDoom at all. Validate DB, serializers, API independently.
P3 — fork mcp-doom, verify you can start a game with a custom PWAD path via the MCP tools manually (curl or a test script).
P4 — wire the agent loop. At this stage you'll see the full trace appearing in game_events after a run.
P4b verification — write a quick script that queries game_events for a run and prints the reasoning chain. Confirm it's all there before touching the frontend.
P5 + P6 — recording and WebSocket together (they share the same per-tick callback).
P7 — defect detection and report generation last, since it depends on having real run data.
P8 — frontend last, once all endpoints are stable.
You said: Q: The starting prompt feeds static analysis data to the LLM to prime its behavior and report style.Q: The starting prompt feeds static analysis data to the LLM to prime its behavior and report style. Where should this prompt live?
A: hardcoded in agent service but the prompt itself to be in other md fileQ: For the max ticks / time limit — what should the hard ceiling be?
A: 35,000 ticks (~35 min at 1 LLM call/sec) — conservativeQ: The full agent loop output (MCP calls, LLM thoughts, game state per tick) — how detailed should the UI be?
A: Full trace: every MCP call + LLM reasoning shown in a scrollable log panel9:42 AMClaude responded: Got it.Got it. Three clean updates to fold in:

Changes to the refined plan
Starting prompt — app/prompts/agent_system_prompt.md
The prompt itself lives in a standalone Markdown file:
app/prompts/
└── agent_system_prompt.md      ← the actual prompt text, editable without touching code
agent_service.py reads this file at startup (or at run start), then programmatically injects the static analysis data into it in Python before sending to Gemini — no Jinja2 needed, just Python string formatting or a simple str.format() call with named placeholders in the Markdown file. This means you can freely edit the prompt wording, restructure sections, tune the report instructions — all without opening a .py file. The injection points in the Markdown look like {enemy_count}, {difficulty_label}, {hitscanner_percent}, {health_ratio}, {map_width}, {secret_sector_count} etc.
The Markdown file itself has three sections as described before — identity/role, map briefing (placeholders), report structure instructions. When agent_service.py reads it and fills in the placeholders with the real analysis data, the rendered string becomes the system message sent to Gemini once at run start.
app/prompts/ also gets the report generation prompt the same way:
app/prompts/
├── agent_system_prompt.md       ← agent behavior + map briefing + report instructions
└── report_generation_prompt.md  ← post-run report structure prompt (read by report_service.py)

Max ticks ceiling — 35,000
POST /runs body:
json{
  "wad_file_id": "uuid",
  "map_name": "MAP01",
  "difficulty_level": 3,
  "max_ticks": 5000
}
run_service.py enforces: max_ticks = min(requested, 35000). Default if not sent: 3000. The test_runs table column stays max_ticks INTEGER NOT NULL DEFAULT 3000. The UI slider goes from 500 to 35,000 with a label explaining the token/time tradeoff — e.g. "35,000 ticks ≈ 35 min, uses significantly more LLM tokens."

Full trace UI — every MCP call + LLM reasoning
The live run page right panel is a single scrollable trace log — no tabs, no summary/full toggle. Every LLM decision tick appends a new entry in real time via WebSocket. Each entry contains:
[Tick 342] — event: kill
  State:  HP 45 | Armor 0 | Bullets 12 | Kills 3 | Pos (1024, -512)
  Input:  {compact game state sent to Gemini}
  Reason: "I see an imp at close range. Shotgun is most ammo-efficient here.
            Retreating would cost positioning. Engaging now."
  Action: step({ ATTACK: 1 })
  Result: kill_count delta +1
The post-run detail page fetches the full trace from GET /runs/{id}/trace (all game_events rows, paginated) and renders the same format in a persistent scrollable panel. Every MCP call is visible — both the tool name + params sent, and the response summary back. Nothing is hidden or summarized away.
game_events stores everything needed for this: llm_input_summary, llm_reasoning, action_taken (with mcp_tool, mcp_params, mcp_response_summary keys inside the JSONB), and event_type. The TraceEntry serializer in app/serializers/game_event_serializers.py maps these columns to the frontend-ready shape.

Everything else in the refined plan stays exactly as written. The build order is unchanged — P1 → P2 → P3 → P4 → P4b → P5+P6 → P7 → P8.