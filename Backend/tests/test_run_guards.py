from __future__ import annotations

from app.services.run_guards import (
    _action_signature,
    _combat_target_is_visible,
    _is_stuck_decision,
    _is_wasted_combat_decision,
    _lockstep_stop_outcome,
    _nearest_available_pickup,
    _turn_delta_for_direction,
)


# ── _turn_delta_for_direction ────────────────────────────────────────────────


def test_turn_north_from_zero() -> None:
    assert _turn_delta_for_direction("north", 0.0) == -45.0


def test_turn_north_from_90() -> None:
    assert _turn_delta_for_direction("north", 90.0) == 0.0


def test_turn_south_from_zero() -> None:
    assert _turn_delta_for_direction("south", 0.0) == 45.0


def test_turn_west_from_zero() -> None:
    assert _turn_delta_for_direction("west", 0.0) == 45.0


def test_turn_east_from_zero() -> None:
    assert _turn_delta_for_direction("east", 0.0) == 0.0


def test_turn_unknown_direction_returns_zero() -> None:
    assert _turn_delta_for_direction("nowhere", 90.0) == 0.0


def test_turn_clamped_to_45_degrees() -> None:
    result = _turn_delta_for_direction("south", 180.0)
    assert -45.0 <= result <= 45.0


# ── _action_signature ────────────────────────────────────────────────────────


def test_action_signature_includes_tool_and_params() -> None:
    sig = _action_signature("move_to", {"object_id": 5, "max_tics": 80})
    assert "move_to" in sig
    assert "5" in sig


def test_action_signature_excludes_telemetry_keys() -> None:
    sig = _action_signature("explore", {"max_tics": 80, "capture_telemetry": True, "telemetry_stride": 3})
    assert "capture_telemetry" not in sig
    assert "telemetry_stride" not in sig


def test_action_signature_sorts_keys() -> None:
    sig1 = _action_signature("test", {"b": 2, "a": 1})
    sig2 = _action_signature("test", {"a": 1, "b": 2})
    assert sig1 == sig2


def test_action_signature_empty_params() -> None:
    sig = _action_signature("explore", {})
    assert sig == 'explore:{}'


# ── _nearest_available_pickup ────────────────────────────────────────────────


def test_pickup_returns_nearest_visible() -> None:
    state = {
        "objects": [
            {"id": 1, "type": "item", "is_visible": True, "distance": 100, "name": "Stimpack"},
            {"id": 2, "type": "ammo", "is_visible": True, "distance": 50, "name": "Clip"},
            {"id": 3, "type": "monster", "is_visible": True, "distance": 200},
        ]
    }
    pickup = _nearest_available_pickup(state, {})
    assert pickup is not None
    assert pickup["id"] == 2


def test_pickup_skips_completed_and_failed() -> None:
    state = {
        "objects": [
            {"id": 1, "type": "item", "is_visible": True, "distance": 100},
            {"id": 2, "type": "ammo", "is_visible": True, "distance": 50},
        ]
    }
    lockstep = {"completed_object_ids": {"1": {}}, "failed_object_ids": {"2": 2}}
    pickup = _nearest_available_pickup(state, lockstep)
    assert pickup is None


def test_pickup_filters_non_pickup_types() -> None:
    state = {
        "objects": [
            {"id": 1, "type": "monster", "is_visible": True, "distance": 10},
            {"id": 2, "type": "key", "is_visible": True, "distance": 20},
        ]
    }
    assert _nearest_available_pickup(state, {}) is not None


def test_pickup_none_when_no_objects() -> None:
    assert _nearest_available_pickup({"objects": []}, {}) is None


def test_pickup_none_when_objects_not_visible() -> None:
    state = {"objects": [{"id": 1, "type": "item", "is_visible": False, "distance": 10}]}
    assert _nearest_available_pickup(state, {}) is None


def test_pickup_prefer_resources_filters_to_ammo_weapon_item() -> None:
    state = {
        "objects": [
            {"id": 1, "type": "key", "is_visible": True, "distance": 10, "name": "RedKey"},
            {"id": 2, "type": "ammo", "is_visible": True, "distance": 50, "name": "Clip"},
        ]
    }
    pickup = _nearest_available_pickup(state, {}, prefer_resources=True)
    assert pickup is not None
    assert pickup["id"] == 2


# ── _is_stuck_decision ───────────────────────────────────────────────────────


class FakeEvent:
    def __init__(self, event_type: str | None = None) -> None:
        self.event_type = event_type


def test_stuck_decision_via_event_type() -> None:
    assert _is_stuck_decision(FakeEvent("stuck"), {}) is True


def test_stuck_decision_via_mcp_stop_reason() -> None:
    event = FakeEvent("normal")
    mcp = {"output": {"action_summary": {"stop_reason": "stuck"}}}
    assert _is_stuck_decision(event, mcp) is True


def test_stuck_decision_normal_is_not_stuck() -> None:
    event = FakeEvent("normal")
    mcp = {"output": {"action_summary": {"stop_reason": "arrived"}}}
    assert _is_stuck_decision(event, mcp) is False


def test_stuck_decision_event_without_event_type() -> None:
    assert _is_stuck_decision("not_an_object", {}) is False


# ── _combat_target_is_visible (edge cases) ───────────────────────────────────


def test_combat_visible_none_object_id() -> None:
    assert _combat_target_is_visible({"objects": []}, None) is False


def test_combat_visible_non_dict_state() -> None:
    assert _combat_target_is_visible(None, 1) is False  # type: ignore[arg-type]


def test_combat_visible_missing_objects_key() -> None:
    assert _combat_target_is_visible({}, 1) is False


def test_combat_visible_target_not_monster() -> None:
    state = {"objects": [{"id": 1, "type": "item", "is_visible": True}]}
    assert _combat_target_is_visible(state, 1) is False


# ── _is_wasted_combat_decision (edge cases) ──────────────────────────────────


def test_wasted_combat_no_shots_fired_not_wasted() -> None:
    decision = {"mcp_tool": "aim_and_shoot"}
    mcp = {"output": {"action_summary": {"stop_reason": "shots_complete", "shots_fired": 0, "hits_landed": 0, "kills": 0}}}
    assert _is_wasted_combat_decision(decision, mcp) is False


def test_wasted_combat_not_combat_tool() -> None:
    assert _is_wasted_combat_decision({"mcp_tool": "explore"}, {}) is False


def test_wasted_combat_hits_landed_not_wasted() -> None:
    decision = {"mcp_tool": "aim_and_shoot"}
    mcp = {"output": {"action_summary": {"stop_reason": "shots_complete", "shots_fired": 5, "hits_landed": 2, "kills": 0}}}
    assert _is_wasted_combat_decision(decision, mcp) is False


def test_wasted_combat_target_not_visible_is_wasted() -> None:
    decision = {"mcp_tool": "strafe_and_shoot"}
    mcp = {"output": {"action_summary": {"stop_reason": "target_not_visible"}}}
    assert _is_wasted_combat_decision(decision, mcp) is True


# ── _lockstep_stop_outcome ────────────────────────────────────────────────────


def test_stop_outcome_defaults_to_stuck() -> None:
    assert _lockstep_stop_outcome({}) == "stuck"


def test_stop_outcome_passthrough_valid() -> None:
    assert _lockstep_stop_outcome({"stop_outcome": "stuck"}) == "stuck"
    assert _lockstep_stop_outcome({"stop_outcome": "incomplete_coverage"}) == "incomplete_coverage"


def test_stop_outcome_invalid_falls_back_to_stuck() -> None:
    assert _lockstep_stop_outcome({"stop_outcome": "map_completed"}) == "stuck"
