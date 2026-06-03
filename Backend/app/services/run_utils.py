from __future__ import annotations

import contextlib
import json
from collections import Counter
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
    return get_profile(get_settings().default_agent_behavior)


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
    compact = {key: value for key, value in state.items() if key not in {"screenshot_png", "sectors", "depth"}}
    variables = compact.get("game_variables")
    if isinstance(variables, dict):
        variable_names = {
            "HEALTH", "ARMOR", "POSITION_X", "POSITION_Y", "POSITION_Z", "ANGLE",
            "SELECTED_WEAPON", "SELECTED_WEAPON_AMMO", "KILLCOUNT", "ITEMCOUNT",
            "SECRETCOUNT", "AMMO0", "AMMO1", "AMMO2", "AMMO3", "AMMO4", "AMMO5",
            "AMMO6", "AMMO7", "AMMO8", "AMMO9",
        }
        compact["game_variables"] = {
            key: value for key, value in variables.items() if str(key).upper() in variable_names
        }
    if isinstance(compact.get("weapon_state"), dict):
        compact["weapon_state"] = _compact_weapon_state_for_llm(compact["weapon_state"])
    if isinstance(compact.get("objects"), list):
        objects = []
        for obj in compact["objects"]:
            if not isinstance(obj, dict):
                continue
            if obj.get("type") in {"player", "decoration", "projectile"} or obj.get("is_visible") is False:
                continue
            dist = float(obj.get("distance") or 999999)
            if obj.get("type") == "monster":
                if dist <= 128:
                    weapon_advice = "melee viable"
                elif dist <= 512:
                    weapon_advice = "shotgun effective"
                else:
                    weapon_advice = "use ranged (pistol/chaingun)"
            else:
                weapon_advice = "pickup"
            entry = {
                key: obj.get(key)
                for key in (
                    "id",
                    "name",
                    "type",
                    "distance",
                    "angle_to_aim",
                    "is_visible",
                )
                if key in obj
            }
            entry["weapon_advice"] = weapon_advice
            objects.append(entry)
        visible_first = [o for o in objects if o.get("is_visible") is True][:5]
        non_visible = [o for o in objects if o.get("is_visible") is not True][:3]
        compact["objects"] = visible_first + non_visible
    return _json_safe(compact)


def _compact_weapon_state_for_llm(state: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: state.get(key)
        for key in (
            "selected_weapon",
            "selected_weapon_name",
            "selected_weapon_ammo",
            "usable_weapons",
            "usable_attack_ammo",
            "best_viable_weapon",
            "melee_available",
        )
        if key in state
    }
    usable = state.get("usable_weapons")
    if isinstance(usable, list) and len(usable) <= 3:
        inventory = state.get("weapon_inventory")
        if isinstance(inventory, list):
            compact["owned_weapons"] = [
                {"slot": w["slot"], "name": w["name"], "ammo": w.get("ammo")}
                for w in inventory
                if isinstance(w, dict) and (w.get("owned") or w.get("selected"))
            ][:4]
    return compact


def _compact_context_for_llm(context: dict[str, Any], *, list_limit: int = 5) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in context.items():
        if key in {"objects", "visible_objects", "weapon_state", "game_variables", "tic", "tick"}:
            continue
        if key == "threats" and isinstance(value, list):
            compact[key] = [
                {
                    threat_key: threat.get(threat_key)
                    for threat_key in ("id", "name", "type", "distance", "attack_type", "is_visible")
                    if threat_key in threat
                }
                if isinstance(threat, dict)
                else threat
                for threat in value
                if not isinstance(threat, dict) or threat.get("is_visible") is not False
            ]
            compact[key] = compact[key][:list_limit]
        else:
            compact[key] = value[:list_limit] if isinstance(value, list) else value
    return _json_safe(compact)


