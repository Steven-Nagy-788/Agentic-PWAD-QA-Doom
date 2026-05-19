"""Unit tests for autonomous executor director-facing state."""

from collections import deque
import threading

from doom_mcp.executor import AutonomousExecutor, ExecutorState, Objective, ObjectiveType, Strategy


def _executor_shell() -> AutonomousExecutor:
    executor = AutonomousExecutor.__new__(AutonomousExecutor)
    executor._director_lock = threading.Lock()
    executor._objectives = []
    executor._strategy = Strategy()
    executor._events = deque(maxlen=100)
    executor._event_cursor = 0
    executor._state = ExecutorState.IDLE
    executor._position_history = []
    executor._stuck_phase = 0
    executor._stuck_tics = 0
    executor._stuck_recovery_count = 0
    executor._last_progress_tic = 0
    executor._current_target_id = None
    return executor


def test_push_objective_replace_clears_queue_and_logs_event() -> None:
    executor = _executor_shell()

    executor.push_objective(Objective(ObjectiveType.EXPLORE, priority=1))
    executor.push_objective(Objective(ObjectiveType.RETREAT, priority=50), replace=True)

    queue = executor.get_objectives()
    events = executor.get_recent_events()

    assert [item["type"] for item in queue] == ["retreat"]
    assert queue[0]["age_tics"] == 0
    assert any(event["event_type"] == "objectives_cleared" for event in events)
    assert any(event["event_type"] == "objective_set" for event in events)


def test_progress_report_exposes_stuck_recovery_state() -> None:
    executor = _executor_shell()
    executor._position_history = [(0.0, 0.0), (3.0, 4.0)]
    executor._stuck_phase = 2
    executor._stuck_tics = 4
    executor._stuck_recovery_count = 3
    executor._last_progress_tic = 99
    executor._current_target_id = 12

    progress = executor.get_progress()

    assert progress["position_spread"] == 5.0
    assert progress["stuck_phase"] == 2
    assert progress["stuck_recovery_count"] == 3
    assert progress["last_progress_tic"] == 99
    assert progress["current_target_id"] == 12
