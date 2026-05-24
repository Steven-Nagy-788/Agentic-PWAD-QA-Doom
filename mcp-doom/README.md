# doom-mcp

FastMCP server that wraps ViZDoom for the Agentic PWAD QA backend. Agents receive structured game state (objects, depth, sectors, variables) plus screenshots, then send named actions back - no raw button arrays or pixel parsing required.

## Features

- **Full game state as structured data** -object positions with distance/angle-to-aim, depth buffer stats, sector geometry, 39 tracked game variables (health, ammo, position, velocity, kills, etc.)
- **Screenshots as PNG images** -returned alongside structured state for visual grounding
- **Delta buttons for precise control** -continuous turn/move values in degrees, not just binary left/right
- **Enemy database** -70+ entity types with threat level, attack type, typical HP, and descriptions
- **Campaign mode** -play through all 32 Doom II maps (or 36 Doom I maps) with automatic level progression
- **9 built-in scenarios** -ViZDoom's training scenarios for focused skill development
- **Headless or visible** -run without a display for AI training, or open a window to watch

## Prerequisites

- Python 3.10+
- A working C++ compiler (ViZDoom builds native code)
- On Linux: `libgl1-mesa-dev` and related OpenGL packages

## Installation

```bash

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify the installation:

```bash
python -c "import vizdoom; print(vizdoom.__version__)"
python -c "import fastmcp; print(fastmcp.__version__)"
```

## Quick Start

### With VS Code (Copilot)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "doom": {
      "command": "${workspaceFolder}/.venv/bin/fastmcp",
      "args": ["run", "src/doom_mcp/server.py"]
    }
  }
}
```

### Standalone

```bash
# stdio transport (for MCP clients)
fastmcp run src/doom_mcp/server.py

# SSE transport (for the FastAPI backend)
fastmcp run src/doom_mcp/server.py --transport sse --host 127.0.0.1 --port 8001 --path /sse
```

## Tools

### `start_game`