def _build_llm_input(
    state: dict[str, Any],
    threat_assessment: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: LockstepState,
    *,
    game_tic: int,
    ticks_remaining: int,
    total_cells: int,
    coverage_warning: str | None,
) -> dict[str, Any]:
    variables = normalize_variables(state)
    objects = _compact_state_for_llm(state).get("objects") or []
    visible_threats = [
        threat
        for threat in threat_assessment.get("threats") or []
        if isinstance(threat, dict) and threat.get("is_visible") is not False
    ][:5]
    occluded_count = sum(
        1
        for threat in threat_assessment.get("threats") or []
        if isinstance(threat, dict) and threat.get("is_visible") is False
    )
    visited_count = len(lockstep_state.get("visited_cells") or {})
    return _json_safe(
        {
            "game_tic": game_tic,
            "ticks_remaining": ticks_remaining,
            "player": {
                "health": variables.get("health"),
                "armor": variables.get("armor"),
                "position": {"x": variables.get("x"), "y": variables.get("y")},
                "angle": variables.get("angle"),
                "kills": variables.get("kill_count"),
                "items": variables.get("item_count"),
                "secrets": variables.get("secret_count"),
            },
            "weapon_state": _compact_weapon_state_for_llm(state.get("weapon_state") or {}),
            "scene_objects": objects[:8],
            "threat_summary": {
                "threat_level": threat_assessment.get("threat_level"),
                "visible_attackable_threats": [
                    {
                        key: threat.get(key)
                        for key in ("id", "name", "type", "distance", "attack_type")
                        if key in threat
                    }
                    for threat in visible_threats
                ],
                "occluded_threat_count": occluded_count,
                "incoming_projectile_count": threat_assessment.get("incoming_projectile_count", 0),
            },
            "navigation": _compact_context_for_llm(navigation_info, list_limit=8),
            "coverage": {
                "visited_cells_count": visited_count,
                "total_map_cells_estimate": total_cells,
                "coverage_percent": round(visited_count / max(total_cells, 1) * 100, 1),
                "new_cells_last_5_decisions": int(lockstep_state.get("new_cells_last_5_decisions") or 0),
                "unvisited_quadrants": _compute_unvisited_quadrants(lockstep_state),
                "warning": coverage_warning,
            },
            "navigation_hints": {
                "suggested_turn_degrees": navigation_info.get("suggested_turn_delta", 0),
                "facing_unexplored": navigation_info.get("suggested_direction") is not None,
                "recent_stuck_events": int(lockstep_state.get("position_stuck_counter") or 0),
                "consecutive_same_tool": int(lockstep_state.get("consecutive_get_state") or 0),
            },
            "same_run_memory": _build_same_run_memory(lockstep_state),
        }
    )


def _build_same_run_memory(
    state: LockstepState,
    *,
    max_chars: int | None = None,
    recent_action_limit: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    char_limit = max_chars or settings.same_run_ledger_max_chars
    detail_limit = recent_action_limit or settings.same_run_ledger_recent_actions
    all_actions = list(state.get("decision_history") or [])
    split_at = max(0, len(all_actions) - detail_limit)
    older = all_actions[:split_at]
    recent = all_actions[split_at:]

    while True:
        projected = {
            "older_milestones": _build_older_milestones(older, state),
            "recent_actions": recent,
            "aggregates": _build_ledger_aggregates(all_actions, state),
            "budget": _build_budget_summary(state),
        }
        if _serialized_size(projected) <= char_limit:
            return projected
        if not recent:
            return _minimal_ledger_projection(all_actions, state)
        older.append(recent.pop(0))


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), default=str))


def _minimal_ledger_projection(actions: list[dict[str, Any]], state: LockstepState) -> dict[str, Any]:
    """Keep every older action represented by deterministic counts under extreme pressure."""
    tool_counts = dict(Counter(str(item.get("tool") or "unknown") for item in actions))
    stop_counts = dict(Counter(str(item.get("stop_reason") or "unknown") for item in actions))
    return {
        "older_milestones": {
            "compacted_action_count": len(actions),
            "tool_counts": tool_counts,
            "stop_reason_counts": stop_counts,
        },
        "recent_actions": [],
        "aggregates": {
            "total_actions": len(actions),
            "combat": _combat_summary_from_actions(actions),
        },
        "budget": _build_budget_summary(state),
    }


