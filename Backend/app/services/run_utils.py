from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.types import LockstepState
from app.services.analysis_constants import CELL_SIZE
from app.services.collector_service import normalize_variables
from app.services.mcp_client_service import normalize_mcp_state
from app.services.run_constants import INFRASTRUCTURE_CATEGORY, PWAD_CRASH_CATEGORY


_PROFILE_ALIASES: dict[str, str] = {
    "speedrunner": "fast",
    "safety": "thorough",
    "exploit_hunter": "exploit_focused",
}


def get_behavior_profile(run: Any | None):
    from app.core.behavior_profiles import get_profile
    if run and getattr(run, "behavior_profile", None):
        name = _PROFILE_ALIASES.get(run.behavior_profile, run.behavior_profile)
        try:
            return get_profile(name)
        except KeyError:
            pass
    from app.core.config import settings as _settings
    return get_profile(_settings.DEFAULT_AGENT_BEHAVIOR)


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _bounded_int(value: Any, default: int, lower: int = 0, upper: int | None = None) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    parsed = max(lower, parsed)
    if upper is not None:
        parsed = min(upper, parsed)
    return parsed


def _bounded_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_like(value: Any) -> int:
    with contextlib.suppress(TypeError, ValueError):
        return int(float(value))
    return 0


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _summary(value: Any) -> str:
    text = json.dumps(_json_safe(value), default=str) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= 1000 else text[:1000] + "..."


def _mcp_action_summary(mcp_call: dict[str, Any]) -> dict[str, Any]:
    output = mcp_call.get("output")
    if not isinstance(output, dict):
        return {}
    summary = output.get("action_summary")
    return summary if isinstance(summary, dict) else {}


def _compact_mcp_output(value: Any) -> Any:
    state, _ = normalize_mcp_state(value)
    if not isinstance(state, dict):
        return _summary(value)
    compact = {key: val for key, val in state.items() if key not in {"telemetry_frames", "depth", "sectors"}}
    if isinstance(compact.get("objects"), list):
        compact["objects"] = compact["objects"][:12]
    if "action_summary" in state:
        compact["action_summary"] = state["action_summary"]
    return compact


def _compact_state_for_llm(state: dict[str, Any]) -> dict[str, Any]:
    compact = {key: value for key, value in state.items() if key not in {"screenshot_png", "sectors"}}
    if isinstance(compact.get("objects"), list):
        objects = []
        for obj in compact["objects"][:30]:
            if not isinstance(obj, dict):
                continue
            objects.append(
                {
                    key: obj.get(key)
                    for key in (
                        "id",
                        "name",
                        "type",
                        "threat",
                        "attack_type",
                        "distance",
                        "angle_to_aim",
                        "is_visible",
                        "screen_x",
                        "screen_y",
                    )
                    if key in obj
                }
            )
        compact["objects"] = objects
    return _json_safe(compact)


def _lockstep_state_snapshot(state: LockstepState) -> LockstepState:
    return {
        "no_progress_polls": int(state.get("no_progress_polls") or 0),
        "recovery_count": int(state.get("recovery_count") or 0),
        "wasted_combat_count": int(state.get("wasted_combat_count") or 0),
        "consecutive_explore_max_tics": int(state.get("consecutive_explore_max_tics") or 0),
        "low_value_explore_total": int(state.get("low_value_explore_total") or 0),
        "low_value_explore_cumulative": int(state.get("low_value_explore_cumulative") or 0),
        "qa_probe_count": int(state.get("qa_probe_count") or 0),
        "invisible_target_failures": dict(state.get("invisible_target_failures") or {}),
        "completed_object_ids": dict(state.get("completed_object_ids") or {}),
        "failed_object_ids": dict(state.get("failed_object_ids") or {}),
        "out_of_ammo_targets": dict(state.get("out_of_ammo_targets") or {}),
        "blocked_decision_count": int(state.get("blocked_decision_count") or 0),
        "progress_score": int(state.get("progress_score") or 0),
        "quality_warnings": list(state.get("quality_warnings") or [])[-8:],
        "hypotheses": list(state.get("hypotheses") or [])[-8:],
        "attempted_interactions": list(state.get("attempted_interactions") or [])[-12:],
        "explored_sectors": _sector_ids_from_state(state),
        "visited_cells_count": len(state.get("visited_cells") or {}),
        "total_map_cells_estimate": state.get("total_map_cells_estimate"),
        "new_cells_last_5_decisions": state.get("new_cells_last_5_decisions", 0),
        "unvisited_quadrants": _compute_unvisited_quadrants(state),
    }