Start a new Doom game. Use `scenario` for built-in training scenarios, or `wad` + `map_name` for full campaign maps.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scenario` | `string` | `"basic"` | Built-in scenario name (ignored if `wad` is set) |
| `wad` | `string` | `null` | Base IWAD file: `"freedoom1"`, `"freedoom2"`, or absolute path |
| `scenario_wad` | `string` | `null` | Custom PWAD file to load on top of the base IWAD |
| `pwad` | `string` | `null` | Alias for `scenario_wad` |
| `map_name` | `string` | `null` | Map to load (e.g. `"MAP01"`, `"E1M1"`) |
| `difficulty` | `int` | `3` | Doom skill level 1-5 |
| `buttons` | `list[str]` | see below | Action buttons to enable |
| `variables` | `list[str]` | see below | Game variables to track |
| `screen_resolution` | `string` | `"RES_320X240"` | ViZDoom resolution enum |
| `episode_timeout` | `int` | `null` | Max tics per episode |
| `render_hud` | `bool` | `false` | Show HUD overlay |
| `window_visible` | `bool` | `false` | Open a game window |
| `async_player` | `bool` | `false` | Run the game continuously in real time and enable the autonomous executor |
| `ticrate` | `int` | `null` | Async game speed in tics/sec; `35` is normal Doom speed |
| `seed` | `int` | `null` | Random seed |

### `get_state`

Returns a screenshot image and game state dict:

- `game_variables` -health, armor, position, angle, ammo, weapons, kills, etc.
- `objects` -all entities with computed `distance`, `angle_to_aim`, type, threat level, HP
- `sectors` -map geometry (wall lines, floor/ceiling heights)
- `depth` -min/mean distance per screen region (6 regions + crosshair)
- `episode_finished`, `tic`, `total_reward`

### `take_action`

Execute an action and return the resulting state (same format as `get_state`).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | `dict[str, float]` | `null` | Button name to value mapping |
| `tics` | `int` | `1` | Game tics to hold the action |

```jsonc
// Example: turn right 15 degrees, move forward, and shoot
{"actions": {"TURN_LEFT_RIGHT_DELTA": 15, "MOVE_FORWARD_BACKWARD_DELTA": 10, "ATTACK": 1}, "tics": 1}
```

Get all objects in the game world with enriched info: distance, angle to aim, type/threat/HP from the enemy database, visibility, and screen bounding box.

### `list_wad_maps`

List map names (MAP01, E1M1, etc.) found inside a WAD file.

| Parameter | Type | Description |
|-----------|------|-------------|
| `wad_path` | `string` | Path to the .wad file to inspect |

### `get_map`

Get the automap (top-down view) as a PNG image.

### `new_episode`

Start a new episode. In campaign mode, automatically advances to the next map on level completion, or restarts the same map on death.

### `get_available_actions`

Returns configured buttons with types (`delta` or `binary`), sign conventions, and usage examples.

### `get_situation_report`

Return a compact director-facing snapshot for games started with `async_player=true`.

The response includes a screenshot plus:

- `executor_state`
- queued `objectives`, including objective age
- current `strategy`
- recent executor `events`
- `game_variables`
- nearby filtered `objects`
- `exploration`
- `executor_progress`, including position spread, stuck counters, recent stop reasons, and target hints

Use this instead of `get_state` when the autonomous executor is active.

### `set_objective`

Queue a high-level objective for the autonomous executor.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `objective_type` | `string` | required | One of `explore`, `kill`, `move_to_pos`, `move_to_obj`, `collect`, `use_object`, `retreat`, `hold_position` |
| `params` | `dict` | `null` | Objective parameters such as `object_id`, `x`, or `y` |
| `priority` | `int` | `0` | Higher priority objectives run first |
| `timeout_tics` | `int` | `0` | Auto-fail the objective after this many tics; `0` means no timeout |
| `replace` | `bool` | `false` | Clear queued objectives before adding this objective |

### `set_strategy`

Tune autonomous executor behavior while an async game is running.

| Parameter | Type | Description |
|-----------|------|-------------|
| `aggression` | `float` | `0.0` avoids fights, `1.0` engages aggressively |
| `health_retreat_threshold` | `int` | Always retreat below this HP |
| `health_collect_threshold` | `int` | Seek health below this HP |
| `ammo_switch_threshold` | `int` | Switch/seek weapons when ammo is low |
| `engage_range` | `float` | Max distance for combat engagement |
| `collect_range` | `float` | Max distance for item collection |
| `prefer_cover` | `bool` | Favor cover during combat |

### `stop_game`

Stop the current game and release resources.

## Action System

Actions use a dict mapping button names to values:

| Button | Type | Convention |
|--------|------|------------|
| `TURN_LEFT_RIGHT_DELTA` | delta | positive = right, negative = left (degrees) |
| `LOOK_UP_DOWN_DELTA` | delta | positive = down, negative = up (degrees) |
| `MOVE_FORWARD_BACKWARD_DELTA` | delta | positive = forward, negative = backward |
| `MOVE_LEFT_RIGHT_DELTA` | delta | positive = right, negative = left |
| `ATTACK` | binary | 1 = fire |
| `USE` | binary | 1 = open doors / activate switches |
| `SPEED` | binary | 1 = run |
| `SELECT_NEXT_WEAPON` | binary | 1 = cycle weapon forward |
| `SELECT_PREV_WEAPON` | binary | 1 = cycle weapon backward |
| `JUMP` | binary | 1 = jump |
| `CROUCH` | binary | 1 = crouch |

Each object in the game state includes an `angle_to_aim` field -pass it directly to `TURN_LEFT_RIGHT_DELTA` to face that object.

## Game Modes

### Training Scenarios

9 built-in ViZDoom scenarios for focused practice:

| Scenario | Description |
|----------|-------------|
| `basic` | Single room, single enemy -learn to shoot |
| `deadly_corridor` | Navigate a corridor with enemies on both sides |
| `defend_the_center` | Survive waves of enemies approaching from all directions |
| `defend_the_line` | Hold a defensive line against approaching enemies |
| `health_gathering` | Collect health packs to survive in a toxic environment |
| `health_gathering_supreme` | Harder version of health gathering |
| `my_way_home` | Navigate a maze to find the goal |
| `predict_position` | Track and shoot a moving target |
| `deathmatch` | Free-for-all deathmatch |

### Campaign Mode

Play through the full Doom game using the bundled Freedoom WADs:

```jsonc
// Custom map PWAD (on top of Freedoom 1)
{"wad": "freedoom1", "scenario_wad": "/absolute/path/to/DRKWRLD1.WAD", "map_name": "E1M1"}

