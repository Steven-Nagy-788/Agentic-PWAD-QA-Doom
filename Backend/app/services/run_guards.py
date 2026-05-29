from __future__ import annotations

import json
from typing import Any

from app.core.types import LockstepState
from app.services.collector_service import normalize_variables
from app.services.run_constants import (
    BLOCKED_DECISION_ABORT_THRESHOLD,
    CARDINAL_DIRECTION_ANGLES,
    COMBAT_TOOLS,
    EXPLORE_MAX_TICS_UPPER,
    LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD,
    LOW_VALUE_EXPLORE_STUCK_LIMIT,
    PICKUP_OBJECT_TYPES,
    QA_PROBE_BURST_LIMIT,
    REPEATED_ACTION_ABORT_THRESHOLD,
    STUCK_RUN_ABORT_THRESHOLD,
    WASTED_COMBAT_ABORT_THRESHOLD,
)
from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _compute_unvisited_quadrants,
    _int_like,
    _json_safe,
    _lockstep_progress_signature,
    _mcp_action_summary,
    _normalize_mcp_params,
)

MAX_USE_ATTEMPTS_BEFORE_CLEAR = 8

_RESOURCE_STOP_REASONS = {
    "out_of_ammo",
    "selected_weapon_empty",
    "no_usable_weapon",
    "no_usable_ranged_weapon",
    "melee_target_out_of_range",
    "weapon_switch_failed",
}


def _apply_lockstep_recovery(
    decision: dict[str, Any],
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: LockstepState,
) -> dict[str, Any]:
    use_attempts = int(lockstep_state.get("use_attempt_count") or 0)
    if use_attempts >= MAX_USE_ATTEMPTS_BEFORE_CLEAR:
        lockstep_state["use_attempt_count"] = 0
        lockstep_state["counter_hypothesis_added"] = False
        lockstep_state["hypothesis_repetition_counts"] = {}
        lockstep_state["hypotheses"] = []
        return {
            "reasoning_summary": (
                f"Excessive USE attempts ({use_attempts}) on nearby walls produced no response — "
                "this is likely a secret-hunting issue, not a geometry defect. "
                "Forcing wide exploration from a fresh angle."
            ),
            "mcp_tool": "explore",
            "mcp_params": {"max_tics": EXPLORE_MAX_TICS_UPPER, "stop_on_enemy": True, "stop_on_item": True},
            "observed_issue": None,
        }

    selected_tool = str(decision.get("mcp_tool") or "explore")
    low_value_explores = int(lockstep_state.get("low_value_explore_total") or 0)
    if selected_tool == "explore" and low_value_explores >= LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD:
        visible_combat = _visible_combat_recovery_decision(
            state,
            "A visible enemy is blocking useful exploration, so I am resolving the threat before probing geometry.",
        )
        if visible_combat is not None:
            return visible_combat
        probe_count = int(lockstep_state.get("qa_probe_count") or 0)
        if probe_count < QA_PROBE_BURST_LIMIT:
            return _qa_probe_decision(
                state,
                navigation_info,
                lockstep_state,
                (
                    "Recent explore calls consumed their tic budget without enemies, items, exits, or other QA "
                    "progress, so I am taking direct lockstep control to break the circular movement pattern."
                ),
            )
        lockstep_state["qa_probe_count"] = 0
        lockstep_state["low_value_explore_total"] = 0

    if bool(lockstep_state.get("counter_hypothesis_added")):
        lockstep_state["counter_hypothesis_added"] = False
        lockstep_state["hypothesis_repetition_counts"] = {}
        if _has_visible_combat_opportunity(state):
            if selected_tool in COMBAT_TOOLS:
                return decision
            visible_combat = _visible_combat_recovery_decision(
                state,
                "Repeated issue hypotheses are less useful than clearing the visible threat first.",
            )
            if visible_combat is not None:
                return visible_combat
        return {
            "reasoning_summary": (
                "Agent repeated the same issue category 3+ times. Forcing wide exploration "
                "from a fresh angle to break the fixation."
            ),
            "mcp_tool": "explore",
            "mcp_params": {"max_tics": EXPLORE_MAX_TICS_UPPER, "stop_on_enemy": True, "stop_on_item": True},
            "observed_issue": None,
        }

    signature = _lockstep_progress_signature(state, navigation_info)
    if signature != lockstep_state.get("last_signature"):
        lockstep_state["last_signature"] = signature
        lockstep_state["no_progress_polls"] = 0
        lockstep_state["should_stop_stuck"] = False
        return decision

    lockstep_state["no_progress_polls"] = int(lockstep_state.get("no_progress_polls") or 0) + 1
    if int(lockstep_state["no_progress_polls"]) < STUCK_RUN_ABORT_THRESHOLD:
        return decision

    recovery_count = int(lockstep_state.get("recovery_count") or 0) + 1
    lockstep_state["recovery_count"] = recovery_count
    lockstep_state["no_progress_polls"] = 0
    if recovery_count >= 4:
        lockstep_state["should_stop_stuck"] = True
    if recovery_count % 2:
        return _qa_probe_decision(
            state,
            navigation_info,
            lockstep_state,
            "Progress has not changed across repeated lockstep decisions, so I am forcing a bounded QA recovery probe.",
        )
    return {
        "reasoning_summary": (
            "The previous recovery did not create measurable progress, so I am exploring from the new angle with "
            "enemy and item stops enabled."
        ),
        "mcp_tool": "explore",
        "mcp_params": {"max_tics": EXPLORE_MAX_TICS_UPPER, "stop_on_enemy": True, "stop_on_item": True},
        "event_type_override": "stuck",
        "observed_issue": None,
    }


