# State Extraction

Utilities for converting ViZDoom screen buffers and game state into structured data for LLM consumption. Located in `mcp-doom/src/doom_mcp/state.py` (~167 lines).

## Functions

### `screen_buffer_to_png(buffer) -> bytes`

Converts ViZDoom RGB24 screen buffer to PNG bytes.

- **Input**: NumPy array `(H, W, 3)` with uint8 RGB values
- **Output**: PNG-encoded bytes (via Pillow `Image.fromarray()`)
- Used by `GameManager.get_state()` for screenshot embedding

### `_relative_angle(px, py, pangle, tx, ty) -> float`

Computes signed angle from player to target in degrees.

| Range | Sign | Meaning |
|-------|------|---------|
| -180 to 0 | Negative | Target is left |
| 0 to 180 | Positive | Target is right |

Used for target acquisition (aim_and_shoot, move_to).

### `extract_game_variables(game, variable_names) -> dict`

Extracts named game variables from ViZDoom `GameState.game_variables` array into a dict keyed by variable name.

- Maps indices from the configured `DEFAULT_VARIABLES` list to names
- Returns dict of `{NAME: value}` for all known variables

### `extract_objects(state, player_x, player_y, player_angle) -> list[dict]`

Extracts all objects from `GameState.labels` with enriched information:

| Field | Source | Description |
|-------|--------|-------------|
| `id` | label.object_id | Numerical object ID |
| `name` | label.object_name / object_info | Human-readable name |
| `distance` | computed | Euclidean distance from player |
| `angle_to_aim` | `_relative_angle()` | Degrees left/right to face target |
| `type` | object_info | monster/weapon/ammo/health/armor/key/powerup/projectile/decor |
| `threat` | object_info | low/medium/high/extreme/none |
| `attack_type` | object_info | melee/ranged/projectile/hitscan/none |
| `typical_hp` | object_info | Typical hit points |
| `description` | object_info | Gameplay-relevant description |
| `position` | label | (x, y, z) world coordinates |
| `velocity` | label | (x, y, z) velocity vector |
| `angle` | label | Object facing angle |
| `pitch` | label | Object pitch |
| `is_visible` | label | Whether currently visible |
| `screen_x`, `screen_y` | label | Screen-space coordinates |

### `extract_sectors(state) -> list[dict]`

Extracts sector geometry from `GameState.sectors`:

| Field | Description |
|-------|-------------|
| `sector_id` | Index |
| `floor_height` | Floor Z |
| `ceiling_height` | Ceiling Z |
| `lines` | List of wall lines with `(x1,y1,x2,y2)` and `is_blocking` |

### `extract_depth_as_stats(depth_buffer) -> dict`

Summarizes depth buffer (ViZDoom `DEPTH_BUFFER` enabled) into 7 regions:

| Region | Coverage | Purpose |
|--------|----------|---------|
| `far_left` | Left 30% | Left-side space awareness |
| `far_center` | Center 40% | Forward clearance |
| `far_right` | Right 30% | Right-side space awareness |
| `near_left` | Left 30% (near half) | Immediate left obstacles |
| `near_center` | Center 40% (near half) | Immediate forward obstacles |
| `near_right` | Right 30% (near half) | Immediate right obstacles |
| `crosshair` | Center 5% | Direct aim-line distance |

Each region returns `min` and `mean` distance. Used by both the LLM prompt and the AutonomousExecutor for wall avoidance.

## State Normalization (in `mcp_client_service.py`)

The Backend's `McpDoomClient` applies additional normalization:

- ViZDoom variable casing normalization (e.g., `SELECTED_WEAPON` uppercase)
- Object ID filtering (hide occluded objects from prompt)
- State compaction for LLM input (capped at ~20 objects, depth removed for token efficiency)