// Doom II campaign (32 maps)
{"wad": "freedoom2", "map_name": "MAP01"}

// Doom I campaign (36 maps)
{"wad": "freedoom1", "map_name": "E1M1"}
```

When a level is completed, `new_episode()` automatically advances to the next map. On death, it restarts the current map. The state includes `level_completed`, `player_dead`, and `next_map` hints to guide the agent.

## Environment Variables

You can set default WADs and maps via environment variables. These are used by `start_game` if the corresponding parameters are not provided and a custom PWAD is being used.

| Variable | Description |
|----------|-------------|
| `DOOM_DEFAULT_IWAD` | Default base IWAD (e.g., `freedoom2`) |
| `DOOM_DEFAULT_PWAD` | Default custom PWAD path |
| `DOOM_DEFAULT_MAP` | Default map name (e.g., `MAP01`) |

## Architecture

```
AI Agent <──MCP──> FastMCP Server <──Python API──> ViZDoom Engine
                        │
              ┌─────────┼─────────┐
              │         │         │
          server.py  game_manager  executor.py
          (tools)    (lifecycle)   (async player)
              │         │         │
          actions.py  game_setup.py state.py objects.py
          (buttons)   (WAD setup)  (extract) (enemy DB)
```

- **`server.py`** -MCP tool definitions (thin wrappers)
- **`game_manager.py`** -game lifecycle, action execution, state management
- **`game_setup.py`** -IWAD/PWAD validation, map discovery, player-start checks, preflight load isolation
- **`executor.py`** -autonomous async-player movement, combat, pickups, objectives, and strategy
- **`state.py`** -screenshot conversion, object enrichment, depth/sector extraction
- **`actions.py`** -button name-to-enum mapping
- **`scenarios.py`** -scenario registry
- **`objects.py`** -database of 70+ Doom entity types

## Development

### Running Tests

```bash
# Unit tests (no ViZDoom runtime needed)
pytest tests/ -k "not integration"

# Integration tests (requires ViZDoom)
pytest tests/ -m integration

# All tests
pytest tests/
```

### Project Structure

```
mcp-doom/
├── src/doom_mcp/
│   ├── __init__.py
│   ├── server.py          # MCP tool definitions
│   ├── game_manager.py    # Core game lifecycle
│   ├── game_setup.py      # WAD/map setup and load preflight
│   ├── actions.py         # Button mapping
│   ├── scenarios.py       # Scenario registry
│   ├── state.py           # State extraction
│   └── objects.py         # Enemy database
├── tests/
│   ├── test_actions.py
│   ├── test_state.py
│   ├── test_scenarios.py
│   ├── test_objects.py
│   ├── test_game_manager.py    # Integration
│   └── test_server_integration.py
├── pyproject.toml
└── .mcp.json              # MCP client config
```

## Known Limitations

- **Single client** -one game instance at a time (no multiplayer MCP sessions this will be added very soon)
- **Delta values scale with tics** -use `tics=1` for precise aiming
- **Freedoom assets** -bundled WADs use Freedoom (free replacement art/levels), not original id Software assets
- **Headless rendering** -requires OpenGL libraries even without a visible window

## License

MIT