def _qa_probe_decision(
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: LockstepState,
    reason: str,
) -> dict[str, Any]:
    probe_index = int(lockstep_state.get("qa_probe_count") or 0)
    lockstep_state["qa_probe_count"] = probe_index + 1
    variables = normalize_variables(state)
    angle = _bounded_float(variables.get("angle"), 0.0)
    suggested = str(navigation_info.get("suggested_direction") or "").lower()
    nearby_doors = navigation_info.get("nearby_doors") if isinstance(navigation_info, dict) else None
    phase = probe_index % QA_PROBE_BURST_LIMIT

    if phase == 0 and isinstance(nearby_doors, list) and nearby_doors:
        return {
            "reasoning_summary": f"{reason} A nearby door-like sector is known, so I am pressing USE and nudging forward.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"USE": 1, "MOVE_FORWARD_BACKWARD_DELTA": 8}, "tics": 4},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    if phase == 0:
        turn = _turn_delta_for_direction(suggested, angle)
        if turn == 0:
            turn = 35.0
        return {
            "reasoning_summary": (
                f"{reason} I am facing a fresh unexplored direction first, then I will move in short bounded steps."
            ),
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"TURN_LEFT_RIGHT_DELTA": turn}, "tics": 1},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    if phase == 1:
        return {
            "reasoning_summary": f"{reason} I am advancing straight under direct control instead of letting explore arc in place.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"MOVE_FORWARD_BACKWARD_DELTA": 25, "SPEED": 1}, "tics": 6},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    if phase == 2:
        return {
            "reasoning_summary": f"{reason} I am probing for a switch or door interaction before declaring the area blocked.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"USE": 1}, "tics": 3},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    return {
        "reasoning_summary": f"{reason} The direct probes did not progress yet, so I am retreating and rotating out of the loop.",
        "mcp_tool": "retreat",
        "mcp_params": {"tics": 28, "backpedal": False},
        "event_type_override": "stuck",
        "observed_issue": None,
    }


def _turn_delta_for_direction(direction: str, current_angle: float) -> float:
    target_angle = CARDINAL_DIRECTION_ANGLES.get(direction)
    if target_angle is None:
        return 0.0
    diff = (target_angle - current_angle + 180.0) % 360.0 - 180.0
    return round(max(-45.0, min(45.0, -diff)), 1)


def _guard_lockstep_decision(
    decision: dict[str, Any],
    state: dict[str, Any],
    lockstep_state: LockstepState,
    navigation_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tool = decision.get("mcp_tool") or "explore"
    params = _normalize_mcp_params(tool, dict(decision.get("mcp_params") or {}))
    invisible_failures = lockstep_state.get("invisible_target_failures") or {}
    object_id = params.get("object_id")
    signature = _action_signature(tool, params)
    signature_count = int((lockstep_state.get("action_signature_counts") or {}).get(signature, 0))
    if signature_count >= REPEATED_ACTION_ABORT_THRESHOLD:
        visible_combat = _visible_combat_recovery_decision(
            state,
            f"The requested action repeats a recent no-progress signature ({tool}), but a visible enemy is actionable.",
        )
        if visible_combat is not None:
            return visible_combat
        return _blocked_decision_fallback(
            f"The requested action repeats a recent no-progress signature ({tool}), so I am switching tactics.",
            state,
            navigation_info or {},
            lockstep_state,
        )
    if tool == "explore" and _has_visible_combat_opportunity(state):
        recent_enemy_spotted = sum(
            1
            for entry in (lockstep_state.get("decision_history") or [])[-4:]
            if entry.get("tool") == "explore" and entry.get("stop_reason") == "enemy_spotted"
        )
        if recent_enemy_spotted:
            visible_combat = _visible_combat_recovery_decision(
                state,
                "Exploration has already stopped on this visible enemy, so I am engaging it instead of looping.",
            )
            if visible_combat is not None:
                return visible_combat
    if tool == "move_to" and object_id is not None:
        completed = lockstep_state.get("completed_object_ids") or {}
        failed = lockstep_state.get("failed_object_ids") or {}
        if str(object_id) in completed:
            return _blocked_decision_fallback(
                f"Object {object_id} was already reached or collected in this run, so I will not target it again.",
                state,
                navigation_info or {},
                lockstep_state,
            )
        if int(failed.get(str(object_id), 0) or 0) >= 2:
            return _blocked_decision_fallback(
                f"Object {object_id} has failed repeatedly, so I am changing route instead of looping on it.",
                state,
                navigation_info or {},
                lockstep_state,
            )
    if tool in COMBAT_TOOLS:
        if not _state_has_usable_attack_weapon(state):
            return _blocked_decision_fallback(
                "No usable attack weapon is currently available, so I need resources or space before forcing combat.",
                state,
                navigation_info or {},
                lockstep_state,
                prefer_resources=True,
            )
        if object_id is not None and str(object_id) in invisible_failures:
            return {
                "reasoning_summary": (
                    f"Target {object_id} was recently rejected as not visible, so I am exploring instead of firing "
                    "through geometry."
                ),
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": False},
                "observed_issue": None,
            }
    total_dc = int(lockstep_state.get("total_decision_count") or 0)
    priority_forced = int(lockstep_state.get("priority_pickup_forced_count") or 0)
    valid_visible_combat = (
        tool in COMBAT_TOOLS
        and _state_has_usable_attack_weapon(state)
        and _combat_target_is_visible(state, object_id)
    )
    if total_dc < 3 and priority_forced < 3 and tool != "move_to" and not valid_visible_combat:
        priority_pickup = _nearest_priority_pickup(state, lockstep_state)
        if priority_pickup is not None:
            lockstep_state["priority_pickup_forced_count"] = priority_forced + 1
            return {
                "reasoning_summary": (
                    f"Early-game priority: collecting {priority_pickup.get('name', 'pickup')} "
                    f"at distance {priority_pickup.get('distance', '?')} before engaging."
                ),
                "mcp_tool": "move_to",
                "mcp_params": {"object_id": priority_pickup["id"], "max_tics": 80, "stop_on_enemy": True},
                "observed_issue": None,
            }
        if not _combat_target_is_visible(state, object_id):
            return {
                "reasoning_summary": (
                    f"The requested combat target {object_id} is not a visible monster in the current state, so I am "
                    "switching to exploration rather than shooting through a wall."
                ),
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": False},
                "observed_issue": None,
            }
    if tool == "select_weapon" or (tool == "take_action" and _has_weapon_switch_action(params)):
        weapon_switch_count = 0
        for entry in (lockstep_state.get("decision_history") or [])[-5:]:
            if entry.get("tool") == "select_weapon" or entry.get("tool") == "take_action" and "SELECT_WEAPON" in str(entry.get("params", {})):
                weapon_switch_count += 1
            elif entry.get("tool") == "take_action" and "SELECT_NEXT_WEAPON" in str(entry.get("params", {})):
                weapon_switch_count += 1
        if weapon_switch_count >= 2:
            requested_slot = params.get("weapon_slot")
            best_weapon = _best_viable_weapon(state)
            selected_weapon = _selected_weapon(state)
            if (
                tool == "select_weapon"
                and best_weapon is not None
                and requested_slot == best_weapon
                and selected_weapon != best_weapon
                and _has_visible_combat_opportunity(state)
            ):
                decision["mcp_tool"] = tool
                decision["mcp_params"] = params
                return decision
            lockstep_state["quality_warnings"] = list(lockstep_state.get("quality_warnings") or []) + [
                f"Weapon switching loop detected ({weapon_switch_count}x in last 5 decisions), forcing explore instead."
            ]
            return {
                "reasoning_summary": (
                    f"Weapon switching detected {weapon_switch_count}x in recent decisions. "
                    "Forcing explore to break the loop."
                ),
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": True},
                "observed_issue": None,
            }

    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    return decision


def _has_weapon_switch_action(params: dict[str, Any]) -> bool:
    actions = params.get("actions") if isinstance(params, dict) else {}
    if not isinstance(actions, dict):
        return False
    for key in actions:
        if "SELECT_WEAPON" in str(key).upper() or "SELECT_NEXT" in str(key).upper() or "SELECT_PREV" in str(key).upper():
            return True
    return False


def _visible_combat_target(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    candidates = []
    for obj in state.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        if obj.get("id") is None or obj.get("type") != "monster" or not obj.get("is_visible"):
            continue
        candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: _bounded_float(obj.get("distance"), 999999.0))


def _has_visible_combat_opportunity(state: dict[str, Any] | None) -> bool:
    return _visible_combat_target(state) is not None and _state_has_usable_attack_weapon(state or {})


def _best_viable_weapon(state: dict[str, Any] | None) -> int | None:
    weapon_state = state.get("weapon_state") if isinstance(state, dict) else None
    if not isinstance(weapon_state, dict):
        return None
    value = weapon_state.get("best_viable_weapon")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _selected_weapon(state: dict[str, Any] | None) -> int | None:
    weapon_state = state.get("weapon_state") if isinstance(state, dict) else None
    if isinstance(weapon_state, dict):
        value = weapon_state.get("selected_weapon")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            pass
    variables = state.get("game_variables") if isinstance(state, dict) else None
    if isinstance(variables, dict):
        return _bounded_int(variables.get("SELECTED_WEAPON"), 2)
    return None


def _visible_combat_recovery_decision(state: dict[str, Any], reason: str) -> dict[str, Any] | None:
    target = _visible_combat_target(state)
    if target is None or not _state_has_usable_attack_weapon(state):
        return None
    target_id = target.get("id")
    if target_id is None:
        return None

    best_weapon = _best_viable_weapon(state)
    selected_weapon = _selected_weapon(state)
    weapon_state = state.get("weapon_state") if isinstance(state, dict) else {}
    usable_ranged = set()
    if isinstance(weapon_state, dict):
        for slot in weapon_state.get("usable_ranged_weapons") or []:
            try:
                usable_ranged.add(int(slot))
            except (TypeError, ValueError):
                continue
    distance = _bounded_float(target.get("distance"), 999999.0)
    if (
        best_weapon is not None
        and selected_weapon != best_weapon
        and best_weapon in usable_ranged
        and distance > 96.0
    ):
        return {
            "reasoning_summary": f"{reason} I am selecting weapon {best_weapon} before shooting.",
            "mcp_tool": "select_weapon",
            "mcp_params": {"weapon_slot": best_weapon, "max_tics": 12},
            "observed_issue": None,
        }

    return {
        "reasoning_summary": f"{reason} I am engaging visible target {target_id} instead of restarting exploration.",
        "mcp_tool": "aim_and_shoot",
        "mcp_params": {"object_id": target_id, "shots": 5, "max_tics": 100},
        "observed_issue": None,
    }


def _blocked_decision_fallback(
    reason: str,
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: LockstepState,
    prefer_resources: bool = False,
) -> dict[str, Any]:
    lockstep_state["blocked_decision_count"] = int(lockstep_state.get("blocked_decision_count") or 0) + 1
    warnings = list(lockstep_state.get("quality_warnings") or [])
    warnings.append(reason)
    lockstep_state["quality_warnings"] = warnings[-20:]
    if int(lockstep_state["blocked_decision_count"]) >= BLOCKED_DECISION_ABORT_THRESHOLD:
        lockstep_state["should_stop_stuck"] = True
        lockstep_state["stop_outcome"] = "inconclusive_agent_stall" if prefer_resources else "stuck"

    pickup = _nearest_available_pickup(state, lockstep_state, prefer_resources=prefer_resources)
    if pickup is not None:
        return {
            "reasoning_summary": f"{reason} I am switching to available pickup {pickup.get('name', 'object')} first.",
            "mcp_tool": "move_to",
            "mcp_params": {"object_id": pickup["id"], "max_tics": 80, "stop_on_enemy": True},
            "observed_issue": None,
        }
    if prefer_resources:
        weapon_state = state.get("weapon_state") if isinstance(state, dict) else {}
        best_weapon = weapon_state.get("best_viable_weapon") if isinstance(weapon_state, dict) else None
        if best_weapon is not None:
            return {
                "reasoning_summary": f"{reason} A usable weapon is known, so I am selecting weapon {best_weapon} before reassessing.",
                "mcp_tool": "select_weapon",
                "mcp_params": {"weapon_slot": best_weapon, "max_tics": 12},
                "event_type_override": "resource_recovery",
                "observed_issue": None,
            }
        return {
            "reasoning_summary": f"{reason} No visible pickup is available, so I am cycling weapons before reassessing.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"SELECT_NEXT_WEAPON": 1}, "tics": 2},
            "event_type_override": "resource_recovery",
            "observed_issue": None,
        }
    return _qa_probe_decision(state, navigation_info, lockstep_state, reason)


def _nearest_available_pickup(
    state: dict[str, Any],
    lockstep_state: LockstepState,
    prefer_resources: bool = False,
) -> dict[str, Any] | None:
    completed = {str(key) for key in (lockstep_state.get("completed_object_ids") or {})}
    failed = lockstep_state.get("failed_object_ids") or {}
    candidates = []
    for obj in state.get("objects") or []:
        if not isinstance(obj, dict) or obj.get("id") is None:
            continue
        if str(obj.get("id")) in completed or int(failed.get(str(obj.get("id")), 0) or 0) >= 2:
            continue
        obj_type = obj.get("type")
        if obj_type not in PICKUP_OBJECT_TYPES:
            continue
        if prefer_resources and obj_type not in {"ammo", "weapon", "item"}:
            continue
        obj_distance = float(obj.get("distance") or 999999)
        if not obj.get("is_visible"):
            if (
                not prefer_resources
                or obj_type not in {"weapon", "ammo", "item"}
                or obj_distance >= 100.0
            ):
                continue
        candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: float(obj.get("distance") or 999999))


def _nearest_priority_pickup(state: dict[str, Any], lockstep_state: LockstepState) -> dict[str, Any] | None:
    completed = {str(key) for key in (lockstep_state.get("completed_object_ids") or {})}
    failed = lockstep_state.get("failed_object_ids") or {}
    candidates = []
    for obj in state.get("objects") or []:
        if not isinstance(obj, dict) or obj.get("id") is None:
            continue
        if str(obj.get("id")) in completed or int(failed.get(str(obj.get("id")), 0) or 0) >= 2:
            continue
        obj_type = obj.get("type")
        if obj_type not in {"weapon", "ammo"}:
            continue
        obj_distance = float(obj.get("distance") or 999999)
        if obj_distance >= 100.0:
            continue
        candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: float(obj.get("distance") or 999999))


