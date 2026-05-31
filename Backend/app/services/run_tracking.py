from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.core.types import LockstepState
from app.services.analysis_constants import CELL_SIZE
from app.services.collector_service import normalize_variables
from app.services.run_constants import COMBAT_TOOLS
from app.services.run_utils import _compute_unvisited_quadrants, _int_like, _json_safe, _mcp_action_summary


_RESOURCE_STOP_REASONS = {
    "out_of_ammo",
    "selected_weapon_empty",
    "no_usable_weapon",
    "no_usable_ranged_weapon",
    "melee_target_out_of_range",
    "weapon_switch_failed",
}


def _action_signature(tool: str, params: dict[str, Any]) -> str:
    compact = {
        key: params.get(key)
        for key in sorted(params)
        if key not in {"capture_telemetry", "telemetry_stride"}
    }
    return f"{tool}:{json.dumps(_json_safe(compact), sort_keys=True, default=str)}"


def _update_lockstep_after_action(
    decision: dict[str, Any],
    mcp_call: dict[str, Any],
    lockstep_state: LockstepState,
    state_after: dict[str, Any] | None = None,
) -> None:
    lockstep_state["total_decision_count"] = int(lockstep_state.get("total_decision_count") or 0) + 1
    summary = _mcp_action_summary(mcp_call)
    tool = str(mcp_call.get("tool") or decision.get("mcp_tool") or "")
    stop_reason = str(summary.get("stop_reason") or "")
    params = mcp_call.get("input") if isinstance(mcp_call.get("input"), dict) else {}
    object_id = params.get("object_id")
    signature = _action_signature(tool, params)
    signature_counts = dict(lockstep_state.get("action_signature_counts") or {})
    signature_counts[signature] = int(signature_counts.get(signature, 0)) + 1
    lockstep_state["action_signature_counts"] = dict(list(signature_counts.items())[-50:])
    _record_attempted_interaction(tool, params, summary, lockstep_state)

    if tool == "explore" and stop_reason == "max_tics":
        lockstep_state["low_value_explore_cumulative"] = int(lockstep_state.get("low_value_explore_cumulative") or 0) + 1
    if stop_reason == "invalid_params":
        lockstep_state["blocked_decision_count"] = int(lockstep_state.get("blocked_decision_count") or 0) + 1

    if tool == "move_to" and object_id is not None:
        key = str(object_id)
        if stop_reason == "arrived":
            completed = dict(lockstep_state.get("completed_object_ids") or {})
            if key not in completed:
                lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 2
                lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
            completed[key] = {
                "target_name": summary.get("target_name"),
                "target_type": summary.get("target_type"),
                "stop_reason": stop_reason,
            }
            lockstep_state["completed_object_ids"] = completed
        elif stop_reason in {"stuck", "pickup_not_collected", "arrival_blocked", "target_lost", "max_tics", "enemy_nearby"}:
            failed = dict(lockstep_state.get("failed_object_ids") or {})
            failed[key] = int(failed.get(key, 0)) + 1
            lockstep_state["failed_object_ids"] = failed

    if tool in COMBAT_TOOLS and stop_reason in _RESOURCE_STOP_REASONS:
        resource_failures = dict(lockstep_state.get("weapon_resource_failures") or {})
        key = _weapon_resource_signature(mcp_call, stop_reason)
        resource_failures[key] = int(resource_failures.get(key, 0)) + 1
        lockstep_state["weapon_resource_failures"] = resource_failures
        _append_warning(lockstep_state, _weapon_resource_warning(object_id, mcp_call, stop_reason))

    if stop_reason in {"target_killed", "shots_complete"} and (
        _int_like(summary.get("hits_landed")) or _int_like(summary.get("kills"))
    ):
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 3
        lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
    elif stop_reason in {"item_found", "enemy_spotted"}:
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 1

    if stop_reason == "target_not_visible" and object_id is not None:
        failures = dict(lockstep_state.get("invisible_target_failures") or {})
        failures[str(object_id)] = int(failures.get(str(object_id), 0)) + 1
        lockstep_state["invisible_target_failures"] = failures

    _update_no_progress_stall(state_after, lockstep_state)


def _update_no_progress_stall(state_after: dict[str, Any] | None, lockstep_state: LockstepState) -> None:
    if not isinstance(state_after, dict):
        return
    variables = normalize_variables(state_after)
    signature = (
        round(float(variables.get("x") or 0) / CELL_SIZE),
        round(float(variables.get("y") or 0) / CELL_SIZE),
        int(variables.get("kill_count") or 0),
        int(variables.get("item_count") or 0),
        int(variables.get("secret_count") or 0),
        len(lockstep_state.get("completed_object_ids") or {}),
        int(lockstep_state.get("progress_score") or 0),
    )
    if signature == lockstep_state.get("last_progress_signature"):
        lockstep_state["no_progress_polls"] = int(lockstep_state.get("no_progress_polls") or 0) + 1
    else:
        lockstep_state["last_progress_signature"] = signature
        lockstep_state["no_progress_polls"] = 0
    threshold = get_settings().no_progress_decision_abort_threshold
    if int(lockstep_state.get("no_progress_polls") or 0) >= threshold:
        lockstep_state["should_stop_stuck"] = True
        lockstep_state["stop_outcome"] = "inconclusive_agent_stall"
        _append_warning(
            lockstep_state,
            f"Run stopped after {threshold} consecutive decisions without measurable gameplay progress.",
        )


