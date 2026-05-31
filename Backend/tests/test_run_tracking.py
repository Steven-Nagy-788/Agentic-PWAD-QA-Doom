from __future__ import annotations

from unittest.mock import patch

from app.services.run_tracking import _lockstep_should_stop_as_stuck, _lockstep_stop_outcome, _update_lockstep_after_action


def _state(x: float = 0, y: float = 0) -> dict:
    return {
        "game_variables": {
            "POSITION_X": x,
            "POSITION_Y": y,
            "KILLCOUNT": 0,
            "ITEMCOUNT": 0,
            "SECRETCOUNT": 0,
        }
    }


def test_tracking_stops_after_configured_consecutive_no_progress_decisions_without_rewrite() -> None:
    decision = {"mcp_tool": "take_action", "mcp_params": {"actions": {"USE": 1}, "tics": 1}}
    call = {
        "tool": "take_action",
        "input": {"actions": {"USE": 1}, "tics": 1},
        "output": {"action_summary": {"stop_reason": "tics_complete"}},
    }
    state = {}
    with patch("app.services.run_tracking.get_settings") as settings:
        settings.return_value.no_progress_decision_abort_threshold = 2
        _update_lockstep_after_action(decision, call, state, _state())
        _update_lockstep_after_action(decision, call, state, _state())
        _update_lockstep_after_action(decision, call, state, _state())

    assert decision == {"mcp_tool": "take_action", "mcp_params": {"actions": {"USE": 1}, "tics": 1}}
    assert _lockstep_should_stop_as_stuck(state) is True
    assert _lockstep_stop_outcome(state) == "inconclusive_agent_stall"
