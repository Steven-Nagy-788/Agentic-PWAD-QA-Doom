"""Guard logic for the lockstep agent run loop.

Guards override bad LLM decisions before execution:
1. get_state spam guard: forces explore after 2+ consecutive get_state calls
2. Position stuck detection: forces explore when agent hasn't moved
3. Decision diversity check: breaks loops of repeated same-tool decisions
4. Premature finish guard: blocks finish() until completion conditions are met
"""

from __future__ import annotations

from typing import Any

from app.core.types import LockstepState


COMBAT_TOOLS = frozenset({"aim_and_shoot", "strafe_and_shoot", "select_weapon"})


def apply_guards(
    decision: dict[str, Any],
    lockstep_state: LockstepState,
    tick: int,
    guard_enabled: bool,
) -> dict[str, Any]:
    """Apply all guard checks to a decision. Returns the (possibly modified) decision.

    Each guard mutates the decision dict in-place and records a failure critique.
    Returns the same decision dict for convenience.
    """
    if not guard_enabled:
        return decision

    _guard_get_state_spam(decision, lockstep_state, tick)
    _guard_position_stuck(decision, lockstep_state, tick)
    _guard_decision_diversity(decision, lockstep_state, tick)
    _guard_finish_premature(decision, lockstep_state, tick)

    return decision


def _guard_get_state_spam(
    decision: dict[str, Any],
    lockstep_state: LockstepState,
    tick: int,
) -> None:
    """After 2+ consecutive get_state calls, force explore with 180-degree turn."""
    from app.services.run_utils import _record_failure_critique

    get_state_count = lockstep_state.get("consecutive_get_state", 0)
    if get_state_count < 2 or decision.get("mcp_tool") != "get_state":
        return

    _record_failure_critique(
        lockstep_state,
        tick=tick,
        tool="get_state",
        params={},
        reason="Called get_state multiple times consecutively instead of taking action.",
    )
    decision["mcp_tool"] = "explore"
    decision["mcp_params"] = {
        "max_tics": 80,
        "stop_on_enemy": False,
        "stop_on_item": True,
        "turn_before": 180.0,
    }
    decision["reasoning_summary"] = (
        "OVERRIDE: Consecutive get_state detected. Forced explore with 180° turn to advance gameplay."
    )
    decision["_decision_source"] = "guard_get_state"


def _guard_position_stuck(
    decision: dict[str, Any],
    lockstep_state: LockstepState,
    tick: int,
) -> None:
    """If agent hasn't moved for 2+ decisions, force explore with alternating turn direction.

    Excludes combat tools — agent is actively fighting, not stuck.
    """
    from app.services.run_utils import _record_failure_critique

    stuck_counter = lockstep_state.get("position_stuck_counter", 0)
    if stuck_counter < 2 or decision.get("mcp_tool") not in (
        "explore",
        "move_to",
        "take_action",
    ):
        return

    _record_failure_critique(
        lockstep_state,
        tick=tick,
        tool=decision.get("mcp_tool", "unknown"),
        params=decision.get("mcp_params", {}),
        reason=f"Agent stuck for {stuck_counter} decisions without meaningful movement. Need different approach.",
    )
    turn_amount = 180.0 if stuck_counter % 2 == 0 else -180.0
    decision["mcp_tool"] = "explore"
    decision["mcp_params"] = {
        "max_tics": 80,
        "stop_on_enemy": False,
        "stop_on_item": True,
        "turn_before": turn_amount,
    }
    decision["reasoning_summary"] = (
        f"OVERRIDE: Agent stuck ({stuck_counter} decisions without meaningful movement). "
        f"Your original plan: {decision.get('reasoning_summary', '?')}. "
        f"Guard forced explore with {turn_amount}° turn to break fixation."
    )
    decision["_decision_source"] = "guard_stuck"


def _guard_decision_diversity(
    decision: dict[str, Any],
    lockstep_state: LockstepState,
    tick: int,
) -> None:
    """If 3+ consecutive decisions used the same non-combat tool, force diverse exploration."""
    from app.services.run_utils import _record_failure_critique

    diversity_counter = lockstep_state.get("decision_diversity_counter", 0)
    tool = decision.get("mcp_tool")
    if (
        diversity_counter < 3
        or tool not in ("explore", "move_to", "take_action")
        or tool in COMBAT_TOOLS
    ):
        return

    _record_failure_critique(
        lockstep_state,
        tick=tick,
        tool=tool or "unknown",
        params=decision.get("mcp_params", {}),
        reason=f"Decision loop: {diversity_counter} repeated {tool} calls. Must change strategy.",
    )
    decision["mcp_tool"] = "explore"
    decision["mcp_params"] = {
        "max_tics": 80,
        "stop_on_enemy": False,
        "stop_on_item": False,
        "ignore_object_ids": [],
        "turn_before": 90.0,
    }
    decision["reasoning_summary"] = (
        f"OVERRIDE: Decision loop detected ({diversity_counter} repeated decisions). "
        f"Your original plan: {decision.get('reasoning_summary', '?')}. "
        f"Guard forced diverse exploration with 90° turn to break cycle."
    )
    decision["_decision_source"] = "guard_diversity"


def _guard_finish_premature(
    decision: dict[str, Any],
    lockstep_state: LockstepState,
    tick: int,
) -> None:
    """Block finish() calls unless completion conditions are met.

    Requires coverage >= 90% and all enemies killed for outcome="qa_completed".
    Exceptions: timeout (ticks < 200), player_died, softlock, pwad_crash.
    """
    from app.services.run_utils import _record_failure_critique

    if decision.get("mcp_tool") != "finish":
        return

    params = decision.get("mcp_params") or {}
    outcome = str(params.get("outcome", "qa_completed")).lower()

    # Non-qa_completed outcomes are always allowed (death, crash, softlock)
    if outcome != "qa_completed":
        return

    coverage_pct = float(lockstep_state.get("coverage_percent", 0) or 0)
    kills = int(lockstep_state.get("player_kills", 0) or 0)
    spawned = int(lockstep_state.get("spawned_enemy_count", 0) or 0)
    ticks_remaining = int(lockstep_state.get("ticks_remaining", 0) or 0)

    # Allow finish if budget is nearly exhausted
    if ticks_remaining < 200:
        return

    # Allow finish if conditions are met
    if coverage_pct >= 90 and kills >= spawned:
        return

    # Block premature finish — override with explore
    _record_failure_critique(
        lockstep_state,
        tick=tick,
        tool="finish",
        params=params,
        reason=(
            f"finish() blocked: coverage={coverage_pct:.1f}% (need 90%), "
            f"kills={kills}/{spawned}. Must continue exploring and fighting."
        ),
    )
    decision["mcp_tool"] = "explore"
    decision["mcp_params"] = {
        "max_tics": 200,
        "stop_on_enemy": False,
        "stop_on_item": True,
    }
    decision["reasoning_summary"] = (
        f"OVERRIDE: finish() blocked — not all completion conditions met. "
        f"Coverage: {coverage_pct:.1f}% (need 90%), Kills: {kills}/{spawned}. "
        f"Forced explore to continue the run."
    )
    decision["_decision_source"] = "guard_finish_premature"
