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
    _int_like,
    _json_safe,
    _lockstep_progress_signature,
    _mcp_action_summary,
    _normalize_mcp_params,
)


def _apply_lockstep_recovery(
    decision: dict[str, Any],
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: LockstepState,
) -> dict[str, Any]:
    selected_tool = str(decision.get("mcp_tool") or "explore")
    low_value_explores = int(lockstep_state.get("low_value_explore_total") or 0)
    if selected_tool == "explore" and low_value_explores >= LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD:
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
        return _blocked_decision_fallback(
            f"The requested action repeats a recent no-progress signature ({tool}), so I am switching tactics.",
            state,
            navigation_info or {},
            lockstep_state,
        )
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
        out_of_ammo_targets = lockstep_state.get("out_of_ammo_targets") or {}
        if object_id is not None and str(object_id) in out_of_ammo_targets:
            return _blocked_decision_fallback(
                f"Combat target {object_id} already returned out_of_ammo, so I need resources or another tactic first.",
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
    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    return decision


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
        lockstep_state["stop_outcome"] = "stuck"

    pickup = _nearest_available_pickup(state, lockstep_state, prefer_resources=prefer_resources)
    if pickup is not None:
        return {
            "reasoning_summary": f"{reason} I am switching to available pickup {pickup.get('name', 'object')} first.",
            "mcp_tool": "move_to",
            "mcp_params": {"object_id": pickup["id"], "max_tics": 80, "stop_on_enemy": True},
            "event_type_override": "stuck",
            "observed_issue": None,
        }
    if prefer_resources:
        return {
            "reasoning_summary": f"{reason} No visible pickup is available, so I am switching weapon before reassessing.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"SELECT_NEXT_WEAPON": 1}, "tics": 2},
            "event_type_override": "stuck",
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
        if not obj.get("is_visible"):
            continue
        candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: float(obj.get("distance") or 999999))


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
    if tool in COMBAT_TOOLS and stop_reason == "out_of_ammo" and object_id is not None:
        out_of_ammo = dict(lockstep_state.get("out_of_ammo_targets") or {})
        key = str(object_id)
        out_of_ammo[key] = int(out_of_ammo.get(key, 0)) + 1
        lockstep_state["out_of_ammo_targets"] = out_of_ammo
        warnings = list(lockstep_state.get("quality_warnings") or [])
        warnings.append(f"Combat against target {object_id} stopped with out_of_ammo.")
        lockstep_state["quality_warnings"] = warnings[-20:]
    if stop_reason in {"target_killed", "shots_complete"} and (_int_like(summary.get("hits_landed")) or _int_like(summary.get("kills"))):
        lockstep_state["invisible_target_failures"] = {}
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 3
        lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
        lockstep_state["blocked_decision_count"] = 0
    if stop_reason in {"item_found", "enemy_spotted"}:
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 1

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
    if stop_reason == "out_of_ammo":
        return "out_of_ammo"
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
    return outcome if outcome in {"stuck", "incomplete_coverage"} else "stuck"


def _lockstep_progress_metrics(lockstep_state: LockstepState) -> dict[str, Any]:
    return {
        "progress_score": int(lockstep_state.get("progress_score") or 0),
        "meaningful_progress_events": int(lockstep_state.get("meaningful_progress_events") or 0),
        "completed_object_count": len(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_count": len(lockstep_state.get("failed_object_ids") or {}),
        "out_of_ammo_target_count": len(lockstep_state.get("out_of_ammo_targets") or {}),
        "blocked_decision_count": int(lockstep_state.get("blocked_decision_count") or 0),
        "low_value_explore_count": int(lockstep_state.get("low_value_explore_cumulative") or 0),
        "recovery_count": int(lockstep_state.get("recovery_count") or 0),
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
