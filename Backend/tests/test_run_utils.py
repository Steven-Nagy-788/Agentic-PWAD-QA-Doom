from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.behavior_profiles import PROFILES
from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _build_llm_input,
    _build_same_run_memory,
    _compact_context_for_llm,
    _compact_state_for_llm,
    _compute_dynamic_throttle,
    _compute_unvisited_quadrants,
    _ensure_aware,
    _int_like,
    _json_safe,
    _merge_hypotheses,
    _normalize_take_action_params,
    _record_decision_in_history,
    _sector_ids_from_state,
    _summary,
    _track_explored_sectors,
    _track_visited_cell,
    _factual_game_tic,
    get_behavior_profile,
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


# ── compact LLM context and QA coverage cells ────────────────────────────────


def test_compact_state_caps_objects_and_removes_depth() -> None:
    state = _state(objects=[{"id": item, "type": "monster", "is_visible": True} for item in range(20)])
    state["depth"] = {"left": 12}
    compact = _compact_state_for_llm(state)
    assert "depth" not in compact
    assert len(compact["objects"]) == 5


def test_compact_state_removes_objects_duplicated_by_threat_context() -> None:
    state = _state(objects=[
        {"id": 1, "type": "player"},
        {"id": 2, "type": "projectile"},
        {"id": 3, "type": "decoration"},
        {"id": 4, "type": "monster"},
    ])
    compact = _compact_state_for_llm(state)
    assert compact["objects"] == [{"id": 4, "type": "monster", "weapon_advice": "use ranged (pistol/chaingun)"}]


def test_compact_context_caps_lists_and_removes_duplicate_objects() -> None:
    compact = _compact_context_for_llm({"threats": list(range(10)), "objects": [1], "weapon_state": {"owned": True}, "level": "high"})
    assert compact == {"threats": [0, 1, 2, 3, 4], "level": "high"}


def test_llm_input_has_no_prior_run_fields_and_hides_occluded_target_ids() -> None:
    payload = _build_llm_input(
        _state(),
        {"threats": [{"id": 1, "is_visible": True}, {"id": 2, "is_visible": False}]},
        {},
        {},
        game_tic=10,
        ticks_remaining=90,
        total_cells=4,
        coverage_warning=None,
    )
    assert "cross_run_memory" not in payload
    assert "lockstep_state" not in payload
    assert payload["threat_summary"]["visible_attackable_threats"] == [{"id": 1}]
    assert payload["threat_summary"]["occluded_threat_count"] == 1


def test_track_visited_cell_uses_comma_delimited_256_unit_grid() -> None:
    lockstep = {}
    _track_visited_cell({"game_variables": {"x": 260, "y": -260}}, lockstep)
    assert lockstep["visited_cells"] == {"1,-1": 1}


def test_unvisited_quadrants_parses_comma_delimited_cells() -> None:
    assert _compute_unvisited_quadrants({"visited_cells": {"-1,-1": 1, "1,1": 1}}) == 2


def test_run_history_uses_persisted_tick_budget() -> None:
    lockstep = {}
    _record_decision_in_history(
        lockstep,
        seq=0,
        tick_before=10,
        tick_after=70,
        tool="explore",
        stop_reason="max_tics",
        params={"max_tics": 60},
        reasoning="Explore north",
        guard_modified=False,
        llm_duration_ms=1,
        mcp_duration_ms=2,
        total_budget=5000,
    )
    assert _build_same_run_memory(lockstep)["budget"]["total_ticks"] == 5000


def test_same_run_ledger_compacts_older_actions_deterministically_and_stays_bounded() -> None:
    lockstep = {}
    for seq in range(30):
        _record_decision_in_history(
            lockstep,
            seq=seq,
            tick_before=seq,
            tick_after=seq + 1,
            tool="explore",
            stop_reason="max_tics",
            params={"max_tics": 80},
            reasoning="x" * 120,
            guard_modified=False,
            llm_duration_ms=1,
            mcp_duration_ms=2,
            total_budget=5000,
        )
    ledger = _build_same_run_memory(lockstep, max_chars=4000, recent_action_limit=16)
    import json
    assert len(json.dumps(ledger, separators=(",", ":"))) <= 4000
    assert ledger == _build_same_run_memory(lockstep, max_chars=4000, recent_action_limit=16)
    assert ledger["older_milestones"]["compacted_action_count"] + len(ledger["recent_actions"]) == 30


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


# ── factual game tic ─────────────────────────────────────────────────────────


def test_factual_game_tic_allows_repeated_or_lower_tics_without_fabrication() -> None:
    ls = {"last_tick": -1}
    t1 = _factual_game_tic({"tic": 10}, ls)
    assert t1 == 10
    assert ls["last_tick"] == 10
    t2 = _factual_game_tic({"tic": 5}, ls)
    assert t2 == 5
    assert ls["last_tick"] == 10


def test_factual_game_tic_defaults_to_last_observed_when_missing() -> None:
    ls = {"last_tick": -1}
    tick = _factual_game_tic({}, ls)
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


# ── structured in-run memory ─────────────────────────────────────────────────


def test_structured_memory_tracks_sector_ids_from_navigation() -> None:
    lockstep = {}
    _track_explored_sectors({}, {"current_sector_id": 2, "visited_sector_ids": [1, "3"]}, lockstep)
    assert _sector_ids_from_state(lockstep) == [1, 2, 3]


def test_merge_hypotheses_deduplicates_and_limits() -> None:
    lockstep = {"hypotheses": ["Starting area appears blocked"]}
    _merge_hypotheses(
        lockstep,
        {
            "hypotheses": [
                "Starting area appears blocked",
                "ClipBox pickup may be unreachable",
            ],
            "observed_issue": {"description": "Invisible collision near spawn"},
        },
    )
    assert lockstep["hypotheses"] == [
        "Starting area appears blocked",
        "ClipBox pickup may be unreachable",
        "Invisible collision near spawn",
    ]


def test_behavior_profile_fallback_uses_settings_default() -> None:
    profile = get_behavior_profile(None)
    assert profile.name in PROFILES


def test_behavior_profile_throttle_keys_match_lockstep_contexts() -> None:
    for profile in PROFILES.values():
        assert {"combat", "low_health", "stuck", "default"} <= set(profile.throttle_delays)
