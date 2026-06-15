# AutonomousExecutor

Background thread that plays Doom autonomously at ~35 Hz (game speed). Located in `mcp-doom/src/doom_mcp/executor.py` (~923 lines).

## State Machine

```
  ┌──────────────────────────────────────────────────┐
  │                    IDLE                          │
  │  (no objective, wanders with exploration bias)   │
  └─────┬──────────────┬──────────────┬──────────────┘
        │ threat       │ objective    │ low health
        ▼              ▼              ▼
  ┌──────────┐  ┌───────────┐  ┌───────────┐
  │ FIGHTING │  │MOVING_TO/ │  │ RETREATING│
  │          │  │COLLECTING │  │           │
  └─────┬────┘  │EXPLORING │  └─────┬─────┘
        │       └─────┬─────┘        │
        └──────────────┴──────────────┘
                │ no threat/obj
                ▼
              IDLE
```

### States

| State | Trigger | Behavior |
|-------|---------|----------|
| `IDLE` | No threats, no objectives | Wand with exploration bias, strafe periodically |
| `EXPLORING` | `set_objective(EXPLORE)` | Depth-buffer wall avoidance, turn toward unexplored |
| `FIGHTING` | Enemy in range | Face target, fire, dodge strafe, weapon switch if OOA |
| `COLLECTING` | `set_objective(COLLECT)` | Navigate to nearest pickup, prioritize weapons>ammo>health>keys |
| `RETREATING` | Health < 30% | Turn away from nearest threat and sprint, or backpedal |
| `MOVING_TO` | `set_objective(MOVE_TO_POS/OBJ)` | Compute angle, clamp turn speed, detect arrival |
| `HOLD_POSITION` | `set_objective(HOLD_POSITION)` | Stay still, react to nearby threats |

## Per-Tick Loop

```
1. Read game state (variables, objects, depth, sectors)
2. Update NavigationMemory (position, keys, doors)
3. Decide behavior:
   a. If objective active → pursue objective
   b. If threat nearby → fight
   c. If low health → retreat
   d. Otherwise → idle/explore
4. Execute action (build action array from decided movement)
5. Log event if notable
```

## Combat System

- **Target scoring**: prioritize by distance (closer=higher), threat level (Archvile > Imp), health remaining (wounded preferred)
- **Weapon switching**: auto-switch when current weapon out of ammo; prefer best weapon for distance
- **Aiming**: compute angle to target, fire when within tolerance (~5.7 degrees)
- **Dodge strafe**: alternate left/right strafe when idle during combat
- **Melee proximity**: switch to chainsaw when target < 64 units

## Exploration System

- **Depth buffer avoidance**: stop forward movement when center depth < 64 units; turn away when any region depth < 48 units
- **Wall detection**: 3-frame lookback for position change < 1 unit → stuck detection
- **Turn bias**: inherit previous turn direction with random variation

## Stuck Recovery

4-phase recovery cycle, escalating:
1. Phase 0: Turn right 45 degrees, move forward
2. Phase 1: Turn left 45 degrees, move forward
3. Phase 2: Turn 180 degrees + move forward
4. Phase 3: Strafe + turn, move forward

Stuck detection: position spread < 0.5 units over 10 consecutive ticks.

## Objective Queue

- Priority-sorted queue (lower number = higher priority)
- `push_objective(obj, replace=False)` — append if lower priority exists
- `push_objective(obj, replace=True)` — clear queue first
- Objectives support `timeout_ticks` (auto-expire)
- Completed/expired objectives are removed and event logged

## Thread Safety

- `AutonomousExecutor.running` flag controls the daemon thread
- `pause()` / `resume()` for synchronous compound action interleaving
- `_with_executor_paused()` context manager in GameManager
- Event log is a thread-safe ring buffer (last 100 events)

## Strategy Parameters

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `aggression` | float 0-1 | 0.5 | Threshold to engage vs flee |
| `caution` | float 0-1 | 0.5 | Health threshold for retreat |
| `exploration_bias` | float 0-1 | 0.5 | Turn toward unexplored vs random |
| `item_hysteria` | float 0-1 | 0.5 | Priority of pickup collection |
| `strafing_frequency` | float 0-1 | 0.3 | Chance of dodge strafe per tick |
| `aim_snappiness` | float 0-1 | 0.5 | Turn speed multiplier for aiming |
| `weapon_preference` | str | "best" | "best" / "safest" / specific slot |

## Event Log

Ring buffer (`collections.deque(maxlen=100)`) of `ExecutorEvent` objects:
- `timestamp`, `state`, `message`, `position (x,y)`, `objective_id`, `health`
