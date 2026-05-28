# Experimental Director mode — not the active production path
# The product uses lockstep (agent_run_task in run_loop.py).
# This file exists because the MCP executor supports async director-style
# play, and tests cover the normalization/recovery logic.

from __future__ import annotations

import contextlib
from typing import Any

from app.models import StaticAnalysisResult, TestRun
from app.services.analysis_service import selected_skill_spawn_summary
from app.services.collector_service import normalize_variables
from app.services.mcp_client_service import McpDoomClient
from app.services.run_constants import DIRECTOR_STUCK_POLL_THRESHOLD, DIRECTOR_STUCK_RECOVERY_LIMIT
from app.services.run_utils import _bounded_float, _bounded_int, _compact_mcp_output, _json_safe


def _initial_strategy_decision(analysis: StaticAnalysisResult, run: TestRun) -> dict[str, Any]:
    skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
    spawned_enemies = int(skill_summary.get("thing_count_enemies") or 0)
    return {
        "reasoning_summary": (
            "Initializing async gameplay strategy from selected-difficulty static analysis."
        ),
        "mcp_tool": "set_strategy",
        "mcp_params": {
            "aggression": 0.8 if spawned_enemies else 0.35,
            "health_retreat_threshold": 25,
            "health_collect_threshold": 65,
            "ammo_switch_threshold": 3,
            "engage_range": 1400 if spawned_enemies else 700,
            "collect_range": 1100,
            "prefer_cover": bool(spawned_enemies),
        },
    }


def _initial_objective_decision(analysis: StaticAnalysisResult, run: TestRun) -> dict[str, Any]:
    skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
    spawned_enemies = int(skill_summary.get("thing_count_enemies") or 0)
    return {
        "reasoning_summary": (
            "Starting the async executor with broad exploration; combat and pickup handling continue autonomously."
        ),
        "mcp_tool": "set_objective",
        "mcp_params": {
            "objective_type": "explore",
            "priority": 40 if spawned_enemies else 25,
            "timeout_tics": 420,
            "replace": True,
        },
    }


