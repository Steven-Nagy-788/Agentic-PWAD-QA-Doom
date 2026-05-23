from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID


RUN_TASKS: dict[UUID, asyncio.Task] = {}
_ACTIVE_RUN_LOCK_ID = 42770001
_ORPHANED_RUN_STALE_AFTER = timedelta(minutes=5)
COMPOUND_TELEMETRY_TOOLS = {"explore", "move_to", "aim_and_shoot", "strafe_and_shoot", "retreat", "take_action"}
OBJECT_ID_TOOLS = {"aim_and_shoot", "strafe_and_shoot", "move_to"}
COMBAT_TOOLS = {"aim_and_shoot", "strafe_and_shoot"}
STUCK_RUN_ABORT_THRESHOLD = 5
WASTED_COMBAT_ABORT_THRESHOLD = 3
LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD = 2
LOW_VALUE_EXPLORE_STUCK_LIMIT = 6
QA_PROBE_BURST_LIMIT = 4
EXPLORE_MAX_TICS_UPPER = 80
REPEATED_ACTION_ABORT_THRESHOLD = 4
BLOCKED_DECISION_ABORT_THRESHOLD = 6
PICKUP_OBJECT_TYPES = {"item", "ammo", "weapon", "key"}
DIRECTOR_POLL_SECONDS = 1.25
DIRECTOR_STUCK_POLL_THRESHOLD = 5
DIRECTOR_STUCK_RECOVERY_LIMIT = 4
PWAD_CRASH_CATEGORY = "pwad_crash"
INFRASTRUCTURE_CATEGORY = "infrastructure"
TAKE_ACTION_BUTTONS = {
    "TURN_LEFT_RIGHT_DELTA",
    "LOOK_UP_DOWN_DELTA",
    "MOVE_FORWARD_BACKWARD_DELTA",
    "MOVE_LEFT_RIGHT_DELTA",
    "ATTACK",
    "USE",
    "SPEED",
    "SELECT_NEXT_WEAPON",
    "SELECT_PREV_WEAPON",
    "JUMP",
    "CROUCH",
}
TAKE_ACTION_BINARY_BUTTONS = {
    "ATTACK",
    "USE",
    "SPEED",
    "SELECT_NEXT_WEAPON",
    "SELECT_PREV_WEAPON",
    "JUMP",
    "CROUCH",
}
CARDINAL_DIRECTION_ANGLES = {"east": 0.0, "north": 90.0, "west": 180.0, "south": 270.0}
OBJECT_ID_ALIASES: dict[str, tuple[str, ...]] = {
    "aim_and_shoot": ("object_id", "enemy_id", "target_id", "monster_id"),
    "strafe_and_shoot": ("object_id", "enemy_id", "target_id", "monster_id"),
    "move_to": ("object_id", "target_id", "item_id", "pickup_id", "enemy_id", "monster_id"),
}
TOOL_PARAM_ALLOWLIST: dict[str, set[str]] = {
    "aim_and_shoot": {"object_id", "shots", "max_tics", "capture_telemetry", "telemetry_stride"},
    "strafe_and_shoot": {"object_id", "direction", "shots", "max_tics", "capture_telemetry", "telemetry_stride"},
    "move_to": {"object_id", "max_tics", "use", "stop_on_enemy", "capture_telemetry", "telemetry_stride"},
    "explore": {"max_tics", "stop_on_enemy", "stop_on_item", "capture_telemetry", "telemetry_stride"},
    "retreat": {"tics", "backpedal", "capture_telemetry", "telemetry_stride"},
    "get_state": {"include_sectors", "include_depth"},
    "get_threat_assessment": set(),
    "get_navigation_info": set(),
}