def _state_has_usable_attack_weapon(state: dict[str, Any]) -> bool:
    weapon_state = state.get("weapon_state") if isinstance(state, dict) else None
    if isinstance(weapon_state, dict):
        usable_weapons = weapon_state.get("usable_weapons")
        if isinstance(usable_weapons, list):
            return bool(usable_weapons)
        if _bounded_float(weapon_state.get("usable_attack_ammo"), 0.0) > 0:
            return True
    variables = state.get("game_variables") if isinstance(state, dict) else {}
    if not isinstance(variables, dict) or not variables:
        return True
    selected_weapon = _bounded_int(variables.get("SELECTED_WEAPON"), 2)
    selected_ammo = _bounded_float(variables.get("SELECTED_WEAPON_AMMO"), 0.0)
    weapon_inventory = variables.get("WEAPON_INVENTORY") or []
    if selected_weapon in {1, 8}:
        return True
    if selected_weapon == 0 and isinstance(weapon_inventory, list):
        equipped_names = weapon_state.get("weapon_inventory", []) if isinstance(weapon_state, dict) else []
        has_chainsaw = any("CHAINSAW" in str(w).upper() for w in equipped_names)
        selected_name = weapon_state.get("selected_weapon_name", "") if isinstance(weapon_state, dict) else ""
        if has_chainsaw or "CHAINSAW" in str(selected_name).upper():
            return True
        if not has_chainsaw and selected_weapon == 0:
            return False
    if selected_weapon == 0:
        return True
    if selected_ammo > 0:
        return True
    return any(_bounded_float(variables.get(f"AMMO{slot}"), 0.0) > 0 for slot in range(10))


