from __future__ import annotations

from uuid import uuid4

from app.models import Defect
from app.repositories.defect_repository import DefectRepository
from app.services.collector_service import STUCK_DECISION_THRESHOLD, CollectorService
from app.services.run_service import (
    _apply_lockstep_recovery,
    _apply_director_recovery,
    _combat_target_is_visible,
    _director_should_stop_as_stuck,
    _guard_lockstep_decision,
    _normalize_director_objective_params,
    _normalize_mcp_params,
    _is_wasted_combat_decision,
    _lockstep_progress_metrics,
    _lockstep_quality_flags,
    _lockstep_should_stop_as_stuck,
    _update_lockstep_after_action,
)


def _variables(**overrides):
    data = {
        "x": 10,
        "y": 20,
        "angle": 90,
        "health": 100,
        "armor": 0,
        "ammo_bullets": 10,
        "ammo_shells": 0,
        "ammo_rockets": 0,
        "ammo_cells": 0,
        "ammo_total": 10,
        "kill_count": 0,
        "item_count": 0,
        "secret_count": 0,
        "weapon_selected": 2,
        "level_completed": False,
        "map_exit": False,
    }
    data.update(overrides)
    return data


def test_stuck_detection_triggers_after_short_decision_streak() -> None:
    collector = CollectorService(None)  # type: ignore[arg-type]
    collector._previous = _variables()

    event_type = "normal"
    for _ in range(STUCK_DECISION_THRESHOLD):
        event_type = collector.detect_event(_variables())
        collector._previous = _variables()

    assert event_type == "stuck"


def test_stuck_detection_resets_when_resources_change() -> None:
    collector = CollectorService(None)  # type: ignore[arg-type]
    collector._previous = _variables()

    event_type = collector.detect_event(_variables(ammo_bullets=9, ammo_total=9))

    assert event_type == "normal"
    assert collector._stuck_count == 0


def test_combat_guard_requires_visible_monster_target() -> None:
    state = {
        "objects": [
            {"id": 1, "type": "monster", "is_visible": False},
            {"id": 2, "type": "monster", "is_visible": True},
            {"id": 3, "type": "item", "is_visible": True},
        ]
    }

    assert _combat_target_is_visible(state, 2) is True
    assert _combat_target_is_visible(state, 1) is False
    assert _combat_target_is_visible(state, 3) is False
    assert _combat_target_is_visible(state, 999) is False


def test_repeated_missed_combat_counts_as_wasted_decision() -> None:
    decision = {"mcp_tool": "aim_and_shoot"}
    mcp_call = {
        "output": {
            "action_summary": {
                "stop_reason": "shots_complete",
                "shots_fired": 3,
                "hits_landed": 0,
                "kills": 0,
            }
        }
    }

    assert _is_wasted_combat_decision(decision, mcp_call) is True


def test_agent_observed_defects_are_deduped_for_api_and_reports() -> None:
    run_id = uuid4()
    first = Defect(
        run_id=run_id,
        severity=2,
        priority=2,
        defect_type="agent_observed",
        title="Agent-observed issue",
        description="same issue wording one",
        detected_at_tick=10,
    )
    duplicate = Defect(
        run_id=run_id,
        severity=2,
        priority=2,
        defect_type="agent_observed",
        title="Agent-observed issue",
        description="same issue wording two",
        detected_at_tick=11,
    )
    static = Defect(
        run_id=run_id,
        severity=1,
        priority=1,
        defect_type="softlock_navigation",
        title="Potential navigation softlock",
        description="stuck",
        detected_at_tick=11,
    )

    assert DefectRepository.dedupe_defects([first, duplicate, static]) == [first, static]


def test_defect_fingerprint_is_stable_for_agent_observed_issue() -> None:
    defect = Defect(
        run_id=uuid4(),
        severity=2,
        priority=2,
        defect_type="agent_observed_geometry",
        title="Automated playthrough observed geometry issue",
        description="same geometry issue",
        detected_at_tick=10,
    )

    DefectRepository._ensure_fingerprint(defect)

    assert defect.fingerprint == "agent_observed_geometry:automated_playthrough_observed_geometry_issue"