async def _execute_director_tool(
    mcp: McpDoomClient,
    decision: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    tool = decision.get("mcp_tool") or "get_situation_report"
    params = dict(decision.get("mcp_params") or {})
    if tool == "set_objective":
        params = _normalize_director_objective_params(params)
        response = await mcp.set_objective(**params)
        stop_reason = "objective_set"
    elif tool == "set_strategy":
        params = _normalize_director_strategy_params(params)
        if not params:
            tool = "get_situation_report"
            response = await mcp.call_tool("get_situation_report", {})
            stop_reason = "strategy_unchanged"
        else:
            response = await mcp.set_strategy(**params)
            stop_reason = "strategy_updated"
    else:
        tool = "get_situation_report"
        params = {}
        response = await mcp.call_tool("get_situation_report", {})
        stop_reason = "situation_report"

    output = _compact_mcp_output(response)
    if not isinstance(output, dict):
        output = {"result": output}
    output.setdefault(
        "action_summary",
        {
            "stop_reason": stop_reason,
            "director_tool": tool,
            "objective_type": params.get("objective_type"),
            "executor_control": True,
        },
    )
    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    return response, {
        "service": "mcp-doom",
        "tool": tool,
        "input": _json_safe(params),
        "output": _json_safe(output),
    }


def _normalize_director_objective_params(params: dict[str, Any]) -> dict[str, Any]:
    valid = {"explore", "kill", "move_to_pos", "move_to_obj", "collect", "use_object", "retreat", "hold_position"}
    objective_type = str(params.get("objective_type") or params.get("type") or "explore")
    if objective_type not in valid:
        objective_type = "explore"
    objective_params = params.get("params") if isinstance(params.get("params"), dict) else {}
    if "object_id" in params and "object_id" not in objective_params:
        with contextlib.suppress(TypeError, ValueError):
            objective_params["object_id"] = int(params["object_id"])
    for coord in ("x", "y"):
        if coord in params and coord not in objective_params:
            with contextlib.suppress(TypeError, ValueError):
                objective_params[coord] = float(params[coord])
    return {
        "objective_type": objective_type,
        "params": objective_params,
        "priority": _bounded_int(params.get("priority"), default=25, lower=0, upper=200),
        "timeout_tics": _bounded_int(params.get("timeout_tics"), default=350, lower=0, upper=2000),
        "replace": bool(params.get("replace", False)),
    }


def _normalize_director_strategy_params(params: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "aggression",
        "health_retreat_threshold",
        "health_collect_threshold",
        "ammo_switch_threshold",
        "engage_range",
        "collect_range",
        "prefer_cover",
    }
    normalized = {key: params[key] for key in allowed if key in params}
    if "aggression" in normalized:
        normalized["aggression"] = max(0.0, min(1.0, _bounded_float(normalized["aggression"], 0.5)))
    for key in ("health_retreat_threshold", "health_collect_threshold", "ammo_switch_threshold"):
        if key in normalized:
            normalized[key] = _bounded_int(normalized[key], default=0, lower=0, upper=200)
    for key in ("engage_range", "collect_range"):
        if key in normalized:
            normalized[key] = max(1.0, min(5000.0, _bounded_float(normalized[key], 1000.0)))
    if "prefer_cover" in normalized:
        normalized["prefer_cover"] = bool(normalized["prefer_cover"])
    return normalized


def _apply_director_recovery(
    decision: dict[str, Any],
    situation: dict[str, Any],
    director_state: dict[str, Any],
) -> dict[str, Any]:
    signature = _director_progress_signature(situation)
    if signature != director_state.get("last_signature"):
        director_state["last_signature"] = signature
        director_state["no_progress_polls"] = 0
        director_state["should_stop_stuck"] = False
    else:
        director_state["no_progress_polls"] = int(director_state.get("no_progress_polls") or 0) + 1

    progress = situation.get("executor_progress") if isinstance(situation.get("executor_progress"), dict) else {}
    stuck_recovery_count = int(progress.get("stuck_recovery_count") or 0)
    if stuck_recovery_count > int(director_state.get("last_stuck_recovery_count") or 0):
        director_state["no_progress_polls"] = max(
            int(director_state.get("no_progress_polls") or 0),
            DIRECTOR_STUCK_POLL_THRESHOLD,
        )
    director_state["last_stuck_recovery_count"] = stuck_recovery_count

    if int(director_state.get("no_progress_polls") or 0) >= DIRECTOR_STUCK_POLL_THRESHOLD:
        recovery_count = int(director_state.get("recovery_count") or 0) + 1
        director_state["recovery_count"] = recovery_count
        director_state["no_progress_polls"] = 0
        if recovery_count >= DIRECTOR_STUCK_RECOVERY_LIMIT:
            director_state["should_stop_stuck"] = True
        objective = "retreat" if recovery_count % 2 else "explore"
        return {
            "reasoning_summary": (
                f"Coverage progress stalled for repeated director polls; replacing the queue with {objective} recovery."
            ),
            "mcp_tool": "set_objective",
            "mcp_params": {
                "objective_type": objective,
                "priority": 120,
                "timeout_tics": 210,
                "replace": True,
            },
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    objectives = situation.get("objectives") if isinstance(situation.get("objectives"), list) else []
    if not objectives and decision.get("mcp_tool") == "get_situation_report":
        return {
            "reasoning_summary": "Executor had no queued objective, so directing exploration coverage.",
            "mcp_tool": "set_objective",
            "mcp_params": {
                "objective_type": "explore",
                "priority": 45,
                "timeout_tics": 350,
                "replace": False,
            },
            "observed_issue": None,
        }
    return decision


def _director_progress_signature(situation: dict[str, Any]) -> tuple[Any, ...]:
    variables = normalize_variables(situation)
    exploration = situation.get("exploration") if isinstance(situation.get("exploration"), dict) else {}
    x = float(variables.get("x") or 0)
    y = float(variables.get("y") or 0)
    return (
        round(x / 128),
        round(y / 128),
        int(variables.get("kill_count") or 0),
        int(variables.get("item_count") or 0),
        int(variables.get("secret_count") or 0),
        int(exploration.get("cells_explored") or 0),
        len(exploration.get("keys_found") or []),
    )


def _director_should_stop_as_stuck(director_state: dict[str, Any]) -> bool:
    return bool(director_state.get("should_stop_stuck"))


def _unique_director_tick(situation: dict[str, Any], director_state: dict[str, Any]) -> int:
    previous = director_state.get("last_tick")
    last_tick = int(previous) if previous is not None else -1
    raw_tick = _bounded_int(situation.get("tic"), default=last_tick + 1, lower=0)
    tick = max(raw_tick, last_tick + 1)
    director_state["last_tick"] = tick
    return tick