def _weapon_resource_signature(mcp_call: dict[str, Any], stop_reason: str) -> str:
    state = _weapon_state_from_call(mcp_call)
    selected = state.get("selected_weapon", "unknown")
    selected_ammo = state.get("selected_weapon_ammo", "unknown")
    usable_attack_ammo = state.get("usable_attack_ammo", "unknown")
    return f"{stop_reason}:weapon={selected}:selected_ammo={selected_ammo}:usable_attack_ammo={usable_attack_ammo}"


def _weapon_resource_warning(object_id: Any, mcp_call: dict[str, Any], stop_reason: str) -> str:
    state = _weapon_state_from_call(mcp_call)
    selected = state.get("selected_weapon", "unknown")
    usable_attack_ammo = state.get("usable_attack_ammo", "unknown")
    target = f" against target {object_id}" if object_id is not None else ""
    return (
        f"Combat{target} stopped with {stop_reason} on weapon {selected}; "
        f"usable_attack_ammo={usable_attack_ammo}."
    )


def _weapon_state_from_call(mcp_call: dict[str, Any]) -> dict[str, Any]:
    output = mcp_call.get("output") if isinstance(mcp_call, dict) else None
    if not isinstance(output, dict):
        return {}
    summary = output.get("action_summary") if isinstance(output.get("action_summary"), dict) else {}
    for key in ("weapon_state_after", "weapon_state_before"):
        value = summary.get(key)
        if isinstance(value, dict):
            return value
    value = output.get("weapon_state")
    return value if isinstance(value, dict) else {}