def _build_older_milestones(actions: list[dict[str, Any]], state: LockstepState) -> dict[str, Any]:
    return {
        "compacted_action_count": len(actions),
        "tool_counts": dict(Counter(str(item.get("tool") or "unknown") for item in actions)),
        "stop_reason_counts": dict(Counter(str(item.get("stop_reason") or "unknown") for item in actions)),
        "completed_targets": _tail_dict(state.get("completed_object_ids"), 24),
        "failed_targets": _tail_dict(state.get("failed_object_ids"), 24),
        "checkpoints": list(state.get("checkpoints") or [])[-12:],
        "hypotheses": list(state.get("hypotheses") or [])[-8:],
    }


def _build_ledger_aggregates(actions: list[dict[str, Any]], state: LockstepState) -> dict[str, Any]:
    combat_attempts = state.get("combat_attempts") or {}
    return {
        "total_actions": len(actions),
        "tool_counts": dict(Counter(str(item.get("tool") or "unknown") for item in actions)),
        "stop_reason_counts": dict(Counter(str(item.get("stop_reason") or "unknown") for item in actions)),
        "combat": _build_combat_summary(combat_attempts) if combat_attempts else _combat_summary_from_actions(actions),
        "progress_score": int(state.get("progress_score") or 0),
        "meaningful_progress_events": int(state.get("meaningful_progress_events") or 0),
        "runtime_warnings": list(state.get("quality_warnings") or [])[-8:],
    }


def _build_combat_summary(attempts: dict) -> dict[str, Any]:
    if not attempts:
        return {"total_engagements": 0}
    enemies = sorted(attempts.values(), key=lambda e: e.get("shots", 0), reverse=True)
    weapons: dict[str, dict] = {}
    for e in enemies:
        w = e.get("weapon", "unknown")
        if w not in weapons:
            weapons[w] = {"shots": 0, "hits": 0, "kills": 0}
        weapons[w]["shots"] += e.get("shots", 0)
        weapons[w]["hits"] += e.get("hits", 0)
        if e.get("killed"):
            weapons[w]["kills"] += 1
    for w in weapons:
        s = weapons[w]["shots"]
        weapons[w]["accuracy"] = round(weapons[w]["hits"] / s, 3) if s > 0 else 0
    kills = sum(1 for e in enemies if e.get("killed"))
    total_shots = sum(e.get("shots", 0) for e in enemies)
    total_hits = sum(e.get("hits", 0) for e in enemies)
    return {
        "total_engagements": len(enemies),
        "total_kills": kills,
        "total_shots": total_shots,
        "total_hits": total_hits,
        "enemies_engaged": [
            {
                key: enemy.get(key)
                for key in ("id", "name", "shots", "hits", "killed", "damage_dealt")
                if key in enemy
            }
            for enemy in enemies[:3]
        ],
        "weapon_performance": weapons,
    }


def _combat_summary_from_actions(actions: list[dict[str, Any]]) -> dict[str, Any]:
    combat_rows = [
        row.get("combat")
        for row in actions
        if isinstance(row.get("combat"), dict) and row.get("combat")
    ]
    if not combat_rows:
        return {"total_engagements": 0}
    weapons: dict[str, dict[str, int | float]] = {}
    for row in combat_rows:
        weapon = str(row.get("weapon_used") or "unknown")
        weapon_summary = weapons.setdefault(weapon, {"shots": 0, "hits": 0, "kills": 0})
        weapon_summary["shots"] += _int_like(row.get("shots_fired"))
        weapon_summary["hits"] += _int_like(row.get("hits_landed"))
        weapon_summary["kills"] += _int_like(row.get("kills"))
    for summary in weapons.values():
        shots = summary["shots"]
        summary["accuracy"] = round(summary["hits"] / shots, 3) if shots else 0
    return {
        "total_engagements": len(combat_rows),
        "total_kills": sum(_int_like(row.get("kills")) for row in combat_rows),
        "total_shots": sum(_int_like(row.get("shots_fired")) for row in combat_rows),
        "total_hits": sum(_int_like(row.get("hits_landed")) for row in combat_rows),
        "weapon_performance": weapons,
    }