def _structured_memory_snapshot(state: LockstepState) -> dict[str, Any]:
    return {
        "explored_sectors": _sector_ids_from_state(state),
        "attempted_interactions": list(state.get("attempted_interactions") or [])[-12:],
        "hypotheses": list(state.get("hypotheses") or [])[-8:],
    }


def _initial_lockstep_state() -> LockstepState:
    return {
        "last_signature": None,
        "no_progress_polls": 0,
        "recovery_count": 0,
        "last_tick": -1,
        "invisible_target_failures": {},
        "wasted_combat_count": 0,
        "consecutive_explore_max_tics": 0,
        "low_value_explore_total": 0,
        "low_value_explore_cumulative": 0,
        "qa_probe_count": 0,
        "completed_object_ids": {},
        "failed_object_ids": {},
        "out_of_ammo_targets": {},
        "action_signature_counts": {},
        "blocked_decision_count": 0,
        "progress_score": 0,
        "meaningful_progress_events": 0,
        "quality_warnings": [],
        "visited_cells": {},
        "visited_sector_ids": {},
        "attempted_interactions": [],
        "hypotheses": [],
        "new_cells_last_5_decisions": 0,
        "_new_cells_current": 0,
        "_new_cells_decision_counts": [],
    }


def _track_visited_cell(state: dict[str, Any], lockstep_state: LockstepState) -> None:
    variables = normalize_variables(state)
    x = float(variables.get("x") or 0)
    y = float(variables.get("y") or 0)
    cell_key = f"{round(x / CELL_SIZE)}_{round(y / CELL_SIZE)}"
    visited = lockstep_state.get("visited_cells") or {}
    was_new = cell_key not in visited
    visited[cell_key] = visited.get(cell_key, 0) + 1
    lockstep_state["visited_cells"] = dict(list(visited.items())[-200:])
    if was_new:
        lockstep_state["_new_cells_current"] = lockstep_state.get("_new_cells_current", 0) + 1


def _track_explored_sectors(
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: LockstepState,
) -> None:
    sector_ids = set(_sector_ids_from_state(lockstep_state))
    for sector_id in _extract_sector_ids(state):
        sector_ids.add(sector_id)
    for sector_id in _extract_sector_ids(navigation_info):
        sector_ids.add(sector_id)
    visited = {str(sector_id): 1 for sector_id in sorted(sector_ids)[-200:]}
    lockstep_state["visited_sector_ids"] = visited


def _merge_hypotheses(lockstep_state: LockstepState, decision: dict[str, Any]) -> None:
    raw = decision.get("hypotheses")
    candidates: list[str] = []
    if isinstance(raw, str):
        candidates.append(raw)
    elif isinstance(raw, list):
        candidates.extend(item for item in raw if isinstance(item, str))
    issue = decision.get("observed_issue")
    if isinstance(issue, str):
        candidates.append(issue)
    elif isinstance(issue, dict) and isinstance(issue.get("description"), str):
        candidates.append(issue["description"])
    if not candidates:
        return
    existing = [str(item) for item in lockstep_state.get("hypotheses") or [] if item]
    seen = {item.lower() for item in existing}
    for candidate in candidates:
        text = " ".join(candidate.split())[:180]
        if not text or text.lower() in seen:
            continue
        existing.append(text)
        seen.add(text.lower())
    lockstep_state["hypotheses"] = existing[-12:]


def _sector_ids_from_state(state: dict[str, Any]) -> list[int]:
    visited = state.get("visited_sector_ids") or {}
    if isinstance(visited, dict):
        values = visited.keys()
    elif isinstance(visited, list):
        values = visited
    else:
        values = []
    sector_ids = []
    for value in values:
        try:
            sector_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(sector_ids))


def _extract_sector_ids(value: Any) -> list[int]:
    if not isinstance(value, dict):
        return []
    candidates: list[Any] = []
    for key in ("current_sector_id", "sector_id", "player_sector_id", "sector_index"):
        if value.get(key) is not None:
            candidates.append(value.get(key))
    for key in ("visited_sector_ids", "explored_sectors"):
        if isinstance(value.get(key), list):
            candidates.extend(value[key])
    variables = value.get("game_variables") if isinstance(value.get("game_variables"), dict) else {}
    for key in ("current_sector_id", "sector_id", "player_sector_id", "sector_index"):
        if variables.get(key) is not None:
            candidates.append(variables.get(key))
    sector_ids = []
    for candidate in candidates:
        try:
            sector_ids.append(int(candidate))
        except (TypeError, ValueError):
            continue
    return sector_ids


