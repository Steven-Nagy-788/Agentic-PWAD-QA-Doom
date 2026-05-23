from __future__ import annotations

from typing import TypedDict


class LockstepState(TypedDict, total=False):
    last_signature: tuple | None
    no_progress_polls: int
    recovery_count: int
    last_tick: int
    invisible_target_failures: dict[str, int]
    wasted_combat_count: int
    consecutive_explore_max_tics: int
    low_value_explore_total: int
    low_value_explore_cumulative: int
    qa_probe_count: int
    completed_object_ids: dict[str, dict[str, object]]
    failed_object_ids: dict[str, int]
    out_of_ammo_targets: dict[str, int]
    action_signature_counts: dict[str, int]
    blocked_decision_count: int
    progress_score: int
    meaningful_progress_events: int
    quality_warnings: list[str]
    visited_cells: dict[str, int]
    new_cells_last_5_decisions: int
    _new_cells_current: int
    _new_cells_decision_counts: list[int]


class ExplorationCoverage(TypedDict, total=False):
    visited_cells_count: int
    total_map_cells_estimate: int | None
    new_cells_last_5_decisions: int
    unvisited_quadrants: int | None


class LlmInput(TypedDict, total=False):
    tick: int
    threat_assessment: dict
    navigation_info: dict
    recent_trace: list[dict]
    lockstep_state: LockstepState
    exploration_coverage: ExplorationCoverage
    objects: list[dict]
    game_variables: dict


class LlmDecision(TypedDict, total=False):
    reasoning_summary: str
    mcp_tool: str
    mcp_params: dict
    observed_issue: str | dict | None


class McpCall(TypedDict, total=False):
    service: str
    tool: str
    input: dict
    output: dict


class ActionSummary(TypedDict, total=False):
    stop_reason: str
    target_name: str | None
    target_type: str | None
    shots_fired: int
    hits_landed: int
    kills: int
    tics: int


class TelemetryFrame(TypedDict, total=False):
    tic: int
    game_variables: dict
    screenshot_png_b64: str
    level_completed: bool
    map_exit: bool
    next_map: bool
