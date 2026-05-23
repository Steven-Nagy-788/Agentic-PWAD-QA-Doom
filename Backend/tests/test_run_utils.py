from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _compute_dynamic_stride,
    _compute_dynamic_throttle,
    _ensure_aware,
    _int_like,
    _json_safe,
    _normalize_take_action_params,
    _summary,
    _unique_lockstep_tick,
)


def _state(**overrides):
    data = {
        "game_variables": {
            "x": 0, "y": 0, "health": 100,
            "ammo_bullets": 10, "ammo_shells": 0, "ammo_rockets": 0, "ammo_cells": 0,
        },
        "objects": [],
    }
    data.update(overrides)
    return data


def _lockstep(**overrides):
    data = {"no_progress_polls": 0}
    data.update(overrides)
    return data


# ── _compute_dynamic_stride ──────────────────────────────────────────────────


def test_stride_returns_one_when_visible_monsters_exist() -> None:
    state = _state(objects=[{"type": "monster", "is_visible": True, "id": 1}])
    assert _compute_dynamic_stride(state, _lockstep()) == 1


def test_stride_returns_five_when_stuck() -> None:
    assert _compute_dynamic_stride(_state(), _lockstep(no_progress_polls=1)) == 5
    assert _compute_dynamic_stride(_state(), _lockstep(no_progress_polls=5)) == 5


def test_stride_returns_three_by_default() -> None:
    assert _compute_dynamic_stride(_state(), _lockstep()) == 3


def test_stride_honors_only_visible_monsters() -> None:
    state = _state(objects=[{"type": "monster", "is_visible": False, "id": 2}])
    assert _compute_dynamic_stride(state, _lockstep()) == 3


def test_stride_combat_overrides_stuck() -> None:
    state = _state(objects=[{"type": "monster", "is_visible": True, "id": 1}])
    assert _compute_dynamic_stride(state, _lockstep(no_progress_polls=5)) == 1


# ── _compute_dynamic_throttle ────────────────────────────────────────────────


def test_throttle_combat_returns_three() -> None:
    state = _state(objects=[{"type": "monster", "is_visible": True, "id": 1}])
    assert _compute_dynamic_throttle(state, _lockstep()) == 3.0


def test_throttle_low_health_returns_six() -> None:
    state = _state(game_variables={"x": 0, "y": 0, "health": 20})
    assert _compute_dynamic_throttle(state, _lockstep()) == 6.0


def test_throttle_no_ammo_returns_six() -> None:
    state = _state(game_variables={"x": 0, "y": 0, "health": 100, "ammo_total": 0})
    assert _compute_dynamic_throttle(state, _lockstep()) == 6.0


def test_throttle_stuck_returns_ten() -> None:
    assert _compute_dynamic_throttle(_state(), _lockstep(no_progress_polls=2)) == 10.0


def test_throttle_default_returns_twelve() -> None:
    assert _compute_dynamic_throttle(_state(), _lockstep()) == 12.0


# ── _bounded_int ─────────────────────────────────────────────────────────────


def test_bounded_int_parses_and_clamps() -> None:
    assert _bounded_int("5", default=0) == 5
    assert _bounded_int(-1, default=0) == 0
    assert _bounded_int(100, default=0, upper=50) == 50
    assert _bounded_int("not_a_number", default=10) == 10
    assert _bounded_int(None, default=3) == 3


# ── _bounded_float ───────────────────────────────────────────────────────────


def test_bounded_float_parses_and_defaults() -> None:
    assert _bounded_float("3.14", 0.0) == 3.14
    assert _bounded_float(None, 1.5) == 1.5
    assert _bounded_float("bad", 2.0) == 2.0


# ── _int_like ────────────────────────────────────────────────────────────────


def test_int_like_converts() -> None:
    assert _int_like("42") == 42
    assert _int_like(3.9) == 3
    assert _int_like(None) == 0
    assert _int_like("garbage") == 0


# ── _json_safe ───────────────────────────────────────────────────────────────


def test_json_safe_passthrough() -> None:
    data = {"a": 1, "b": "hello"}
    assert _json_safe(data) is data


def test_json_safe_custom_object() -> None:
    class Custom:
        def __str__(self) -> str:
            return "custom_str"

    raw = {"obj": Custom()}
    result = _json_safe(raw)
    import json
    assert json.dumps(result, default=str) is not None


# ── _summary ─────────────────────────────────────────────────────────────────


def test_summary_truncates_long_text() -> None:
    long_value = "x" * 2000
    result = _summary(long_value)
    assert len(result) == 1003
    assert result.endswith("...")


def test_summary_short_passthrough() -> None:
    assert _summary("short") == "short"
    assert _summary(42) == "42"


# ── _ensure_aware ────────────────────────────────────────────────────────────


def test_ensure_aware_naive_becomes_aware() -> None:
    naive = datetime(2025, 1, 1)
    result = _ensure_aware(naive)
    assert result.tzinfo is not None
    assert result.tzinfo == UTC


def test_ensure_aware_already_aware() -> None:
    aware = datetime(2025, 1, 1, tzinfo=UTC)
    result = _ensure_aware(aware)
    assert result is aware


def test_ensure_aware_none() -> None:
    assert _ensure_aware(None) is None


# ── _unique_lockstep_tick ────────────────────────────────────────────────────


def test_unique_lockstep_tick_increments() -> None:
    ls = {"last_tick": -1}
    t1 = _unique_lockstep_tick({"tic": 10}, ls)
    assert t1 == 10
    assert ls["last_tick"] == 10
    t2 = _unique_lockstep_tick({"tic": 5}, ls)
    assert t2 == 11
    assert ls["last_tick"] == 11


def test_unique_lockstep_tick_default_when_missing_tic() -> None:
    ls = {"last_tick": -1}
    tick = _unique_lockstep_tick({}, ls)
    assert tick == 0
    assert ls["last_tick"] == 0


# ── _normalize_take_action_params ────────────────────────────────────────────


def test_normalize_take_action_params_clamps_actions() -> None:
    result = _normalize_take_action_params({
        "actions": {"TURN_LEFT_RIGHT_DELTA": 120, "MOVE_FORWARD_BACKWARD_DELTA": 90, "USE": 2},
        "tics": 99,
    })
    assert result["actions"]["TURN_LEFT_RIGHT_DELTA"] == 45.0
    assert result["actions"]["MOVE_FORWARD_BACKWARD_DELTA"] == 50.0
    assert result["actions"]["USE"] == 1
    assert result["tics"] == 8


def test_normalize_take_action_params_defaults() -> None:
    result = _normalize_take_action_params({})
    assert result["actions"] == {}
    assert result["tics"] == 4


def test_take_action_filters_unknown_buttons() -> None:
    result = _normalize_take_action_params({
        "actions": {"UNKNOWN_BUTTON": 1, "MOVE_FORWARD_BACKWARD_DELTA": 10},
    })
    assert "UNKNOWN_BUTTON" not in result["actions"]
    assert result["actions"]["MOVE_FORWARD_BACKWARD_DELTA"] == 10.0
