# MCP Tools Reference

All 24 tools exposed by the MCP Doom server. Tools are defined in `server.py` and delegate to `GameManager` methods.

---

## 1. `start_game`

Start a new Doom game with the given configuration. Use a built-in ViZDoom scenario, or provide a WAD + map for full campaign play.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `scenario` | `string` | `"basic"` | Built-in scenario name. Ignored if `wad` is set. One of: `basic`, `deadly_corridor`, `defend_the_center`, `defend_the_line`, `health_gathering`, `health_gathering_supreme`, `my_way_home`, `predict_position`, `deathmatch` |
| `wad` | `string` | `null` | WAD file to load. Use `"freedoom1"` (E1M1-E4M9), `"freedoom2"` (MAP01-MAP32), or an absolute path |
| `scenario_wad` | `string` | `null` | PWAD file to load on top of the IWAD. Absolute path required |
| `map_name` | `string` | `null` | Map to load (e.g. `"MAP01"`, `"E1M1"`). Required when using `wad` |
| `difficulty` | `integer` | `3` | Doom skill level 1-5 (1=easiest, 5=nightmare) |
| `buttons` | `string[]` | `null` | Button names to enable. Defaults to delta aim + movement + combat |
| `variables` | `string[]` | `null` | Game variable names to track. Defaults to comprehensive set (39 vars) |
| `screen_resolution` | `string` | `"RES_320X240"` | ViZDoom resolution enum name |
| `episode_timeout` | `integer` | `null` | Max tics per episode. `null` uses scenario/map default |
| `render_hud` | `boolean` | `false` | Whether to render the HUD overlay |
| `window_visible` | `boolean` | `false` | Open a game window so you can watch. Requires a display |
| `async_player` | `boolean` | `false` | Run game in real-time (ASYNC_PLAYER mode). Enables the autonomous executor |
| `ticrate` | `integer` | `null` | Game speed in tics/sec for async mode (default 35 = normal speed) |
| `seed` | `integer` | `null` | Random seed for reproducibility |
| `recording_path` | `string` | `null` | File path to record episode demo (`.lmp`) |

**Returns:** `{status, buttons, variables, screen_resolution, [wad/map or scenario]}`

---

## 2. `get_state`

Get the current game state: screenshot + full structured data with variables, objects, depth stats, and optional sector geometry.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `include_sectors` | `boolean` | `false` | Include map geometry (wall lines, heights). Very large payload — only request when needed |
| `include_depth` | `boolean` | `true` | Include depth buffer stats per screen region |

**Returns:** `[screenshot PNG, state_dict]`

State dict contains:
- `episode_finished`, `tic`, `total_reward`
- `game_variables`: health, armor, position, angle, ammo, weapons, kills, damage, etc.
- `objects`: entities with distance, angle_to_aim, type, threat, HP, visibility
- `depth` (optional): min/mean distance per screen region (far_left, far_center, far_right, near_left, near_center, near_right, crosshair)
- `sectors` (optional): sector geometry

---

## 3. `take_action`

Execute one or more button actions for N game tics and return the resulting state.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `actions` | `object` | `null` | Dict mapping button names to values. Binary: `1` to press. Delta: degrees (e.g. `TURN_LEFT_RIGHT_DELTA: -15`). `null` or `{}` = no-op |
| `tics` | `integer` | `1` | Game tics to hold the action. Delta values are **multiplied by tics** |
| `include_sectors` | `boolean` | `false` | Include map geometry in result |
| `include_depth` | `boolean` | `true` | Include depth buffer stats |
| `capture_telemetry` | `boolean` | `false` | Return per-tic gameplay frames for recording |
| `telemetry_stride` | `integer` | `1` | Capture every N tics when telemetry is enabled |

**Returns:** `[screenshot PNG, {episode_finished, game_variables, objects, depth, reward, action_summary}]`

Action summary includes `stop_reason`: `tics_complete`, `player_died`, `episode_finished`.

---

## 4. `get_objects`

Get all visible objects with enriched info from the entity database.

**Parameters:** None

**Returns:** `{objects: [{id, name, distance, angle_to_aim, type, threat, attack_type, typical_hp, description, is_visible, position_x/y/z, angle, pitch, velocity_x/y/z, screen_x/y (if visible)}]}`

---

## 5. `get_map`

Get the automap (top-down view) of the current level as a PNG image.

**Parameters:** None

**Returns:** `[screenshot PNG]` or `[{error: "..."}]`

---

## 6. `new_episode`

Start a new episode in the current game. Resets the level while keeping the same configuration. In campaign mode, **auto-advances** to the next map if the previous level was completed.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `recording_path` | `string` | `null` | File path to record this episode's demo (`.lmp`). Falls back to `start_game` recording path |

**Returns:** `{status, [map or scenario], [advanced: true]}`