def _action_signature(tool: str, params: dict[str, Any]) -> str:
    compact_params = {
        key: params.get(key)
        for key in sorted(params)
        if key not in {"capture_telemetry", "telemetry_stride"}
    }
    return f"{tool}:{json.dumps(_json_safe(compact_params), sort_keys=True, default=str)}"


def _update_lockstep_after_action(
    decision: dict[str, Any],
    mcp_call: dict[str, Any],
    lockstep_state: LockstepState,
) -> None:
    lockstep_state["total_decision_count"] = int(lockstep_state.get("total_decision_count") or 0) + 1
    summary = _mcp_action_summary(mcp_call)
    tool = str(mcp_call.get("tool") or decision.get("mcp_tool") or "")
    stop_reason = str(summary.get("stop_reason") or "")
    params = mcp_call.get("input") if isinstance(mcp_call.get("input"), dict) else {}
    object_id = params.get("object_id")
    signature = _action_signature(tool, params if isinstance(params, dict) else {})
    signature_counts = dict(lockstep_state.get("action_signature_counts") or {})
    signature_counts[signature] = int(signature_counts.get(signature, 0)) + 1
    lockstep_state["action_signature_counts"] = dict(list(signature_counts.items())[-50:])
    _record_attempted_interaction(tool, params, summary, lockstep_state)

    if tool == "explore" and stop_reason == "max_tics":
        lockstep_state["consecutive_explore_max_tics"] = int(lockstep_state.get("consecutive_explore_max_tics") or 0) + 1
        lockstep_state["low_value_explore_total"] = int(lockstep_state.get("low_value_explore_total") or 0) + 1
        lockstep_state["low_value_explore_cumulative"] = int(lockstep_state.get("low_value_explore_cumulative") or 0) + 1
    elif tool == "explore" and stop_reason in {"enemy_spotted", "item_found", "episode_finished", "player_died"}:
        lockstep_state["consecutive_explore_max_tics"] = 0
        lockstep_state["low_value_explore_total"] = 0
        lockstep_state["low_value_explore_cumulative"] = 0
        lockstep_state["qa_probe_count"] = 0
    elif tool in {"move_to", "aim_and_shoot", "strafe_and_shoot"} and stop_reason not in {"target_not_visible", "no_target"}:
        lockstep_state["consecutive_explore_max_tics"] = 0
        lockstep_state["low_value_explore_total"] = 0
        lockstep_state["low_value_explore_cumulative"] = 0
        lockstep_state["qa_probe_count"] = 0
    else:
        lockstep_state["consecutive_explore_max_tics"] = 0

    if (
        int(lockstep_state.get("low_value_explore_total") or 0) >= LOW_VALUE_EXPLORE_STUCK_LIMIT
        or int(lockstep_state.get("low_value_explore_cumulative") or 0) >= LOW_VALUE_EXPLORE_STUCK_LIMIT
    ):
        lockstep_state["should_stop_stuck"] = True

    if tool == "move_to" and object_id is not None:
        if stop_reason == "arrived":
            lockstep_state["invisible_target_failures"] = {}
            completed = dict(lockstep_state.get("completed_object_ids") or {})
            key = str(object_id)
            if key not in completed:
                lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 2
                lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
            completed[key] = {
                "target_name": summary.get("target_name"),
                "target_type": summary.get("target_type"),
                "stop_reason": stop_reason,
            }
            lockstep_state["completed_object_ids"] = completed
            lockstep_state["blocked_decision_count"] = 0
        elif stop_reason in {"stuck", "pickup_not_collected", "arrival_blocked", "target_lost", "max_tics", "enemy_nearby"}:
            failed = dict(lockstep_state.get("failed_object_ids") or {})
            key = str(object_id)
            failed[key] = int(failed.get(key, 0)) + 1
            lockstep_state["failed_object_ids"] = failed
    if tool in COMBAT_TOOLS and stop_reason in _RESOURCE_STOP_REASONS:
        resource_failures = dict(lockstep_state.get("weapon_resource_failures") or {})
        key = _weapon_resource_signature(mcp_call, stop_reason)
        resource_failures[key] = int(resource_failures.get(key, 0)) + 1
        lockstep_state["weapon_resource_failures"] = resource_failures
        warnings = list(lockstep_state.get("quality_warnings") or [])
        warnings.append(_weapon_resource_warning(object_id, mcp_call, stop_reason))
        lockstep_state["quality_warnings"] = warnings[-20:]
    if stop_reason in {"target_killed", "shots_complete"} and (_int_like(summary.get("hits_landed")) or _int_like(summary.get("kills"))):
        lockstep_state["invisible_target_failures"] = {}
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 3
        lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
        lockstep_state["blocked_decision_count"] = 0
    if stop_reason in {"item_found", "enemy_spotted"}:
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 1

    if tool == "take_action":
        actions = params.get("actions") if isinstance(params.get("actions"), dict) else {}
        if actions.get("USE") in (1, "1", True):
            lockstep_state["use_attempt_count"] = int(lockstep_state.get("use_attempt_count") or 0) + 1

    if summary.get("stop_reason") == "target_not_visible":
        params = decision.get("mcp_params") if isinstance(decision.get("mcp_params"), dict) else {}
        object_id = params.get("object_id")
        if object_id is not None:
            failures = dict(lockstep_state.get("invisible_target_failures") or {})
            failures[str(object_id)] = int(failures.get(str(object_id), 0)) + 1
            lockstep_state["invisible_target_failures"] = failures
    if _is_wasted_combat_decision(decision, mcp_call):
        lockstep_state["wasted_combat_count"] = int(lockstep_state.get("wasted_combat_count") or 0) + 1
    else:
        lockstep_state["wasted_combat_count"] = 0
    if int(lockstep_state.get("wasted_combat_count") or 0) >= WASTED_COMBAT_ABORT_THRESHOLD:
        lockstep_state["no_progress_polls"] = STUCK_RUN_ABORT_THRESHOLD


