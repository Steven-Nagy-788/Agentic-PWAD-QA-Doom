# NavigationMemory

Spatial navigation memory for explored areas, keys, and doors. Located in `mcp-doom/src/doom_mcp/navigation.py` (~261 lines).

## Grid System

- **Cell size**: 128 world units (configurable via `_CELL_SIZE`)
- **Grid cells**: `(int(x / CELL_SIZE), int(y / CELL_SIZE))` — floor division
- Visited cells stored in a `set` of `(gx, gy)` tuples

## Breadcrumb Trail

- **Spacing**: one breadcrumb every 64 units (`_BREADCRUMB_SPACING`)
- **Limit**: 500 breadcrumbs max (`_BREADCRUMB_MAX`)
- Tracks `(x, y, angle)` tuples for path history visualization

## Key Tracking

- **Detection range**: 64 units (`_KEY_PICKUP_RANGE`)
- Detects visible keys via `get_objects()` with type matching `_ITEM_TYPES`
- Records pickup when a key disappears from the nearby list while player is within range
- Stores: key type, position, and pickup tick in `keys_found` list

## Door Detection

Detected from sector geometry during `update()`:

1. Scan all sectors from game state
2. Identify small sectors (max dimension < `_DOOR_MAX_SECTOR_SIZE` = 256)
3. Check ceiling-floor gap < `_DOOR_HEIGHT_THRESHOLD` = 8 units
4. Create door entry with: position (sector centroid), lines, sector index
5. Deduplicate: skip if existing door within `_DOOR_DEDUP_RANGE` = 128 units

## Exploration Analysis

`get_exploration_summary(px, py, pa)` returns:

| Field | Description |
|-------|-------------|
| `cells_explored` | Count of distinct visited grid cells |
| `breadcrumbs` | Path history as coordinate array |
| `explored_directions` | Set of four cardinal directions explored |
| `unexplored_directions` | Set of cardinal directions NOT explored |
| `suggested_direction` | Single suggested cardinal direction string |
| `keys_found` | List of discovered keys with positions |
| `known_key_locations` | Known key spawn points |
| `nearby_doors` | Door objects within detection range |

### Direction Classification

From player angle:
- **North**: -45° to 45°
- **East**: 45° to 135°
- **South**: 135° to -135° (wrapping)
- **West**: -135° to -45°

### Suggested Direction

- If unexplored directions exist → random unexplored direction
- If all explored → turn toward fewest-breadcrumb direction
- Uses `suggested_turn_delta(px, py, pa, max_delta)` for signed turn angle

## Growth Tracking

- `growth_history`: tracks cells discovered per tick (for coverage progress metrics)
- `_previous_player_pos`: 3-frame position history for stuck detection

## Sector Tracking

- `visited_sector_ids`: set of visited sector indices
- `_sector_at_position(px, py, sectors)`: find sector via point-in-polygon
- `_point_in_closed_lines(px, py, lines)`: ray-casting test