---

## 7. `get_available_actions`

Get metadata about the configured action buttons — their names, types (binary vs delta), sign conventions, and usage example.

**Parameters:** None

**Returns:** `{buttons: [{name, type, description}], usage, delta_convention}`

Delta conventions:
- `TURN_LEFT_RIGHT_DELTA`: positive=right, negative=left (degrees)
- `LOOK_UP_DOWN_DELTA`: positive=down, negative=up (degrees)
- `MOVE_FORWARD_BACKWARD_DELTA`: positive=forward, negative=backward
- `MOVE_LEFT_RIGHT_DELTA`: positive=right, negative=left

---

## 8. `list_wad_maps`

List map markers (MAP01, E1M1, etc.) found inside a WAD file.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `wad_path` | `string` | — | Path to the WAD file |

**Returns:** `{wad_path, maps: ["MAP01", "MAP02", ...]}`

---

## 9. `aim_and_shoot`

Compound action: aim at an enemy and fire multiple shots. Handles aiming, firing, and weapon cooldown automatically. Runs many game tics internally in milliseconds — the player doesn't stand idle between LLM decisions.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `object_id` | `integer` | — | Numeric ID of a visible monster target from the current objects list |
| `shots` | `integer` | `3` | Number of shots to fire. Stops early if target dies |
| `max_tics` | `integer` | `100` | Maximum game tics before giving up |
| `capture_telemetry` | `boolean` | `false` | Return per-tic gameplay frames |
| `telemetry_stride` | `integer` | `4` | Capture every N tics when telemetry is enabled |

**Returns:** `[screenshot PNG, {action_summary: {shots_fired, hits_landed, kills, ammo_spent, target_name, stop_reason}}]`

Stop reasons: `shots_complete`, `target_killed`, `target_lost`, `target_not_visible`, `player_died`, `out_of_ammo`, `episode_finished`, `max_tics`.

---

## 10. `move_to`

Compound action: move toward an object by ID. Handles pathfinding, turning, and stuck recovery automatically.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `object_id` | `integer` | — | Numeric ID of a visible target from the objects list |
| `max_tics` | `integer` | `140` | Maximum game tics before giving up |
| `use` | `boolean` | `false` | Press USE when arriving (for switches/doors) |
| `stop_on_enemy` | `boolean` | `true` | Stop if a visible monster appears nearby (within 800 units) |
| `capture_telemetry` | `boolean` | `false` | Return per-tic gameplay frames |
| `telemetry_stride` | `integer` | `4` | Capture every N tics when telemetry is enabled |

**Returns:** `[screenshot PNG, {action_summary: {distance_moved, distance_remaining, target_name, used_object, collected, threat_object, stop_reason}}]`

Stop reasons: `arrived`, `target_lost`, `enemy_nearby`, `stuck`, `player_died`, `episode_finished`, `max_tics`, `pickup_not_collected`.

---

## 11. `explore`