def _record_attempted_interaction(
    tool: str,
    params: dict[str, Any],
    summary: dict[str, Any],
    lockstep_state: LockstepState,
) -> None:
    stop_reason = str(summary.get("stop_reason") or "")
    object_id = params.get("object_id")
    attempt: dict[str, Any] = {
        "type": tool,
        "result": _interaction_result(tool, stop_reason),
    }
    if object_id is not None:
        attempt["object_id"] = object_id
    if stop_reason:
        attempt["stop_reason"] = stop_reason
    for source_key, target_key in (("target_name", "target_name"), ("target_type", "target_type")):
        if summary.get(source_key) is not None:
            attempt[target_key] = summary[source_key]
    attempts = list(lockstep_state.get("attempted_interactions") or [])
    attempts.append(attempt)
    lockstep_state["attempted_interactions"] = attempts[-30:]


def _interaction_result(tool: str, stop_reason: str) -> str:
    if stop_reason in {"arrival_blocked", "stuck"}:
        return "blocked_by_collision"
    if stop_reason == "arrived":
        return "reached"
    if stop_reason == "target_not_visible":
        return "target_not_visible"
    if stop_reason in _RESOURCE_STOP_REASONS:
        return stop_reason
    if stop_reason in {"pickup_not_collected", "target_lost", "max_tics", "enemy_nearby"}:
        return "unreachable_or_interrupted"
    if stop_reason in {"target_killed", "shots_complete"}:
        return "combat_executed"
    if tool == "take_action" and stop_reason in {"", "tics_complete"}:
        return "probe_executed"
    return stop_reason or "executed"