def _finalize_lockstep_decision(lockstep_state: dict[str, Any]) -> None:
    counts = list(lockstep_state.get("_new_cells_decision_counts", []))
    counts.append(lockstep_state.get("_new_cells_current", 0))
    lockstep_state["_new_cells_current"] = 0
    lockstep_state["_new_cells_decision_counts"] = counts[-5:]
    lockstep_state["new_cells_last_5_decisions"] = sum(counts[-5:])


def _compute_unvisited_quadrants(lockstep_state: dict[str, Any]) -> int | None:
    visited = lockstep_state.get("visited_cells") or {}
    if not visited:
        return 4
    cells = []
    for key in visited:
        parts = key.split("_")
        if len(parts) == 2:
            try:
                cells.append((int(parts[0]), int(parts[1])))
            except ValueError:
                continue
    if not cells:
        return None
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    mid_x = (min(xs) + max(xs)) / 2.0
    mid_y = (min(ys) + max(ys)) / 2.0
    nw = any(c[0] <= mid_x and c[1] <= mid_y for c in cells)
    ne = any(c[0] > mid_x and c[1] <= mid_y for c in cells)
    sw = any(c[0] <= mid_x and c[1] > mid_y for c in cells)
    se = any(c[0] > mid_x and c[1] > mid_y for c in cells)
    return 4 - sum(int(v) for v in (nw, ne, sw, se))


def _unique_lockstep_tick(state: dict[str, Any], lockstep_state: dict[str, Any]) -> int:
    previous = lockstep_state.get("last_tick")
    last_tick = int(previous) if previous is not None else -1
    raw_tick = _bounded_int(state.get("tic"), default=last_tick + 1, lower=0)
    tick = max(raw_tick, last_tick + 1)
    lockstep_state["last_tick"] = tick
    return tick


def _lockstep_progress_signature(state: dict[str, Any], navigation_info: dict[str, Any]) -> tuple:
    variables = normalize_variables(state)
    x = float(variables.get("x") or 0)
    y = float(variables.get("y") or 0)
    return (
        round(x / 128),
        round(y / 128),
        int(variables.get("kill_count") or 0),
        int(variables.get("item_count") or 0),
        int(variables.get("secret_count") or 0),
        int(navigation_info.get("cells_explored") or 0),
        len(navigation_info.get("keys_found") or []),
    )


def _state_report_call(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "service": "mcp-doom",
        "tool": "get_state",
        "input": {},
        "output": _json_safe(
            {
                **_compact_state_for_llm(state),
                "action_summary": {
                    "stop_reason": "episode_finished" if state.get("episode_finished") else "state_report",
                    "executor_control": False,
                    "lockstep_control": True,
                },
            }
        ),
    }


def _pwad_crash_fields(exc: Exception, stage: str) -> dict[str, Any]:
    raw_error = str(exc)
    summary = "PWAD crashed or failed to initialize under the configured ViZDoom/Freedoom test environment."
    if stage == "gameplay":
        summary = "PWAD runtime crashed or disconnected during the automated playthrough."
    return {
        "failure_category": PWAD_CRASH_CATEGORY,
        "failure_stage": stage,
        "failure_summary": summary,
        "failure_diagnostics": {
            "raw_error": raw_error,
            "exception_type": exc.__class__.__name__,
            "user_facing_outcome": PWAD_CRASH_CATEGORY,
        },
    }


def _infrastructure_failure_fields(exc: Exception, stage: str) -> dict[str, Any]:
    raw_error = str(exc)
    if stage == "mcp_connect_retry_exhausted":
        summary = "mcp-doom could not be reached or start_game did not respond after retrying."
    elif stage == "mcp_tool_timeout":
        summary = "mcp-doom stopped responding during an MCP tool call."
    else:
        summary = "The test infrastructure failed before the PWAD result could be classified."
    return {
        "failure_category": INFRASTRUCTURE_CATEGORY,
        "failure_stage": stage,
        "failure_summary": summary,
        "failure_diagnostics": {
            "raw_error": raw_error,
            "exception_type": exc.__class__.__name__,
            "user_facing_outcome": "infrastructure_error",
        },
    }


def _normalize_take_action_params(params: dict[str, Any]) -> dict[str, Any]:
    from app.services.run_constants import TAKE_ACTION_BINARY_BUTTONS, TAKE_ACTION_BUTTONS

    actions_source = params.get("actions")
    if not isinstance(actions_source, dict):
        actions_source = {key: value for key, value in params.items() if key in TAKE_ACTION_BUTTONS}

    actions: dict[str, float | int] = {}
    for key, value in actions_source.items():
        name = str(key).upper()
        if name not in TAKE_ACTION_BUTTONS:
            continue
        if name in TAKE_ACTION_BINARY_BUTTONS:
            actions[name] = 1 if _bounded_float(value, 0.0) > 0 else 0
        elif name in {"TURN_LEFT_RIGHT_DELTA", "LOOK_UP_DOWN_DELTA"}:
            actions[name] = round(max(-45.0, min(45.0, _bounded_float(value, 0.0))), 2)
        else:
            actions[name] = round(max(-50.0, min(50.0, _bounded_float(value, 0.0))), 2)

    return {
        "actions": actions,
        "tics": _bounded_int(params.get("tics"), default=4, lower=1, upper=8),
    }