def _build_budget_summary(state: LockstepState) -> dict[str, Any]:
    decisions = list(state.get("decision_history") or [])
    if not decisions:
        return {
            "decisions_made": 0, "avg_ticks_per_decision": 0, "estimated_decisions_remaining": 0,
        }
    first = decisions[0]
    last = decisions[-1]
    ticks_used = max(0, last.get("tick_after", 0) - first.get("tick_before", 0))
    total_ticks = last.get("total_budget", 500)
    remaining = max(0, total_ticks - last.get("tick_after", 0))
    avg = round(ticks_used / max(len(decisions), 1), 1)
    est_remaining = max(0, round(remaining / max(avg, 1))) if avg > 0 else 0
    return {
        "total_ticks": total_ticks,
        "ticks_used": last.get("tick_after", 0),
        "ticks_remaining": remaining,
        "decisions_made": len(decisions),
        "avg_ticks_per_decision": avg,
        "estimated_decisions_remaining": est_remaining,
    }


def _record_decision_in_history(
    lockstep_state: LockstepState,
    seq: int,
    tick_before: int,
    tick_after: int,
    tool: str,
    stop_reason: str | None,
    params: dict[str, Any],
    reasoning: str | None,
    guard_modified: bool,
    llm_duration_ms: float,
    mcp_duration_ms: float,
    total_budget: int,
    *,
    action_summary: dict[str, Any] | None = None,
    state_before: dict[str, Any] | None = None,
    state_after: dict[str, Any] | None = None,
    decision_source: str = "gemini",
    observed_issue: Any = None,
) -> None:
    action_summary = action_summary or {}
    result = "success"
    if stop_reason in ("stuck", "arrival_blocked", "target_not_visible"):
        result = "blocked"
    elif stop_reason in ("out_of_ammo", "no_usable_weapon", "no_target", "weapon_switch_failed"):
        result = "failed"
    elif stop_reason in ("max_tics",):
        result = "timeout"

    entry = {
        "seq": seq,
        "tick_before": tick_before,
        "tick_after": tick_after,
        "tool": tool,
        "stop_reason": stop_reason or "unknown",
        "result": result,
        "params": _compact_params(params),
        "key_findings": _extract_key_finding(tool, stop_reason, params),
        "reasoning": (reasoning or "")[:120],
        "decision_source": decision_source,
        "validation_rejection": action_summary.get("validation_error"),
        "target": {
            key: action_summary.get(key)
            for key in ("target_name", "target_type", "target_distance")
            if action_summary.get(key) is not None
        },
        "movement": {
            key: action_summary.get(key)
            for key in ("distance_moved", "distance_remaining", "direction_changes")
            if action_summary.get(key) is not None
        },
        "collection": {
            key: action_summary.get(key)
            for key in ("collected", "items_seen")
            if action_summary.get(key) is not None
        },
        "combat": {
            key: action_summary.get(key)
            for key in ("weapon_used", "shots_fired", "hits_landed", "kills", "ammo_spent")
            if action_summary.get(key) is not None
        },
        "state_delta": _state_delta(state_before, state_after),
        "final_position": _position_from_state(state_after),
        "total_budget": total_budget,
        "llm_ms": round(llm_duration_ms, 1),
        "mcp_ms": round(mcp_duration_ms, 1),
    }
    if observed_issue is not None:
        entry["observed_issue"] = _summary(observed_issue)[:180]
    history = list(lockstep_state.get("decision_history") or [])
    history.append(entry)
    lockstep_state["decision_history"] = history