def _lockstep_should_stop_as_stuck(lockstep_state: LockstepState) -> bool:
    return bool(lockstep_state.get("should_stop_stuck"))


def _lockstep_stop_outcome(lockstep_state: LockstepState) -> str:
    outcome = str(lockstep_state.get("stop_outcome") or "stuck")
    return outcome if outcome in {"stuck", "incomplete_coverage", "inconclusive_agent_stall"} else "stuck"


def _lockstep_progress_metrics(lockstep_state: LockstepState) -> dict[str, Any]:
    visited_cells_count = len(lockstep_state.get("visited_cells") or {})
    total_cells = lockstep_state.get("total_map_cells_estimate")
    coverage_percent = None
    if total_cells:
        coverage_percent = round((visited_cells_count / max(int(total_cells), 1)) * 100, 1)
    return {
        "progress_score": int(lockstep_state.get("progress_score") or 0),
        "meaningful_progress_events": int(lockstep_state.get("meaningful_progress_events") or 0),
        "completed_object_count": len(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_count": len(lockstep_state.get("failed_object_ids") or {}),
        "out_of_ammo_target_count": len(lockstep_state.get("out_of_ammo_targets") or {}),
        "weapon_resource_failure_count": len(lockstep_state.get("weapon_resource_failures") or {}),
        "blocked_decision_count": int(lockstep_state.get("blocked_decision_count") or 0),
        "low_value_explore_count": int(lockstep_state.get("low_value_explore_cumulative") or 0),
        "recovery_count": int(lockstep_state.get("recovery_count") or 0),
        "visited_cells_count": visited_cells_count,
        "total_map_cells_estimate": total_cells,
        "coverage_percent": coverage_percent,
        "new_cells_last_5_decisions": int(lockstep_state.get("new_cells_last_5_decisions") or 0),
        "unvisited_quadrants": _compute_unvisited_quadrants(lockstep_state),
    }


def _lockstep_quality_flags(lockstep_state: LockstepState, recording_metadata: dict[str, Any]) -> dict[str, Any]:
    warnings = list(lockstep_state.get("quality_warnings") or [])
    warnings.extend(recording_metadata.get("validation_warnings") or [])
    return {
        "quality_status": "warning" if warnings else "ok",
        "warnings": warnings[-30:],
        "completed_object_ids": dict(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_ids": dict(lockstep_state.get("failed_object_ids") or {}),
        "out_of_ammo_targets": dict(lockstep_state.get("out_of_ammo_targets") or {}),
        "weapon_resource_failures": dict(lockstep_state.get("weapon_resource_failures") or {}),
    }


def _is_stuck_decision(event: Any, mcp_call: dict[str, Any]) -> bool:
    if getattr(event, "event_type", None) == "stuck":
        return True
    summary = _mcp_action_summary(mcp_call)
    return summary.get("stop_reason") == "stuck"


def _is_wasted_combat_decision(decision: dict[str, Any], mcp_call: dict[str, Any]) -> bool:
    if decision.get("mcp_tool") not in COMBAT_TOOLS:
        return False
    summary = _mcp_action_summary(mcp_call)
    stop_reason = summary.get("stop_reason")
    if stop_reason == "target_not_visible":
        return True
    shots = _int_like(summary.get("shots_fired"))
    hits = _int_like(summary.get("hits_landed"))
    kills = _int_like(summary.get("kills"))
    return shots > 0 and hits == 0 and kills == 0


def _combat_target_is_visible(state: dict[str, Any] | None, object_id: Any) -> bool:
    if object_id is None or not isinstance(state, dict):
        return False
    for obj in state.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        if obj.get("id") == object_id and obj.get("type") == "monster":
            return bool(obj.get("is_visible"))
    return False
