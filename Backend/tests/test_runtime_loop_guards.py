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
    _is_wasted_combat_decision,
    _lockstep_should_stop_as_stuck,
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