def _compact_params(params: dict) -> dict[str, Any]:
    if "actions" in params:
        return {"actions": params["actions"]}
    out = {}
    for key in ("object_id", "max_tics", "tics", "shots", "weapon_slot", "direction", "use", "backpedal"):
        if key in params:
            out[key] = params[key]
    return out


def _position_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    variables = normalize_variables(state)
    return {
        "x": round(float(variables.get("x") or 0), 1),
        "y": round(float(variables.get("y") or 0), 1),
        "angle": round(float(variables.get("angle") or 0), 1),
    }


def _state_delta(
    state_before: dict[str, Any] | None,
    state_after: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(state_before, dict) or not isinstance(state_after, dict):
        return {}
    before = normalize_variables(state_before)
    after = normalize_variables(state_after)
    delta: dict[str, Any] = {}
    for key in ("health", "armor", "ammo_total", "kill_count", "item_count", "secret_count"):
        change = _bounded_float(after.get(key), 0.0) - _bounded_float(before.get(key), 0.0)
        if change:
            delta[key] = round(change, 1)
    return delta


def _extract_key_finding(tool: str, stop_reason: str | None, params: dict) -> str:
    if stop_reason == "item_found":
        return f"found item"
    if stop_reason == "enemy_spotted":
        return f"spotted enemy"
    if stop_reason == "arrived":
        obj = params.get("object_id")
        return f"reached object {obj}" if obj else "arrived"
    if stop_reason == "target_killed":
        obj = params.get("object_id")
        return f"killed target {obj}" if obj else "got kill"
    if stop_reason == "no_target":
        return "no target found"
    if stop_reason == "stuck":
        return "stuck - no movement"
    if stop_reason == "max_tics":
        return "timed out"
    if tool == "explore" and stop_reason == "max_tics":
        return "explored nothing"
    if tool == "take_action" and stop_reason == "tics_complete":
        return "probe completed"
    if stop_reason == "target_not_visible":
        return "target not visible"
    if tool == "retreat":
        return "retreated"
    return stop_reason or tool


def _record_event_in_history(
    lockstep_state: LockstepState,
    tick: int,
    event_type: str,
    x: float,
    y: float,
    detail: str = "",
) -> None:
    normalized = _normalize_event_type(event_type)
    entry = {
        "tick": tick,
        "type": normalized,
        "detail": detail[:120],
        "pos": {"x": round(x, 1), "y": round(y, 1)},
    }
    events = list(lockstep_state.get("run_events") or [])
    events.append(entry)
    lockstep_state["run_events"] = events[-100:]


def _normalize_event_type(event_type: str) -> str:
    lower = event_type.lower()
    if lower in ("kill", "target_killed"):
        return "enemy_kill"
    if lower in ("death", "player_died"):
        return "death"
    if lower in ("item_found", "pickup"):
        return "item_collect"
    if lower in ("stuck",):
        return "stuck"
    if lower in ("map_exit", "level_completed", "episode_finished"):
        return "map_event"
    if lower in ("damage_taken",):
        return "damage"
    if lower in ("key_found",):
        return "key_found"
    if lower in ("secret_found",):
        return "secret_found"
    if lower in ("ammo_starvation", "health_deficit", "resource_recovery"):
        return "resource"
    return "movement"


def _record_position_in_trail(
    lockstep_state: LockstepState,
    tick: int,
    x: float,
    y: float,
    angle: int,
) -> None:
    trail = list(lockstep_state.get("position_trail") or [])
    trail.append({"tick": tick, "x": round(x, 1), "y": round(y, 1), "angle": angle})
    lockstep_state["position_trail"] = trail[-60:]


def _update_combat_log(
    lockstep_state: LockstepState,
    object_id: int | None,
    weapon: str,
    shots: int,
    hits: int,
    killed: bool,
    distance: float,
    damage_dealt: float = 0,
) -> None:
    if object_id is None:
        return
    attempts = dict(lockstep_state.get("combat_attempts") or {})
    key = str(object_id)
    existing = attempts.get(key, {"id": object_id, "name": "unknown", "weapon": weapon, "shots": 0, "hits": 0, "killed": False, "distance": distance, "damage_dealt": 0})
    existing["shots"] += shots
    existing["hits"] += hits
    existing["damage_dealt"] += damage_dealt
    if killed:
        existing["killed"] = True
    existing["distance"] = distance
    existing["weapon"] = weapon
    attempts[key] = existing
    lockstep_state["combat_attempts"] = attempts


def _record_checkpoint(
    lockstep_state: LockstepState,
    tick: int,
    x: float,
    y: float,
    event: str,
) -> None:
    checkpoints = list(lockstep_state.get("checkpoints") or [])
    checkpoints.append({"tick": tick, "event": event[:80], "pos": {"x": round(x, 1), "y": round(y, 1)}})
    lockstep_state["checkpoints"] = checkpoints[-15:]


def _update_objective_history(
    lockstep_state: LockstepState,
    reasoning: str | None,
) -> None:
    if not reasoning:
        return
    lower = reasoning.lower()
    objective = "unknown"
    if any(kw in lower for kw in ("explor", "search", "find", "sweep")):
        objective = "exploring"
    elif any(kw in lower for kw in ("kill", "shoot", "attack", "fight", "combat")):
        objective = "combat"
    elif any(kw in lower for kw in ("collect", "pickup", "grab", "get")):
        objective = "collecting"
    elif any(kw in lower for kw in ("retreat", "back", "flee", "dodge")):
        objective = "retreating"
    elif any(kw in lower for kw in ("use", "door", "switch", "open")):
        objective = "interacting"
    elif any(kw in lower for kw in ("stuck", "softlock", "blocked", "loop")):
        objective = "diagnosing_blockage"
    elif any(kw in lower for kw in ("report", "defect", "issue")):
        objective = "reporting_defect"
    history = list(lockstep_state.get("objective_history") or [])
    history.append(objective)
    lockstep_state["objective_history"] = history[-10:]


def _initial_lockstep_state() -> LockstepState:
    return {
        "last_signature": None,
        "no_progress_polls": 0,
        "last_tick": -1,
        "invisible_target_failures": {},
        "wasted_combat_count": 0,
        "consecutive_explore_max_tics": 0,
        "low_value_explore_total": 0,
        "low_value_explore_cumulative": 0,
        "completed_object_ids": {},
        "failed_object_ids": {},
        "out_of_ammo_targets": {},
        "weapon_resource_failures": {},
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
        "hypothesis_repetition_counts": {},
        "counter_hypothesis_added": False,
        "use_attempt_count": 0,
        "total_decision_count": 0,
        "decision_history": [],
        "run_events": [],
        "position_trail": [],
        "combat_attempts": {},
        "checkpoints": [],
        "defects_found": [],
        "objective_history": [],
        "position_stuck_counter": 0,
        "last_position": None,
        "decision_diversity_counter": 0,
        "consecutive_get_state": 0,
    }


def _track_visited_cell(state: dict[str, Any], lockstep_state: LockstepState) -> None:
    variables = normalize_variables(state)
    x = float(variables.get("x") or 0)
    y = float(variables.get("y") or 0)
    if x == 0 and y == 0:
        raw_vars = state.get("game_variables") or state.get("variables") or {}
        x = float(raw_vars.get("POSITION_X", raw_vars.get("position_x", raw_vars.get("x", 0))) or 0)
        y = float(raw_vars.get("POSITION_Y", raw_vars.get("position_y", raw_vars.get("y", 0))) or 0)
    cell_key = f"{round(x / CELL_SIZE)},{round(y / CELL_SIZE)}"
    visited = lockstep_state.get("visited_cells") or {}
    was_new = cell_key not in visited
    visited[cell_key] = visited.get(cell_key, 0) + 1
    lockstep_state["visited_cells"] = dict(list(visited.items())[-200:])
    if was_new:
        lockstep_state["_new_cells_current"] = lockstep_state.get("_new_cells_current", 0) + 1


def _tail_dict(value: Any, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return dict(list(value.items())[-limit:])


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


HYPOTHESIS_REPETITION_LIMIT = 3

_COUNTER_HYPOTHESIS_TEXT = (
    "Suspected false positive: agent repeated the same category of issue 3+ times without new evidence. "
    "Continue exploring wider area instead of fixating on previous hypothesis."
)


def _hypothesis_category_key(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in ("softlock", "progression", "unreachable", "stuck")):
        return "PROGRESSION"
    if any(kw in lower for kw in ("blocked", "collision", "gap", "sealed", "non-interactive")):
        return "GEOMETRY"
    if any(kw in lower for kw in ("ammo", "starvation", "health", "resource", "weapon")):
        return "RESOURCE_BALANCE"
    if any(kw in lower for kw in ("encounter", "combat", "monster", "hitscanner")):
        return "ENCOUNTER_DESIGN"
    return "OTHER"


def _merge_hypotheses(
    lockstep_state: LockstepState,
    decision: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> None:
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

    visited_count = len(lockstep_state.get("visited_cells") or {})
    kills = 0
    has_runtime_state = isinstance(state, dict)
    if has_runtime_state:
        variables = state.get("game_variables") if isinstance(state.get("game_variables"), dict) else state
        kills = int(variables.get("KILLS") or 0)

    repetition_counts = dict(lockstep_state.get("hypothesis_repetition_counts") or {})
    existing = [str(item) for item in lockstep_state.get("hypotheses") or [] if item]
    seen = {item.lower() for item in existing}
    counter_added = bool(lockstep_state.get("counter_hypothesis_added"))

    for candidate in candidates:
        text = " ".join(candidate.split())[:180]
        if not text:
            continue

        category = _hypothesis_category_key(text)

        if has_runtime_state and category == "PROGRESSION" and kills < 2 and visited_count < 5:
            continue

        repetition_counts[category] = repetition_counts.get(category, 0) + 1

        if text.lower() in seen:
            continue

        if repetition_counts[category] >= HYPOTHESIS_REPETITION_LIMIT:
            if not counter_added:
                existing.append(_COUNTER_HYPOTHESIS_TEXT)
                counter_added = True
            continue

        existing.append(text)
        seen.add(text.lower())

    lockstep_state["hypotheses"] = existing[-12:]
    lockstep_state["hypothesis_repetition_counts"] = repetition_counts
    lockstep_state["counter_hypothesis_added"] = counter_added


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
        parts = key.split(",")
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


def _factual_game_tic(state: dict[str, Any], lockstep_state: dict[str, Any]) -> int:
    previous = lockstep_state.get("last_tick")
    last_tick = int(previous) if previous is not None else -1
    variables = state.get("game_variables") if isinstance(state.get("game_variables"), dict) else {}
    raw_tick = state.get("tic", variables.get("TIC"))
    factual_tick = _bounded_int(raw_tick, default=max(last_tick, 0), lower=0)
    lockstep_state["last_tick"] = max(last_tick, factual_tick)
    return factual_tick


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
    elif tool == "select_weapon":
        params["weapon_slot"] = _bounded_int(params.get("weapon_slot"), default=2, lower=0, upper=9)
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=20, lower=1, upper=20)
    if tool in COMPOUND_TELEMETRY_TOOLS and "telemetry_stride" in params:
        params["telemetry_stride"] = _bounded_int(params.get("telemetry_stride"), default=1, lower=1, upper=10)
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