def test_director_recovery_replaces_objective_after_no_progress() -> None:
    situation = {
        "tic": 100,
        "game_variables": {"POSITION_X": 0, "POSITION_Y": 0, "KILLCOUNT": 0, "ITEMCOUNT": 0, "SECRETCOUNT": 0},
        "exploration": {"cells_explored": 1},
        "executor_progress": {"stuck_recovery_count": 0},
        "objectives": [{"type": "explore"}],
    }
    state = {"last_signature": None, "no_progress_polls": 0, "recovery_count": 0, "last_stuck_recovery_count": 0}
    decision = {"mcp_tool": "get_situation_report", "mcp_params": {}}

    for _ in range(6):
        decision = _apply_director_recovery(decision, situation, state)

    assert decision["mcp_tool"] == "set_objective"
    assert decision["mcp_params"]["replace"] is True
    assert decision["event_type_override"] == "stuck"


def test_director_stops_after_recovery_limit() -> None:
    situation = {
        "game_variables": {"POSITION_X": 0, "POSITION_Y": 0, "KILLCOUNT": 0, "ITEMCOUNT": 0, "SECRETCOUNT": 0},
        "exploration": {"cells_explored": 1},
        "executor_progress": {"stuck_recovery_count": 0},
        "objectives": [{"type": "explore"}],
    }
    state = {"last_signature": None, "no_progress_polls": 0, "recovery_count": 3, "last_stuck_recovery_count": 0}

    _apply_director_recovery({"mcp_tool": "get_situation_report", "mcp_params": {}}, situation, state)
    for _ in range(5):
        _apply_director_recovery({"mcp_tool": "get_situation_report", "mcp_params": {}}, situation, state)

    assert _director_should_stop_as_stuck(state) is True


def test_director_objective_params_are_bounded_and_replaceable() -> None:
    params = _normalize_director_objective_params(
        {"type": "move_to_obj", "object_id": "42", "priority": 999, "timeout_tics": 99999, "replace": True}
    )

    assert params == {
        "objective_type": "move_to_obj",
        "params": {"object_id": 42},
        "priority": 200,
        "timeout_tics": 2000,
        "replace": True,
    }


def test_lockstep_guard_rejects_non_visible_combat_target() -> None:
    decision = {"mcp_tool": "aim_and_shoot", "mcp_params": {"object_id": 1}}
    state = {"objects": [{"id": 1, "type": "monster", "is_visible": False}]}

    guarded = _guard_lockstep_decision(decision, state, {"invisible_target_failures": {}})

    assert guarded["mcp_tool"] == "explore"
    assert "not a visible monster" in guarded["reasoning_summary"]


def test_lockstep_guard_blocks_retargeting_completed_pickup() -> None:
    decision = {"mcp_tool": "move_to", "mcp_params": {"object_id": 10}}
    state = {
        "objects": [
            {"id": 10, "type": "item", "name": "Stimpack", "is_visible": True, "distance": 10},
            {"id": 11, "type": "ammo", "name": "Clip", "is_visible": True, "distance": 30},
        ]
    }
    lockstep_state = {
        "completed_object_ids": {"10": {"target_name": "Stimpack", "stop_reason": "arrived"}},
        "failed_object_ids": {},
        "action_signature_counts": {},
    }

    guarded = _guard_lockstep_decision(decision, state, lockstep_state, {})

    assert guarded["mcp_tool"] == "move_to"
    assert guarded["mcp_params"]["object_id"] == 11
    assert "already reached or collected" in guarded["reasoning_summary"]


def test_lockstep_guard_blocks_repeated_out_of_ammo_combat() -> None:
    decision = {"mcp_tool": "aim_and_shoot", "mcp_params": {"object_id": 7}}
    state = {
        "objects": [
            {"id": 7, "type": "monster", "name": "FormerHuman", "is_visible": True, "distance": 160},
            {"id": 8, "type": "ammo", "name": "Clip", "is_visible": True, "distance": 96},
        ]
    }
    lockstep_state = {
        "out_of_ammo_targets": {"7": 1},
        "completed_object_ids": {},
        "failed_object_ids": {},
        "action_signature_counts": {},
    }

    guarded = _guard_lockstep_decision(decision, state, lockstep_state, {})

    assert guarded["mcp_tool"] == "move_to"
    assert guarded["mcp_params"]["object_id"] == 8
    assert "out_of_ammo" in guarded["reasoning_summary"]


def test_lockstep_guard_marks_strict_stop_after_repeated_blocked_decisions() -> None:
    decision = {"mcp_tool": "move_to", "mcp_params": {"object_id": 10}}
    state = {"objects": []}
    lockstep_state = {
        "completed_object_ids": {"10": {"target_name": "Stimpack"}},
        "failed_object_ids": {},
        "action_signature_counts": {},
        "blocked_decision_count": 5,
    }

    guarded = _guard_lockstep_decision(decision, state, lockstep_state, {})

    assert guarded["mcp_tool"] in {"take_action", "retreat"}
    assert _lockstep_should_stop_as_stuck(lockstep_state) is True