def _bound_mcp_tool_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    from app.services.run_constants import COMPOUND_TELEMETRY_TOOLS, EXPLORE_MAX_TICS_UPPER

    if tool == "explore":
        params["max_tics"] = _bounded_int(
            params.get("max_tics"),
            default=EXPLORE_MAX_TICS_UPPER,
            lower=20,
            upper=EXPLORE_MAX_TICS_UPPER,
        )
        if "stop_on_enemy" in params:
            params["stop_on_enemy"] = bool(params["stop_on_enemy"])
        if "stop_on_item" in params:
            params["stop_on_item"] = bool(params["stop_on_item"])
    elif tool in {"aim_and_shoot", "strafe_and_shoot"}:
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=90, lower=10, upper=120)
        if "shots" in params:
            params["shots"] = _bounded_int(params.get("shots"), default=5, lower=1, upper=8)
        if tool == "strafe_and_shoot":
            direction = str(params.get("direction") or "auto").lower()
            params["direction"] = direction if direction in {"left", "right", "auto"} else "auto"
    elif tool == "move_to":
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=140, lower=20, upper=180)
        if "use" in params:
            params["use"] = bool(params["use"])
        if "stop_on_enemy" in params:
            params["stop_on_enemy"] = bool(params["stop_on_enemy"])
    elif tool == "retreat":
        params["tics"] = _bounded_int(params.get("tics"), default=35, lower=8, upper=70)
        if "backpedal" in params:
            params["backpedal"] = bool(params["backpedal"])
    if tool in COMPOUND_TELEMETRY_TOOLS and "telemetry_stride" in params:
        params["telemetry_stride"] = _bounded_int(params.get("telemetry_stride"), default=2, lower=1, upper=10)
    return params


def _normalize_mcp_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    from app.services.run_constants import OBJECT_ID_ALIASES, OBJECT_ID_TOOLS, TOOL_PARAM_ALLOWLIST

    if tool == "step":
        return params
    if tool == "take_action":
        return _normalize_take_action_params(params)

    if tool in OBJECT_ID_TOOLS and "object_id" not in params:
        for alias in OBJECT_ID_ALIASES.get(tool, ("object_id",)):
            if alias in params:
                params["object_id"] = params[alias]
                break

    if "object_id" in params:
        with contextlib.suppress(TypeError, ValueError):
            params["object_id"] = int(params["object_id"])

    allowed = TOOL_PARAM_ALLOWLIST.get(tool)
    if allowed is not None:
        params = {key: value for key, value in params.items() if key in allowed}

    return _bound_mcp_tool_params(tool, params)


def _compute_dynamic_throttle(
    state: dict[str, Any],
    lockstep_state: LockstepState,
    throttle_delays: dict[str, float] | None = None,
) -> float:
    variables = normalize_variables(state)
    objects = state.get("objects") or []
    visible_monsters = [o for o in objects if o.get("type") == "monster" and o.get("is_visible")]
    health = float(variables.get("health", 100))
    ammo_total = float(variables.get("ammo_total", 0))

    if throttle_delays:
        if visible_monsters:
            return throttle_delays.get("combat", 3.0)
        if health < 25 or ammo_total == 0:
            return throttle_delays.get("low_health", 6.0)
        if int(lockstep_state.get("no_progress_polls") or 0) >= 2:
            return throttle_delays.get("stuck", 10.0)
        return throttle_delays.get("default", 12.0)

    if visible_monsters:
        return 3.0

    if health < 25 or ammo_total == 0:
        return 6.0

    if int(lockstep_state.get("no_progress_polls") or 0) >= 2:
        return 10.0

    return 12.0


def _compute_dynamic_stride(
    state: dict[str, Any],
    lockstep_state: LockstepState,
    default_stride: int = 3,
    combat_stride: int = 1,
    stuck_stride: int = 5,
) -> int:
    variables = normalize_variables(state)
    objects = state.get("objects") or []
    visible_monsters = [o for o in objects if o.get("type") == "monster" and o.get("is_visible")]
    if visible_monsters:
        return combat_stride
    if int(lockstep_state.get("no_progress_polls") or 0) > 0:
        return stuck_stride
    return default_stride