def _record_attempted_interaction(
    tool: str,
    params: dict[str, Any],
    summary: dict[str, Any],
    lockstep_state: LockstepState,
) -> None:
    stop_reason = str(summary.get("stop_reason") or "")
    attempt: dict[str, Any] = {"type": tool, "result": _interaction_result(tool, stop_reason)}
    if params.get("object_id") is not None:
        attempt["object_id"] = params["object_id"]
    if stop_reason:
        attempt["stop_reason"] = stop_reason
    for key in ("target_name", "target_type"):
        if summary.get(key) is not None:
            attempt[key] = summary[key]
    attempts = list(lockstep_state.get("attempted_interactions") or [])
    attempts.append(attempt)
    lockstep_state["attempted_interactions"] = attempts[-30:]


def _interaction_result(tool: str, stop_reason: str) -> str:
    if stop_reason in {"arrival_blocked", "stuck"}:
        return "blocked_by_collision"
    if stop_reason == "arrived":
        return "reached"
    if stop_reason in _RESOURCE_STOP_REASONS or stop_reason == "target_not_visible":
        return stop_reason
    if stop_reason in {"pickup_not_collected", "target_lost", "max_tics", "enemy_nearby"}:
        return "unreachable_or_interrupted"
    if stop_reason in {"target_killed", "shots_complete"}:
        return "combat_executed"
    if tool == "take_action" and stop_reason in {"", "tics_complete"}:
        return "action_executed"
    return stop_reason or "executed"


def _weapon_resource_signature(mcp_call: dict[str, Any], stop_reason: str) -> str:
    state = _weapon_state_from_call(mcp_call)
    return (
        f"{stop_reason}:weapon={state.get('selected_weapon', 'unknown')}:"
        f"selected_ammo={state.get('selected_weapon_ammo', 'unknown')}:"
        f"usable_attack_ammo={state.get('usable_attack_ammo', 'unknown')}"
    )


def _weapon_resource_warning(object_id: Any, mcp_call: dict[str, Any], stop_reason: str) -> str:
    state = _weapon_state_from_call(mcp_call)
    target = f" against target {object_id}" if object_id is not None else ""
    return (
        f"Combat{target} stopped with {stop_reason} on weapon {state.get('selected_weapon', 'unknown')}; "
        f"usable_attack_ammo={state.get('usable_attack_ammo', 'unknown')}."
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


def _append_warning(lockstep_state: LockstepState, warning: str) -> None:
    warnings = list(lockstep_state.get("quality_warnings") or [])
    if warning not in warnings:
        warnings.append(warning)
    lockstep_state["quality_warnings"] = warnings[-30:]


def _lockstep_should_stop_as_stuck(lockstep_state: LockstepState) -> bool:
    return bool(lockstep_state.get("should_stop_stuck"))


def _lockstep_stop_outcome(lockstep_state: LockstepState) -> str:
    return "inconclusive_agent_stall"


def _lockstep_progress_metrics(lockstep_state: LockstepState) -> dict[str, Any]:
    visited_count = len(lockstep_state.get("visited_cells") or {})
    total_cells = lockstep_state.get("total_map_cells_estimate")
    return {
        "progress_score": int(lockstep_state.get("progress_score") or 0),
        "meaningful_progress_events": int(lockstep_state.get("meaningful_progress_events") or 0),
        "completed_object_count": len(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_count": len(lockstep_state.get("failed_object_ids") or {}),
        "weapon_resource_failure_count": len(lockstep_state.get("weapon_resource_failures") or {}),
        "blocked_decision_count": int(lockstep_state.get("blocked_decision_count") or 0),
        "low_value_explore_count": int(lockstep_state.get("low_value_explore_cumulative") or 0),
        "visited_cells_count": visited_count,
        "total_map_cells_estimate": total_cells,
        "coverage_percent": round(visited_count / max(int(total_cells), 1) * 100, 1) if total_cells else None,
        "new_cells_last_5_decisions": int(lockstep_state.get("new_cells_last_5_decisions") or 0),
        "unvisited_quadrants": _compute_unvisited_quadrants(lockstep_state),
        "consecutive_no_progress_decisions": int(lockstep_state.get("no_progress_polls") or 0),
    }


def _lockstep_quality_flags(lockstep_state: LockstepState, recording_metadata: dict[str, Any]) -> dict[str, Any]:
    warnings = list(lockstep_state.get("quality_warnings") or [])
    warnings.extend(recording_metadata.get("validation_warnings") or [])
    return {
        "quality_status": "warning" if warnings else "ok",
        "warnings": warnings[-30:],
        "completed_object_ids": dict(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_ids": dict(lockstep_state.get("failed_object_ids") or {}),
        "weapon_resource_failures": dict(lockstep_state.get("weapon_resource_failures") or {}),
    }
