# MCP Doom Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that wraps [ViZDoom](https://github.com/mwydmuch/ViZDoom) to let AI agents play Doom. The server exposes 20 MCP tools for game control, state inspection, combat, navigation, and high-level strategic direction, plus an autonomous background executor that can play at real-time speed (~35 Hz).

## Architecture

```
AI Agent (LLM) <-> MCP Protocol <-> FastMCP Server <-> GameManager <-> ViZDoom <-> Doom Engine
                                                  <-> AutonomousExecutor (async thread)
```

The AI agent communicates over the Model Context Protocol (MCP), sending tool requests to the server. The **FastMCP server** routes each request to the **GameManager**, which wraps a ViZDoom `DoomGame` instance. Compound actions (`aim_and_shoot`, `move_to`, `explore`) run tight internal game loops so the agent doesn't need to issue per-tic commands. For real-time play, the **AutonomousExecutor** runs in a background thread at ~35 Hz, handling combat, navigation, and item collection while the LLM acts as a high-level director via `set_objective` and `set_strategy`.

## Modules

| Module | File | Purpose |
|---|---|---|
| **Server** | `server.py` | 20 MCP tool definitions, wires tools to GameManager methods |
| **Game Manager** | `game_manager.py` | Core `GameManager` class wrapping `vzd.DoomGame`; lifecycle, state extraction, compound actions, director API, telemetry, campaign auto-advance |
| **Executor** | `executor.py` | `AutonomousExecutor` — background-thread state machine for real-time gameplay |
| **Game Setup** | `game_setup.py` | WAD parsing, map listing, preflight validation, Player 1 start normalization |
| **Navigation** | `navigation.py` | `NavigationMemory` — grid-based cell tracking, key/door detection, exploration direction analysis |
| **State** | `state.py` | Game state extraction — 39 game variables, object enrichment, sector geometry, depth buffer stats |
| **Objects** | `objects.py` | Entity database for 70+ Doom entity types — monster info, items, weapons, keys, projectiles, decorations, powerups |
| **Actions** | `actions.py` | Button name-to-ViZDoom action mapping |
| **Scenarios** | `scenarios.py` | Registry of 9 built-in ViZDoom scenarios: basic, deadly_corridor, defend_the_center, defend_the_line, health_gathering, health_gathering_supreme, my_way_home, predict_position, deathmatch |

## Quick Start

```bash
# Install
cd mcp-doom
pip install -e .

# Run as MCP server
python -m doom_mcp
```

### With Claude Desktop / opencode

Add to `opencode.json`:

```json
{
  "mcpServers": {
    "doom": {
      "command": "python",
      "args": ["-m", "doom_mcp"],
      "cwd": "/path/to/mcp-doom"
    }
  }
}
```

## Usage Patterns

### Turn-based (synchronous) play

```python
# 1. Start a game
start_game(wad="freedoom2", map_name="MAP01")

# 2. Look around
state = get_state()

# 3. Act
result = take_action({"MOVE_FORWARD": 1}, tics=10)

# 4. Or use compound actions
result = aim_and_shoot(object_id=5)
result = explore(max_tics=100)
result = move_to(object_id=3, use=True)
```

### Real-time (async) play with autonomous executor

```python
# 1. Start with async player
start_game(wad="freedoom2", map_name="MAP01", async_player=True)

# 2. Set objectives for the executor
set_objective("explore", priority=1)
set_strategy(aggression=0.7, health_retreat_threshold=30)

# 3. Monitor progress
report = get_situation_report()  # returns screenshot + state + events
```

### Campaign mode

```python
# Episode auto-advances through E1M1..E4M9 (Doom 1) or MAP01..MAP32 (Doom 2)
start_game(wad="freedoom1", map_name="E1M1")
# ... play ...
result = get_state()
if result.get("level_completed"):
    new_episode()  # auto-advances to E1M2
```

## Further Reading

| Document | Description |
|----------|-------------|
| [Tools Reference](tools.md) | Complete MCP tools with parameters, return types, stop reasons |
| [Game Manager](game-manager.md) | GameManager lifecycle, compound actions, campaign mode, director API |
| [Executor](executor.md) | AutonomousExecutor state machine, combat, exploration, stuck recovery |
| [Navigation](navigation.md) | NavigationMemory grid cells, key/door detection, direction analysis |
| [State](state.md) | Game state extraction: variables, objects, sectors, depth buffer |
| [Objects](objects.md) | Entity database: 70+ Doom entities with threat/attack/HP metadata |
