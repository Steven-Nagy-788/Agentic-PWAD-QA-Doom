from __future__ import annotations

from unittest.mock import patch

from app.core.types import LockstepState
from app.services.run_tracking import (
    _lockstep_quality_flags,
    _lockstep_progress_metrics,
    _update_no_progress_stall,
)


def _base_state(**overrides: object) -> LockstepState:
    state: LockstepState = {}
    state.update(overrides)  # type: ignore[arg-type]
    return state


def _game_state(x: float = 0, y: float = 0, kill: int = 0, item: int = 0, secret: int = 0) -> dict:
    return {
        "game_variables": {
            "POSITION_X": x,
            "POSITION_Y": y,
            "KILLCOUNT": kill,
            "ITEMCOUNT": item,
            "SECRETCOUNT": secret,
        }
    }


# ── _lockstep_progress_metrics ──────────────────────────────────────────────


def test_lockstep_progress_metrics_empty_state() -> None:
    state = _base_state()
    metrics = _lockstep_progress_metrics(state)
    assert metrics["progress_score"] == 0
    assert metrics["meaningful_progress_events"] == 0
    assert metrics["completed_object_count"] == 0
    assert metrics["failed_object_count"] == 0
    assert metrics["weapon_resource_failure_count"] == 0
    assert metrics["blocked_decision_count"] == 0
    assert metrics["low_value_explore_count"] == 0
    assert metrics["visited_cells_count"] == 0
    assert metrics["total_map_cells_estimate"] is None
    assert metrics["coverage_percent"] is None
    assert metrics["new_cells_last_5_decisions"] == 0
    assert metrics["consecutive_no_progress_decisions"] == 0


def test_lockstep_progress_metrics_with_data() -> None:
    state = _base_state(
        visited_cells={"0,0": 1, "1,0": 1, "2,0": 1, "0,1": 1, "1,1": 1},
        progress_score=15,
        meaningful_progress_events=4,
        completed_object_ids={"key1": {}, "key2": {}},
        failed_object_ids={"wall1": 2, "door1": 1},
        weapon_resource_failures={"out_of_ammo:weapon=pistol": 3},
        blocked_decision_count=7,
        low_value_explore_cumulative=5,
        total_map_cells_estimate=100,
        new_cells_last_5_decisions=2,
        no_progress_polls=1,
    )
    metrics = _lockstep_progress_metrics(state)
    assert metrics["progress_score"] == 15
    assert metrics["meaningful_progress_events"] == 4
    assert metrics["completed_object_count"] == 2
    assert metrics["failed_object_count"] == 2
    assert metrics["weapon_resource_failure_count"] == 1
    assert metrics["blocked_decision_count"] == 7
    assert metrics["low_value_explore_count"] == 5
    assert metrics["visited_cells_count"] == 5
    assert metrics["total_map_cells_estimate"] == 100
    assert metrics["new_cells_last_5_decisions"] == 2
    assert metrics["consecutive_no_progress_decisions"] == 1


def test_lockstep_progress_metrics_coverage_percent() -> None:
    visited = {f"{i},{j}": 1 for i in range(10) for j in range(5)}
    state = _base_state(
        visited_cells=visited,
        total_map_cells_estimate=200,
    )
    metrics = _lockstep_progress_metrics(state)
    assert metrics["coverage_percent"] == 25.0


def test_lockstep_progress_metrics_no_total_cells() -> None:
    state = _base_state(
        visited_cells={"0,0": 1},
        total_map_cells_estimate=None,
    )
    metrics = _lockstep_progress_metrics(state)
    assert metrics["coverage_percent"] is None


# ── _lockstep_quality_flags ─────────────────────────────────────────────────


def test_lockstep_quality_flags_ok() -> None:
    state = _base_state()
    meta: dict = {}
    result = _lockstep_quality_flags(state, meta)
    assert result["quality_status"] == "ok"
    assert result["warnings"] == []


def test_lockstep_quality_flags_warning_from_state() -> None:
    state = _base_state(quality_warnings=["something went wrong"])
    result = _lockstep_quality_flags(state, {})
    assert result["quality_status"] == "warning"
    assert "something went wrong" in result["warnings"]


def test_lockstep_quality_flags_warning_from_recording() -> None:
    state = _base_state()
    meta = {"validation_warnings": ["recording issue"]}
    result = _lockstep_quality_flags(state, meta)
    assert result["quality_status"] == "warning"
    assert "recording issue" in result["warnings"]


def test_lockstep_quality_flags_limits_warnings_to_30() -> None:
    warnings = [f"warn-{i}" for i in range(50)]
    state = _base_state(quality_warnings=warnings)
    result = _lockstep_quality_flags(state, {})
    assert len(result["warnings"]) == 30
    assert result["warnings"][0] == "warn-20"
    assert result["warnings"][-1] == "warn-49"


def test_lockstep_quality_flags_records_ids() -> None:
    state = _base_state(
        completed_object_ids={"obj_a": {"target_name": "key"}},
        failed_object_ids={"obj_b": 2},
        weapon_resource_failures={"out_of_ammo:weapon=pistol": 1},
    )
    result = _lockstep_quality_flags(state, {})
    assert "obj_a" in result["completed_object_ids"]
    assert "obj_b" in result["failed_object_ids"]
    assert "out_of_ammo:weapon=pistol" in result["weapon_resource_failures"]


# ── _update_no_progress_stall ───────────────────────────────────────────────


def test_update_no_progress_stall_increments() -> None:
    state: LockstepState = {}
    with patch("app.services.run_tracking.get_settings") as settings:
        settings.return_value.no_progress_decision_abort_threshold = 10
        _update_no_progress_stall(_game_state(x=0, y=0), state)
        _update_no_progress_stall(_game_state(x=0, y=0), state)
        _update_no_progress_stall(_game_state(x=0, y=0), state)
    assert state["no_progress_polls"] == 2


def test_update_no_progress_stall_resets() -> None:
    state: LockstepState = {}
    with patch("app.services.run_tracking.get_settings") as settings:
        settings.return_value.no_progress_decision_abort_threshold = 10
        _update_no_progress_stall(_game_state(x=0, y=0), state)
        _update_no_progress_stall(_game_state(x=0, y=0), state)
        _update_no_progress_stall(_game_state(x=300, y=300), state)
    assert state["no_progress_polls"] == 0


def test_update_no_progress_stall_triggers_stop() -> None:
    state: LockstepState = {}
    with patch("app.services.run_tracking.get_settings") as settings:
        settings.return_value.no_progress_decision_abort_threshold = 2
        _update_no_progress_stall(_game_state(x=0, y=0), state)
        _update_no_progress_stall(_game_state(x=0, y=0), state)
        _update_no_progress_stall(_game_state(x=0, y=0), state)
    assert state.get("should_stop_stuck") is True
    assert state.get("stop_outcome") == "inconclusive_agent_stall"