def test_lockstep_recovery_stops_after_bounded_retries() -> None:
    state = {
        "game_variables": {"POSITION_X": 0, "POSITION_Y": 0, "KILLCOUNT": 0, "ITEMCOUNT": 0, "SECRETCOUNT": 0},
        "objects": [],
    }
    navigation = {"cells_explored": 1, "keys_found": []}
    lockstep_state = {"last_signature": None, "no_progress_polls": 0, "recovery_count": 3}

    _apply_lockstep_recovery({"mcp_tool": "explore", "mcp_params": {}}, state, navigation, lockstep_state)
    for _ in range(5):
        _apply_lockstep_recovery({"mcp_tool": "explore", "mcp_params": {}}, state, navigation, lockstep_state)

    assert _lockstep_should_stop_as_stuck(lockstep_state) is True


def test_lockstep_overrides_repeated_low_value_explore_with_qa_probe() -> None:
    state = {
        "game_variables": {"POSITION_X": 0, "POSITION_Y": 0, "ANGLE": 0, "KILLCOUNT": 0, "ITEMCOUNT": 0, "SECRETCOUNT": 0},
        "objects": [],
    }
    navigation = {"cells_explored": 3, "keys_found": [], "suggested_direction": "north", "nearby_doors": []}
    lockstep_state = {"last_signature": None, "low_value_explore_total": 2, "qa_probe_count": 0}

    decision = _apply_lockstep_recovery(
        {"mcp_tool": "explore", "mcp_params": {"max_tics": 160}},
        state,
        navigation,
        lockstep_state,
    )

    assert decision["mcp_tool"] == "take_action"
    assert decision["mcp_params"]["actions"]["TURN_LEFT_RIGHT_DELTA"] == -45.0
    assert decision["event_type_override"] == "stuck"
    assert lockstep_state["qa_probe_count"] == 1


def test_low_value_explore_stops_run_after_bounded_attempts() -> None:
    lockstep_state = {"low_value_explore_total": 5, "consecutive_explore_max_tics": 0}
    mcp_call = {"tool": "explore", "output": {"action_summary": {"stop_reason": "max_tics"}}}

    _update_lockstep_after_action({"mcp_tool": "explore"}, mcp_call, lockstep_state)

    assert _lockstep_should_stop_as_stuck(lockstep_state) is True


def test_lockstep_progress_and_quality_flags_capture_guard_evidence() -> None:
    lockstep_state = {}
    _update_lockstep_after_action(
        {"mcp_tool": "move_to", "mcp_params": {"object_id": 4}},
        {
            "tool": "move_to",
            "input": {"object_id": 4},
            "output": {"action_summary": {"stop_reason": "arrived", "target_name": "Clip", "target_type": "ammo"}},
        },
        lockstep_state,
    )
    _update_lockstep_after_action(
        {"mcp_tool": "aim_and_shoot", "mcp_params": {"object_id": 9}},
        {
            "tool": "aim_and_shoot",
            "input": {"object_id": 9},
            "output": {"action_summary": {"stop_reason": "out_of_ammo"}},
        },
        lockstep_state,
    )

    metrics = _lockstep_progress_metrics(lockstep_state)
    flags = _lockstep_quality_flags(lockstep_state, {"quality_status": "ok", "validation_warnings": []})

    assert metrics["progress_score"] == 2
    assert metrics["completed_object_count"] == 1
    assert metrics["out_of_ammo_target_count"] == 1
    assert flags["quality_status"] == "warning"
    assert "4" in flags["completed_object_ids"]
    assert "9" in flags["out_of_ammo_targets"]


def test_lockstep_tool_params_are_bounded_for_trace_and_mcp_call() -> None:
    assert _normalize_mcp_params("explore", {"max_tics": 999})["max_tics"] == 80
    assert _normalize_mcp_params("retreat", {"tics": 999})["tics"] == 70
    take_action = _normalize_mcp_params(
        "take_action",
        {
            "actions": {
                "TURN_LEFT_RIGHT_DELTA": 120,
                "MOVE_FORWARD_BACKWARD_DELTA": 90,
                "USE": 2,
                "UNKNOWN": 1,
            },
            "tics": 99,
        },
    )

    assert take_action == {
        "actions": {"TURN_LEFT_RIGHT_DELTA": 45.0, "MOVE_FORWARD_BACKWARD_DELTA": 50.0, "USE": 1},
        "tics": 8,
    }