Compound action: explore the environment autonomously. Walks forward, avoids walls using depth buffer analysis, performs stuck recovery, and scans for threats and items.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_tics` | `integer` | `200` | Maximum game tics to explore |
| `stop_on_enemy` | `boolean` | `true` | Stop when a visible monster is spotted nearby (first sighting) |
| `stop_on_item` | `boolean` | `false` | Stop when a new item/ammo is spotted (first sighting) |
| `capture_telemetry` | `boolean` | `false` | Return per-tic gameplay frames |
| `telemetry_stride` | `integer` | `4` | Capture every N tics when telemetry is enabled |

**Returns:** `[screenshot PNG, {action_summary: {distance_moved, direction_changes, enemies_seen[], items_seen[], stop_reason}}]`

Stop reasons: `enemy_spotted`, `item_found`, `stuck`, `player_died`, `episode_finished`, `max_tics`.

---

## 12. `strafe_and_shoot`

Compound action: strafe laterally while firing at an enemy. Better than `aim_and_shoot` against hitscan enemies — the player dodges left/right while keeping the target in the crosshair.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `object_id` | `integer` | — | Numeric ID of the target from the objects list |
| `direction` | `string` | `"auto"` | Strafe direction: `"left"`, `"right"`, or `"auto"` (alternates every ~15 tics) |
| `shots` | `integer` | `5` | Number of shots to fire |
| `max_tics` | `integer` | `100` | Maximum game tics before giving up |
| `capture_telemetry` | `boolean` | `false` | Return per-tic gameplay frames |
| `telemetry_stride` | `integer` | `4` | Capture every N tics when telemetry is enabled |

**Returns:** `[screenshot PNG, {action_summary: {shots_fired, hits_landed, kills, ammo_spent, target_name, strafe_direction, damage_taken, stop_reason}}]`

Stop reasons: `shots_complete`, `target_killed`, `target_lost`, `target_not_visible`, `player_died`, `out_of_ammo`, `episode_finished`, `max_tics`.

---

## 13. `retreat`

Compound action: retreat from the current position. Two modes — turn 180 and sprint forward (faster escape), or backpedal while maintaining line of sight (slower but keeps visual).

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `tics` | `integer` | `35` | Total game tics for the retreat (~1 second at 35 Hz) |
| `backpedal` | `boolean` | `false` | If true, move backward while keeping current facing. If false (default), turn 180° then sprint forward |
| `capture_telemetry` | `boolean` | `false` | Return per-tic gameplay frames |
| `telemetry_stride` | `integer` | `4` | Capture every N tics when telemetry is enabled |

**Returns:** `[screenshot PNG, {action_summary: {distance_moved, mode ("backpedal"|"turn_and_run"), stop_reason}}]`

---

## 14. `get_threat_assessment`

Analyze known threats and return prioritized tactical intelligence. No game tics consumed — call freely between actions.

**Parameters:** None

**Returns:** `{threat_level, threats[], incoming_projectiles[], tactical_advice[], player_health, player_armor, selected_weapon_ammo}`

- `threat_level`: `"none"`, `"low"`, `"medium"`, `"high"`, or `"critical"`
- `threats`: sorted by priority score; each has `id`, `name`, `distance`, `angle_to_aim`, `attack_type`, `is_visible`, `priority_rank`, `priority_score`
- `incoming_projectiles`: active projectiles to dodge
- `tactical_advice`: string list with prioritized recommendations

---

## 15. `get_navigation_info`

Get spatial navigation intelligence. Tracks exploration across calls using `NavigationMemory`. No game tics consumed.

**Parameters:** None

**Returns:** `{cells_explored, explored_directions, unexplored_directions, suggested_direction, keys_found, known_key_locations, nearby_doors, total_doors_found}`

- `cells_explored`: number of MCP navigation's internal 128-unit grid cells
  visited. Backend QA coverage uses a separate 256-unit grid.
- `suggested_direction`: best unexplored cardinal direction aligned with player facing
- `nearby_doors`: detected doors within 512 units

---

## 16. `get_situation_report`

Get a director-facing snapshot of the game state. Use this instead of `get_state` when the autonomous executor is running. Returns screenshot, executor state, recent events, game variables, nearby objects, and exploration progress.

**Parameters:** None

**Returns:** `[screenshot PNG, {executor_state, objectives[], strategy, events[], game_variables, objects, exploration, executor_progress}]`

---

## 17. `set_objective`

Set an objective for the autonomous executor. The executor works toward this objective while handling combat and navigation autonomously. Higher-priority objectives are executed first. Requires `async_player=True`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `objective_type` | `string` | — | One of: `explore`, `kill`, `move_to_pos`, `move_to_obj`, `collect`, `use_object`, `retreat`, `hold_position` |
| `params` | `object` | `null` | Parameters (e.g. `{"object_id": 5}` for `kill`/`move_to_obj`, `{"x": 100, "y": 200}` for `move_to_pos`) |
| `priority` | `integer` | `0` | Higher = executed first |
| `timeout_tics` | `integer` | `0` | Auto-fail after this many tics. `0` = no timeout |
| `replace` | `boolean` | `false` | Clear queued objectives before adding this one |

**Returns:** `{status, objective, replace, queue}`

---

## 18. `set_strategy`

Tune the autonomous executor's behavior parameters. Requires `async_player=True`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `aggression` | `number` | `0.5` | 0.0=passive (avoid fights), 1.0=aggressive (engage everything) |
| `health_retreat_threshold` | `integer` | `20` | HP at which executor always retreats |
| `health_collect_threshold` | `integer` | `50` | HP at which executor seeks health items |
| `ammo_switch_threshold` | `integer` | `5` | Ammo count at which executor switches weapons |
| `engage_range` | `number` | `1500` | Max distance (map units) to engage enemies |
| `collect_range` | `number` | `800` | Max distance to collect items |
| `prefer_cover` | `boolean` | `false` | Try to use cover during combat |

**Returns:** `{status, strategy}`

---

## 19. `get_map_knowledge`

Get accumulated map knowledge for strategic planning. Returns position, cells explored, unexplored directions, known keys, doors, current executor state, and objectives. No game tics consumed.

**Parameters:** None

**Returns:** `{position, cells_explored, explored_directions, unexplored_directions, suggested_direction, keys_found, known_key_locations, nearby_doors, total_doors_found, [executor_state, objectives]}`

---

## 20. `stop_game`

Stop the current game and release all resources. Cleans up the ViZDoom instance, stops the autonomous executor, and removes any temporary WAD files.

**Parameters:** None

**Returns:** `{status: "stopped"}`
