"""Tests for run_guards guard logic."""

from __future__ import annotations

from app.services.run_guards import apply_guards


def _base_state(**overrides) -> dict:
    state: dict = {
        "consecutive_get_state": 0,
        "position_stuck_counter": 0,
        "decision_diversity_counter": 0,
        "coverage_percent": 0,
        "player_kills": 0,
        "spawned_enemy_count": 0,
        "ticks_remaining": 5000,
        "failure_critiques": [],
    }
    state.update(overrides)
    return state


def _decision(tool: str = "explore", params: dict | None = None, outcome: str | None = None) -> dict:
    d: dict = {"mcp_tool": tool, "mcp_params": params or {}, "reasoning_summary": "original plan"}
    if outcome is not None:
        d["mcp_params"] = {"outcome": outcome}
    return d


def test_guard_disabled_passes_through() -> None:
    state = _base_state(consecutive_get_state=5)
    dec = _decision("get_state")
    result = apply_guards(dec, state, tick=100, guard_enabled=False)
    assert result["mcp_tool"] == "get_state"
    assert "_decision_source" not in result


def test_guard_get_state_spam_forces_explore() -> None:
    state = _base_state(consecutive_get_state=2)
    dec = _decision("get_state")
    apply_guards(dec, state, tick=10, guard_enabled=True)
    assert dec["mcp_tool"] == "explore"
    assert dec["mcp_params"]["turn_before"] == 180.0
    assert dec["_decision_source"] == "guard_get_state"
    assert len(state["failure_critiques"]) == 1


def test_guard_get_state_spam_skips_when_count_below_threshold() -> None:
    state = _base_state(consecutive_get_state=1)
    dec = _decision("get_state")
    apply_guards(dec, state, tick=10, guard_enabled=True)
    assert dec["mcp_tool"] == "get_state"
    assert "_decision_source" not in dec


def test_guard_get_state_spam_skips_non_get_state_tool() -> None:
    state = _base_state(consecutive_get_state=3)
    dec = _decision("explore")
    apply_guards(dec, state, tick=10, guard_enabled=True)
    assert dec["mcp_tool"] == "explore"
    assert dec.get("_decision_source") is None


def test_guard_position_stuck_forces_explore() -> None:
    state = _base_state(position_stuck_counter=3)
    dec = _decision("explore")
    apply_guards(dec, state, tick=20, guard_enabled=True)
    assert dec["mcp_tool"] == "explore"
    assert dec["mcp_params"]["turn_before"] == -180.0
    assert dec["_decision_source"] == "guard_stuck"


def test_guard_position_stuck_skips_combat_tools() -> None:
    state = _base_state(position_stuck_counter=5)
    dec = _decision("aim_and_shoot")
    apply_guards(dec, state, tick=20, guard_enabled=True)
    assert dec["mcp_tool"] == "aim_and_shoot"
    assert "_decision_source" not in dec


def test_guard_position_stuck_skips_below_threshold() -> None:
    state = _base_state(position_stuck_counter=1)
    dec = _decision("explore")
    apply_guards(dec, state, tick=20, guard_enabled=True)
    assert dec["mcp_tool"] == "explore"
    assert "_decision_source" not in dec


def test_guard_decision_diversity_forces_explore() -> None:
    state = _base_state(decision_diversity_counter=4)
    dec = _decision("explore")
    apply_guards(dec, state, tick=30, guard_enabled=True)
    assert dec["mcp_tool"] == "explore"
    assert dec["mcp_params"]["turn_before"] == 90.0
    assert dec["_decision_source"] == "guard_diversity"


def test_guard_finish_premature_blocks_when_conditions_unmet() -> None:
    state = _base_state(coverage_percent=30, player_kills=2, spawned_enemy_count=10, ticks_remaining=1000)
    dec = _decision("finish", outcome="qa_completed")
    apply_guards(dec, state, tick=100, guard_enabled=True)
    assert dec["mcp_tool"] == "explore"
    assert dec["_decision_source"] == "guard_finish_premature"


def test_guard_finish_premature_allows_when_conditions_met() -> None:
    state = _base_state(coverage_percent=95, player_kills=10, spawned_enemy_count=10, ticks_remaining=1000)
    dec = _decision("finish", outcome="qa_completed")
    apply_guards(dec, state, tick=100, guard_enabled=True)
    assert dec["mcp_tool"] == "finish"
    assert "_decision_source" not in dec


def test_guard_finish_premature_allows_when_budget_exhausted() -> None:
    state = _base_state(coverage_percent=20, player_kills=0, spawned_enemy_count=10, ticks_remaining=50)
    dec = _decision("finish", outcome="qa_completed")
    apply_guards(dec, state, tick=100, guard_enabled=True)
    assert dec["mcp_tool"] == "finish"
    assert "_decision_source" not in dec


def test_guard_finish_premature_allows_non_qa_outcome() -> None:
    state = _base_state(coverage_percent=10, player_kills=0, spawned_enemy_count=10, ticks_remaining=2000)
    dec = _decision("finish", outcome="player_died")
    apply_guards(dec, state, tick=100, guard_enabled=True)
    assert dec["mcp_tool"] == "finish"
    assert "_decision_source" not in dec
