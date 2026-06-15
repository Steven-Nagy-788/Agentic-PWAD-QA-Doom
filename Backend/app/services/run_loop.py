from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.types import LockstepState
from app.models import AgentDecision, Defect, GameEvent, TestRun
from app.repositories.agent_decision_repository import AgentDecisionRepository
from app.repositories.defect_repository import DefectRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.services.collector_service import CollectorService, normalize_variables
from app.services.defect_service import DefectService
from app.repositories.config_repository import ConfigRepository
from app.services.analysis_constants import CELL_SIZE
from app.services.gemini_service import GeminiService, estimate_llm_cost_usd
from app.services.environment_service import collect_environment_metadata
from app.services.mcp_client_service import McpDoomClient, McpStartupError, McpToolTimeoutError, normalize_mcp_state
from app.services.prompt_service import render_agent_prompt
from app.services.recording_service import RecordingService, jpeg_b64, png_bytes_to_frame
from app.services.report_service import ReportService
from app.services.run_constants import RUN_TASKS
from app.services.run_tracking import (
    _lockstep_progress_metrics,
    _lockstep_quality_flags,
    _lockstep_should_stop_as_stuck,
    _lockstep_stop_outcome,
    _update_lockstep_after_action,
)
from app.services.run_memory import RunMemoryService
from app.services.run_telemetry import (
    _broadcast_state,
    _pop_telemetry_frames,
    _record_telemetry_frames,
)
from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _build_llm_input,
    _build_same_run_memory,
    _compact_mcp_output,
    _compute_dynamic_throttle,
    _finalize_lockstep_decision,
    _infrastructure_failure_fields,
    _initial_lockstep_state,
    _json_safe,
    _merge_hypotheses,
    _mcp_action_summary,
    _normalize_mcp_params,
    _pwad_crash_fields,
    _record_checkpoint,
    _record_decision_in_history,
    _record_event_in_history,
    _record_failure_critique,
    _record_position_in_trail,
    _state_report_call,
    _summary,
    _track_explored_sectors,
    _track_visited_cell,
    _factual_game_tic,
    _update_combat_log,
    _update_objective_history,
    generate_map_layout_png,
    get_behavior_profile,
)
from app.services.websocket_service import websocket_service


async def _build_cross_run_memory_context(
    db: AsyncSession,
    wad_file_id: UUID,
    map_name: str,
) -> str:
    """Build cross-run memory context from hypotheses and spatial memory."""
    from app.models import WadHypothesis, WadSpatialMemory
    from sqlalchemy import select

    parts: list[str] = []

    # High-confidence hypotheses from previous runs
    hyp_result = await db.execute(
        select(WadHypothesis).where(
            WadHypothesis.wad_file_id == wad_file_id,
            WadHypothesis.map_name == map_name.upper(),
            WadHypothesis.confidence >= 0.5,
            WadHypothesis.refuted_at.is_(None),
        ).order_by(WadHypothesis.confidence.desc()).limit(10)
    )
    hypotheses = list(hyp_result.scalars().all())
    if hypotheses:
        hyp_lines = []
        for h in hypotheses:
            hyp_lines.append(f"- [{h.tag}] {h.content} (confidence: {h.confidence:.1f})")
        parts.append("CROSS-RUN HYPOTHESES:\n" + "\n".join(hyp_lines))

    # Spatial memory: high-death or high-stuck cells
    spatial_result = await db.execute(
        select(WadSpatialMemory).where(
            WadSpatialMemory.wad_file_id == wad_file_id,
            WadSpatialMemory.map_name == map_name.upper(),
            WadSpatialMemory.event_type.in_(["death", "stuck"]),
            WadSpatialMemory.occurrence_count >= 3,
        ).order_by(WadSpatialMemory.occurrence_count.desc()).limit(10)
    )
    spatial = list(spatial_result.scalars().all())
    if spatial:
        spatial_lines = []
        for s in spatial:
            spatial_lines.append(
                f"- Cell ({s.cell_x},{s.cell_y}): {s.event_type} x{s.occurrence_count}"
            )
        parts.append("KNOWN DANGER ZONES:\n" + "\n".join(spatial_lines))

    if not parts:
        return ""
    return (
        "## CROSS-RUN MEMORY (from previous runs on this map)\n"
        + "\n\n".join(parts)
        + "\n\nUse this as context only. Do not blindly follow old hypotheses—verify through gameplay."
    )


logger = logging.getLogger(__name__)


async def agent_run_task(run_id: UUID) -> None:
    # Phase 1: load initial data in a short-lived session, then close it
    async with SessionLocal() as db:
        run_orm = await db.get(TestRun, run_id)
        if run_orm is None:
            return
        wad = await WadRepository(db).get_by_id(run_orm.wad_file_id)
        from app.models import StaticAnalysisResult

        analysis = await db.get(StaticAnalysisResult, run_orm.static_analysis_id) if run_orm.static_analysis_id else None
        if wad is None or analysis is None:
            await RunRepository(db).update(
                run_orm,
                status="failed",
                outcome="error",
                error_message="Run is missing WAD or static analysis",
            )
            await db.commit()
            return
        settings = get_settings()
        runtime_overrides = await ConfigRepository(db).get_all()

        def runtime_value(key: str, fallback: Any = None) -> Any:
            return runtime_overrides.get(key, getattr(settings, key, fallback))

        profile = get_behavior_profile(run_orm)
        total_map_cells_estimate = _estimate_total_map_cells(analysis)
        prompt = render_agent_prompt(wad, analysis, run_orm) + "\n\n" + profile.system_prompt_addendum

        # Conditionally inject cross-run memory
        cross_run_enabled = runtime_value("cross_run_memory_enabled", settings.cross_run_memory_enabled)
        if cross_run_enabled:
            cross_run_context = await _build_cross_run_memory_context(
                db, run_orm.wad_file_id, run_orm.map_name
            )
            if cross_run_context:
                prompt += f"\n\n{cross_run_context}"

        # Extract primitive values before session closes
        run_id_val = run_orm.id
        wad_file_id = run_orm.wad_file_id
        map_name_val = run_orm.map_name
        max_ticks = run_orm.max_ticks
        seed = run_orm.seed
        iwad_used = run_orm.iwad_used
        difficulty_level = run_orm.difficulty_level
        llm_model = run_orm.llm_model
        wad_stored_path = wad.stored_path
        map_overview_png_path = getattr(analysis, "map_overview_png_path", None)
        map_bounds_raw = (analysis.spawn_summary_by_skill or {}).get("_map_features", {}).get("bounds") if analysis else None
        map_bounds_for_layout = None
        if isinstance(map_bounds_raw, dict):
            try:
                map_bounds_for_layout = {
                    "min_x": float(map_bounds_raw["min_x"]),
                    "max_x": float(map_bounds_raw["max_x"]),
                    "min_y": float(map_bounds_raw["min_y"]),
                    "max_y": float(map_bounds_raw["max_y"]),
                }
            except (KeyError, TypeError, ValueError):
                pass
        recording_fps = max(15.0, _bounded_float(runtime_value("recording_fps", settings.recording_fps), settings.recording_fps))
        gemini_rate_limit = _bounded_int(
            runtime_value("gemini_rate_limit_calls_per_minute", settings.gemini_rate_limit_calls_per_minute),
            settings.gemini_rate_limit_calls_per_minute,
            lower=0,
        )
        llm_input_cost_per_million = _bounded_float(
            runtime_value("llm_input_cost_per_million", settings.llm_input_cost_per_million),
            settings.llm_input_cost_per_million,
        )
        llm_output_cost_per_million = _bounded_float(
            runtime_value("llm_output_cost_per_million", settings.llm_output_cost_per_million),
            settings.llm_output_cost_per_million,
        )
        llm_throttle_cap_seconds = _bounded_float(
            runtime_value("llm_throttle_seconds", settings.llm_throttle_seconds),
            settings.llm_throttle_seconds,
        )
        live_frame_fps = max(0.1, _bounded_float(runtime_value("live_frame_fps", settings.live_frame_fps), settings.live_frame_fps))
        recording_telemetry_stride = _bounded_int(
            runtime_value("recording_telemetry_stride", settings.recording_telemetry_stride),
            settings.recording_telemetry_stride,
            lower=1,
            upper=10,
        )

    # Phase 1 complete — session closed, all ORM objects detached
    lockstep_state: LockstepState = _initial_lockstep_state()
    if total_map_cells_estimate is not None:
        lockstep_state["total_map_cells_estimate"] = total_map_cells_estimate
    recorder = RecordingService(str(run_id_val), fps=recording_fps)
    gemini = GeminiService(
        llm_model=llm_model,
        rate_limit_calls_per_minute=gemini_rate_limit,
    )
    total_actions = 0
    total_llm_calls = 0
    last_frame_at = 0.0
    outcome = "timeout"
    latest_event = None
    mcp_client: McpDoomClient | None = None
    runtime_stage = "startup"
    failure_fields: dict[str, Any] = {}
    last_record_frame: Any = None

    # Helpers that extract needed primitive values from `run_orm` before they go out of scope
    def _run_status() -> str:
        return "running"

    try:
        async with McpDoomClient() as mcp:
            mcp_client = mcp
            await mcp.start_game(
                wad=iwad_used,
                scenario_wad=wad_stored_path,
                map_name=map_name_val,
                difficulty=difficulty_level,
                episode_timeout=max_ticks,
                async_player=False,
                seed=seed,
            )
            try:
                mcp_metadata = await mcp.get_runtime_metadata()
            except Exception:
                mcp_metadata = {}
            environment_metadata = await collect_environment_metadata(
                mcp_metadata,
                model=llm_model,
                iwad=iwad_used,
                difficulty=difficulty_level,
                max_ticks=max_ticks,
                seed=seed,
            )
            # Set status to running in its own short session
            async with SessionLocal() as db:
                run_orm = await db.get(TestRun, run_id_val)
                if run_orm is not None:
                    await RunRepository(db).update(
                        run_orm,
                        status="running",
                        started_at=datetime.now(UTC),
                        environment_metadata=_json_safe(environment_metadata),
                    )
                    await db.commit()
            runtime_stage = "gameplay"
            sequence_number = 0

            while True:
                state, screenshot_png = await mcp.get_state()
                tick = _factual_game_tic(state, lockstep_state)
                _track_visited_cell(state, lockstep_state)
                frame = png_bytes_to_frame(screenshot_png)
                if frame is not None:
                    last_record_frame = frame
                    recorder.write_frame(frame, game_tick=tick)
                threat_assessment = await _safe_context_tool(mcp, "get_threat_assessment")
                navigation_info = await _safe_context_tool(mcp, "get_navigation_info")
                _track_explored_sectors(state, navigation_info, lockstep_state)
                visited_count = len(lockstep_state.get("visited_cells") or {})
                ticks_remaining = max(0, max_ticks - tick)
                total_cells = lockstep_state.get("total_map_cells_estimate", 225) or 225
                coverage_percent = round(visited_count / max(total_cells, 1) * 100, 1)
                coverage_warning = None
                if coverage_percent < 20 and ticks_remaining < max_ticks * 0.7:
                    coverage_warning = (
                        f"WARNING: Coverage is only {coverage_percent}% with {ticks_remaining} ticks remaining. "
                        "Stop fighting and EXPLORE immediately. Use the map layout to find unvisited areas."
                    )
                elif coverage_percent < 10 and ticks_remaining < max_ticks * 0.5:
                    coverage_warning = (
                        f"CRITICAL: Coverage is {coverage_percent}% with {ticks_remaining} ticks remaining. "
                        "You are barely exploring. Find new areas NOW using the map layout frontier cells."
                    )
                llm_input = _build_llm_input(
                    state,
                    threat_assessment,
                    navigation_info,
                    lockstep_state,
                    game_tic=tick,
                    ticks_remaining=ticks_remaining,
                    total_cells=total_cells,
                    coverage_warning=coverage_warning,
                )

                # Each iteration acquires its own DB session, commits, and releases
                async with SessionLocal() as db:
                    run_orm = await db.get(TestRun, run_id_val)
                    if run_orm is None:
                        outcome = "error"
                        break
                    collector = CollectorService(db)
                    decision_repo = AgentDecisionRepository(db)

                    if _situation_finished(state):
                        decision = {
                            "reasoning_summary": "Runtime reported the episode finished; recording final situation.",
                            "mcp_tool": "get_state",
                            "mcp_params": {},
                        }
                        mcp_call = _state_report_call(state)
                        decision_row = await decision_repo.create(
                            AgentDecision(
                                run_id=run_id_val,
                                sequence_number=sequence_number,
                                tick_before=tick,
                                tick_after=tick,
                                status="complete",
                                llm_input_summary=_json_safe(llm_input),
                                llm_decision=_json_safe(decision),
                                reasoning_summary=decision["reasoning_summary"],
                                mcp_tool="get_state",
                                mcp_input={},
                                mcp_output=_json_safe(mcp_call["output"]),
                                mcp_stop_reason=_mcp_action_summary(mcp_call).get("stop_reason"),
                                decision_source="terminal_state",
                            )
                        )
                        sequence_number += 1
                        latest_event = await collector.collect(
                            run_id_val,
                            tick,
                            state,
                            llm_input,
                            decision,
                            mcp_call,
                            agent_decision_id=decision_row.id,
                        )
                        await decision_repo.update(decision_row, game_event_id=latest_event.id)
                        await _broadcast_state(run_id_val, latest_event, decision)
                        await db.commit()
                        if latest_event.event_type == "map_exit" or state.get("level_completed") or state.get("next_map"):
                            outcome = "map_completed"
                        elif latest_event.health <= 0 or state.get("dead"):
                            outcome = "player_died"
                        elif state.get("episode_timeout"):
                            outcome = "timeout"
                        break

                    await websocket_service.broadcast(
                        run_id_val,
                        {"type": "llm_start", "sequence_number": sequence_number, "tick": tick},
                    )
                    decision_row = await decision_repo.create(
                        AgentDecision(
                            run_id=run_id_val,
                            sequence_number=sequence_number,
                            tick_before=tick,
                            status="started",
                            llm_input_summary=_json_safe(llm_input),
                        )
                    )
                    sequence_number += 1

                    llm_started = time.monotonic()
                    # Generate map layout overlay with position trail for spatial awareness
                    map_layout_png = generate_map_layout_png(
                        map_overview_png_path,
                        lockstep_state.get("_position_trail_for_layout") or [],
                        float(llm_input.get("player", {}).get("position", {}).get("x") or 0),
                        float(llm_input.get("player", {}).get("position", {}).get("y") or 0),
                        map_bounds_for_layout,
                    )
                    # Track position for layout overlay
                    pos_x = float(llm_input.get("player", {}).get("position", {}).get("x") or 0)
                    pos_y = float(llm_input.get("player", {}).get("position", {}).get("y") or 0)
                    trail = lockstep_state.setdefault("_position_trail_for_layout", [])
                    if not trail or trail[-1] != (pos_x, pos_y):
                        trail.append((pos_x, pos_y))
                        if len(trail) > 200:
                            trail[:] = trail[-200:]
                    decision, token_usage = await gemini.decide(prompt, llm_input, screenshot_png=screenshot_png, map_layout_png=map_layout_png)
                    total_llm_calls += 1
                    llm_duration_ms = (time.monotonic() - llm_started) * 1000
                    cost_estimate_usd = round(
                        estimate_llm_cost_usd(
                            token_usage.get("prompt_tokens"),
                            token_usage.get("completion_tokens"),
                            input_cost_per_million=llm_input_cost_per_million,
                            output_cost_per_million=llm_output_cost_per_million,
                        ),
                        6,
                    )
                    raw_decision = dict(decision)
                    decision_source = str(decision.pop("_decision_source", "gemini"))
                    _merge_hypotheses(lockstep_state, raw_decision, state)
                    await decision_repo.update(
                        decision_row,
                        status="llm_complete",
                        llm_decision=_json_safe(decision),
                        raw_llm_decision=_json_safe(raw_decision),
                        reasoning_summary=decision.get("reasoning_summary"),
                        llm_duration_ms=llm_duration_ms,
                        llm_input_tokens=token_usage.get("prompt_tokens"),
                        llm_output_tokens=token_usage.get("completion_tokens"),
                        llm_cost_estimate_usd=cost_estimate_usd,
                        decision_source=decision_source,
                    )
                    await websocket_service.broadcast(
                        run_id_val,
                        {
                            "type": "llm_decision",
                            "sequence_number": decision_row.sequence_number,
                            "tick": tick,
                            "reasoning_summary": decision.get("reasoning_summary"),
                            "mcp_tool": decision.get("mcp_tool"),
                            "mcp_params": decision.get("mcp_params") or {},
                            "llm_duration_ms": round(llm_duration_ms, 1),
                            "llm_input": _json_safe(llm_input),
                            "llm_raw_output": _json_safe(raw_decision),
                            "visited_cells": dict(lockstep_state.get("visited_cells") or {}),
                            "visited_cell_size": CELL_SIZE,
                            "decision_source": decision_source,
                            "llm_input_tokens": token_usage.get("prompt_tokens"),
                            "llm_output_tokens": token_usage.get("completion_tokens"),
                            "llm_cost_estimate_usd": cost_estimate_usd,
                        },
                    )

                    await websocket_service.broadcast(
                        run_id_val,
                        {
                            "type": "mcp_call_start",
                            "sequence_number": decision_row.sequence_number,
                            "tick": tick,
                            "mcp_tool": decision.get("mcp_tool"),
                            "mcp_params": decision.get("mcp_params") or {},
                        },
                    )
                    decision.setdefault("mcp_params", {})
                    from app.services.run_constants import COMPOUND_TELEMETRY_TOOLS

                    # Check if guard is enabled
                    guard_enabled = runtime_value("guard_enabled", settings.guard_enabled)

                    # Get_state spam guard: after 2 consecutive get_state, force explore
                    get_state_count = lockstep_state.get("consecutive_get_state", 0)
                    if guard_enabled and get_state_count >= 2 and decision.get("mcp_tool") == "get_state":
                        _record_failure_critique(
                            lockstep_state, tick=tick, tool="get_state",
                            params={},
                            reason="Called get_state multiple times consecutively instead of taking action.",
                        )
                        decision["mcp_tool"] = "explore"
                        decision["mcp_params"] = {"max_tics": 80, "stop_on_enemy": False, "stop_on_item": True, "turn_before": 180.0}
                        decision["reasoning_summary"] = "OVERRIDE: Consecutive get_state detected. Forced explore with 180° turn to advance gameplay."
                        decision["_decision_source"] = "guard_get_state"

                    # Position stuck detection: override if agent hasn't moved in 2+ consecutive decisions
                    # Exclude combat tools — agent is actively fighting, not stuck
                    stuck_counter = lockstep_state.get("position_stuck_counter", 0)
                    combat_tools = {"aim_and_shoot", "strafe_and_shoot", "select_weapon"}
                    if guard_enabled and stuck_counter >= 2 and decision.get("mcp_tool") in ("explore", "move_to", "take_action"):
                        _record_failure_critique(
                            lockstep_state, tick=tick, tool=decision.get("mcp_tool", "unknown"),
                            params=decision.get("mcp_params", {}),
                            reason=f"Agent stuck for {stuck_counter} decisions without meaningful movement. Need different approach.",
                        )
                        # Alternate turn direction to avoid repeating the same wall
                        turn_amount = 180.0 if stuck_counter % 2 == 0 else -180.0
                        decision["mcp_tool"] = "explore"
                        decision["mcp_params"] = {"max_tics": 80, "stop_on_enemy": False, "stop_on_item": True, "turn_before": turn_amount}
                        decision["reasoning_summary"] = (
                            f"OVERRIDE: Agent stuck ({stuck_counter} decisions without meaningful movement). "
                            f"Your original plan: {decision.get('reasoning_summary', '?')}. "
                            f"Guard forced explore with {turn_amount}° turn to break fixation."
                        )
                        decision["_decision_source"] = "guard_stuck"

                    # Decision diversity check: if last 3 same-tool decisions had similar reasoning, break loop
                    # Skip during combat — don't interrupt active fights
                    diversity_counter = lockstep_state.get("decision_diversity_counter", 0)
                    if guard_enabled and diversity_counter >= 3 and decision.get("mcp_tool") in ("explore", "move_to", "take_action") and decision.get("mcp_tool") not in combat_tools:
                        _record_failure_critique(
                            lockstep_state, tick=tick, tool=decision.get("mcp_tool", "unknown"),
                            params=decision.get("mcp_params", {}),
                            reason=f"Decision loop: {diversity_counter} repeated {decision.get('mcp_tool')} calls. Must change strategy.",
                        )
                        decision["mcp_tool"] = "explore"
                        decision["mcp_params"] = {"max_tics": 80, "stop_on_enemy": False, "stop_on_item": False, "ignore_object_ids": [], "turn_before": 90.0}
                        decision["reasoning_summary"] = (
                            f"OVERRIDE: Decision loop detected ({diversity_counter} repeated decisions). "
                            f"Your original plan: {decision.get('reasoning_summary', '?')}. "
                            f"Guard forced diverse exploration with 90° turn to break cycle."
                        )
                        decision["_decision_source"] = "guard_diversity"

                    if (
                        decision.get("mcp_tool") in COMPOUND_TELEMETRY_TOOLS
                        and "telemetry_stride" not in decision["mcp_params"]
                    ):
                        decision["mcp_params"]["telemetry_stride"] = recording_telemetry_stride
                    if recording_telemetry_stride > 1:
                        decision["recording_fidelity_warning"] = (
                            f"Recording telemetry stride is {recording_telemetry_stride}; "
                            "video evidence may be sparse."
                        )
                    effective_decision_source = str(decision.pop("_decision_source", decision_source))
                    guard_modified = effective_decision_source.startswith("guard_")
                    guard_reason = effective_decision_source if guard_modified else None
                    mcp_started = time.monotonic()
                    response, mcp_call = await _execute_tool(mcp, decision, state)
                    mcp_duration_ms = (time.monotonic() - mcp_started) * 1000
                    total_actions += 1

                    result_state, result_screenshot_png = normalize_mcp_state(response)
                    telemetry_frames = _pop_telemetry_frames(result_state)
                    await _record_telemetry_frames(run_id_val, tick, telemetry_frames, collector, recorder)
                    frame = png_bytes_to_frame(result_screenshot_png)
                    if frame is None:
                        frame = png_bytes_to_frame(screenshot_png)
                    if not isinstance(result_state, dict) or "game_variables" not in result_state:
                        result_state = state
                    result_x, result_y, result_angle = _history_position_from_state(result_state)
                    result_tick = _factual_game_tic(result_state, lockstep_state)
                    if frame is not None:
                        last_record_frame = frame
                        recorder.write_frame(frame, game_tick=result_tick)
                    record_frame = frame if frame is not None else last_record_frame
                    _update_lockstep_after_action(decision, mcp_call, lockstep_state, result_state)
                    _track_visited_cell(result_state, lockstep_state)
                    _finalize_lockstep_decision(lockstep_state)

                    stop_reason = _mcp_action_summary(mcp_call).get("stop_reason")
                    tool = mcp_call.get("tool") or decision.get("mcp_tool") or "explore"

                    # Record failure critiques for actionable stop reasons
                    if stop_reason in ("target_lost", "target_not_visible"):
                        _record_failure_critique(
                            lockstep_state, tick=result_tick, tool=tool,
                            params=decision.get("mcp_params", {}),
                            reason=f"Target {stop_reason}: enemy is behind cover or no longer visible. Must reposition for line of sight.",
                        )
                    elif stop_reason == "out_of_ammo":
                        _record_failure_critique(
                            lockstep_state, tick=result_tick, tool=tool,
                            params=decision.get("mcp_params", {}),
                            reason="Out of ammo for current weapon. Need to find ammo or switch to melee/unlimited ammo weapon.",
                        )
                    elif stop_reason == "no_usable_weapon":
                        _record_failure_critique(
                            lockstep_state, tick=result_tick, tool=tool,
                            params=decision.get("mcp_params", {}),
                            reason="No usable weapon available. Must retreat and find weapons/ammo.",
                        )

                    self_x = float(state.get("game_variables", {}).get("POSITION_X", 0))
                    self_y = float(state.get("game_variables", {}).get("POSITION_Y", 0))
                    dx = abs(result_x - self_x)
                    dy = abs(result_y - self_y)
                    movement = math.sqrt(dx * dx + dy * dy)
                    # Combat tools don't involve movement — don't count them as stuck
                    no_stuck_tools = {"select_weapon", "get_threat_assessment", "get_navigation_info", "aim_and_shoot", "strafe_and_shoot"}
                    if movement < 15 and tool not in no_stuck_tools:
                        lockstep_state["position_stuck_counter"] = lockstep_state.get("position_stuck_counter", 0) + 1
                    else:
                        lockstep_state["position_stuck_counter"] = 0

                    # Circling detection: if agent keeps returning to the same area
                    if tool not in no_stuck_tools:
                        recent_positions = lockstep_state.setdefault("_recent_positions", [])
                        recent_positions.append((result_x, result_y))
                        if len(recent_positions) > 12:
                            recent_positions[:] = recent_positions[-12:]
                        if len(recent_positions) >= 6:
                            xs = [p[0] for p in recent_positions]
                            ys = [p[1] for p in recent_positions]
                            x_range = max(xs) - min(xs)
                            y_range = max(ys) - min(ys)
                            if x_range < 200 and y_range < 200:
                                lockstep_state["position_stuck_counter"] = lockstep_state.get("position_stuck_counter", 0) + 2

                    if tool == "get_state":
                        lockstep_state["consecutive_get_state"] = lockstep_state.get("consecutive_get_state", 0) + 1
                    else:
                        lockstep_state["consecutive_get_state"] = 0

                    prev_decisions = list(lockstep_state.get("decision_history") or [])
                    last_three = [d.get("tool") for d in prev_decisions[-3:] if d.get("tool")]
                    if len(last_three) >= 3 and len(set(last_three)) == 1:
                        lockstep_state["decision_diversity_counter"] = lockstep_state.get("decision_diversity_counter", 0) + 1
                    else:
                        lockstep_state["decision_diversity_counter"] = 0

                    _record_decision_in_history(
                        lockstep_state,
                        seq=decision_row.sequence_number,
                        tick_before=tick,
                        tick_after=result_tick,
                        tool=tool,
                        stop_reason=stop_reason,
                        params=decision.get("mcp_params") or {},
                        reasoning=decision.get("reasoning_summary"),
                        guard_modified=guard_modified,
                        llm_duration_ms=llm_duration_ms,
                        mcp_duration_ms=mcp_duration_ms,
                        total_budget=max_ticks,
                        action_summary=_mcp_action_summary(mcp_call),
                        state_before=state,
                        state_after=result_state,
                        decision_source=effective_decision_source,
                        observed_issue=decision.get("observed_issue"),
                    )
                    if sequence_number % 3 == 0:
                        _record_position_in_trail(
                            lockstep_state, result_tick,
                            result_x,
                            result_y,
                            result_angle,
                        )
                    summary_d = _mcp_action_summary(mcp_call)
                    if tool in ("aim_and_shoot", "strafe_and_shoot"):
                        damage_before = float(state.get("game_variables", {}).get("DAMAGECOUNT", 0))
                        damage_after = float(result_state.get("game_variables", {}).get("DAMAGECOUNT", 0))
                        damage_delta = max(0, damage_after - damage_before)
                        _update_combat_log(
                            lockstep_state,
                            object_id=decision.get("mcp_params", {}).get("object_id"),
                            weapon=str(summary_d.get("weapon_used", "unknown")),
                            shots=int(summary_d.get("shots_fired", 0)),
                            hits=int(summary_d.get("hits_landed", 0)),
                            killed=(stop_reason == "target_killed" or int(summary_d.get("kills", 0)) > 0),
                            distance=float(summary_d.get("target_distance", 0)),
                            damage_dealt=damage_delta,
                        )
                    if stop_reason in ("target_killed", "item_found", "key_found", "secret_found", "map_exit", "player_died"):
                        _record_checkpoint(
                            lockstep_state, result_tick,
                            result_x,
                            result_y,
                            f"{stop_reason}: {summary_d.get('target_name', '')}" if summary_d else stop_reason or "",
                        )
                    _update_objective_history(lockstep_state, decision.get("reasoning_summary"))

                    latest_event = await collector.collect(
                        run_id_val,
                        result_tick,
                        result_state,
                        llm_input,
                        decision,
                        mcp_call,
                        agent_decision_id=decision_row.id,
                    )
                    _record_event_in_history(
                        lockstep_state,
                        result_tick,
                        latest_event.event_type,
                        result_x,
                        result_y,
                        detail=stop_reason or tool,
                    )
                    summary = _mcp_action_summary(mcp_call)
                    await decision_repo.update(
                        decision_row,
                        status="complete",
                        llm_decision=_json_safe(decision),
                        raw_llm_decision=_json_safe(raw_decision),
                        tick_after=result_tick,
                        game_event_id=latest_event.id,
                        mcp_tool=mcp_call.get("tool") or decision.get("mcp_tool"),
                        mcp_input=_json_safe(mcp_call.get("input") or {}),
                        mcp_output=_json_safe(mcp_call.get("output") or {}),
                        mcp_stop_reason=str(summary.get("stop_reason")) if summary.get("stop_reason") is not None else None,
                        guard_modified=guard_modified,
                        guard_reason=guard_reason,
                        decision_source=effective_decision_source,
                        mcp_duration_ms=mcp_duration_ms,
                    )
                    await websocket_service.broadcast(
                        run_id_val,
                        {
                            "type": "mcp_call_result",
                            "sequence_number": decision_row.sequence_number,
                            "tick": result_tick,
                            "mcp_tool": mcp_call.get("tool") or decision.get("mcp_tool"),
                            "mcp_stop_reason": summary.get("stop_reason"),
                            "mcp_input": _json_safe(mcp_call.get("input") or {}),
                            "mcp_output": _json_safe(mcp_call.get("output") or {}),
                            "mcp_duration_ms": round(mcp_duration_ms, 1),
                            "decision_source": effective_decision_source,
                            "guard_modified": guard_modified,
                            "guard_reason": guard_reason,
                            "validation_rejection": summary.get("validation_error"),
                        },
                    )
                    progress_payload = _lockstep_progress_metrics(lockstep_state)
                    history_snapshot = _build_same_run_memory(lockstep_state)
                    await websocket_service.broadcast(
                        run_id_val,
                        {
                            "type": "progress",
                            "tick": result_tick,
                            **progress_payload,
                            "same_run_memory": history_snapshot,
                        },
                    )
                    event_screenshot_b64 = None
                    if (
                        latest_event.event_type in {"kill", "death", "damage_taken", "stuck"}
                        or decision.get("observed_issue")
                    ) and record_frame is not None:
                        screenshot_path = recorder.save_screenshot(record_frame, latest_event.id)
                        await collector.attach_screenshot(run_id_val, latest_event, str(screenshot_path))
                        event_screenshot_b64 = jpeg_b64(record_frame)
                    await _broadcast_state(run_id_val, latest_event, decision, event_screenshot_b64)
                    now = time.monotonic()
                    if record_frame is not None and now - last_frame_at >= 1 / live_frame_fps:
                        encoded = jpeg_b64(record_frame)
                        if encoded:
                            await websocket_service.broadcast(
                                run_id_val,
                                {"type": "frame", "tick": result_tick, "mime_type": "image/jpeg", "frame_b64": encoded},
                            )
                        last_frame_at = now
                    await db.commit()
                # Session released, connection returned to pool

                if latest_event.event_type == "map_exit" or result_state.get("level_completed") or result_state.get("next_map"):
                    outcome = "map_completed"
                    break
                if latest_event.health <= 0 or result_state.get("dead"):
                    outcome = "player_died"
                    break
                if tool == "finish":
                    outcome = _normalize_run_outcome(str(summary_d.get("outcome", "qa_completed")))
                    break
                if _lockstep_should_stop_as_stuck(lockstep_state):
                    outcome = _lockstep_stop_outcome(lockstep_state)
                    break
                if result_state.get("episode_finished") or result_state.get("episode_timeout"):
                    outcome = "timeout"
                    break
                if result_tick >= max_ticks:
                    outcome = "timeout"
                    break

                raw_state = state if isinstance(state, dict) else result_state
                profile_throttle = {
                    "combat": profile.throttle_delays.get("combat", 0.5),
                    "low_health": profile.throttle_delays.get("low_health", 1.0),
                    "stuck": profile.throttle_delays.get("stuck", 2.0),
                    "default": profile.throttle_delays.get("default", 1.5),
                }
                throttle_seconds = _compute_dynamic_throttle(raw_state, lockstep_state, throttle_delays=profile_throttle)
                if llm_throttle_cap_seconds <= 0:
                    throttle_seconds = 0
                else:
                    throttle_seconds = min(throttle_seconds, llm_throttle_cap_seconds)
                if throttle_seconds:
                    await websocket_service.broadcast(
                        run_id_val,
                        {
                            "type": "status",
                            "status": "running",
                            "phase": "lockstep_throttle",
                            "message": f"Game is paused in PLAYER mode for {throttle_seconds:g}s before the next LLM decision.",
                            "sleep_seconds": throttle_seconds,
                            "tick": result_tick,
                        },
                    )
                    await asyncio.sleep(throttle_seconds)
    except asyncio.CancelledError:
        outcome = "cancelled"
        async with SessionLocal() as db:
            run_orm = await db.get(TestRun, run_id_val)
            if run_orm is not None:
                await RunRepository(db).update(run_orm, status="cancelled")
                await db.commit()
    except Exception as exc:
        exc_msg = str(exc)
        if isinstance(exc, McpStartupError):
            outcome, failure_fields = _classify_startup_failure(exc)
        elif isinstance(exc, McpToolTimeoutError):
            if any(kw in exc_msg.lower() for kw in ("wad", "map", "crash", "pwad")):
                failure_fields = _pwad_crash_fields(exc, "gameplay")
                outcome = "pwad_crash"
            else:
                failure_fields = _infrastructure_failure_fields(exc, "mcp_tool_timeout")
                outcome = "error"
        else:
            if any(kw in exc_msg.lower() for kw in ("wad", "map", "lump", "texture", "crash", "pwad", "init")):
                failure_fields = _pwad_crash_fields(exc, "wad_loading")
                outcome = "pwad_crash"
            else:
                failure_fields = _infrastructure_failure_fields(exc, runtime_stage)
                outcome = "error"
        async with SessionLocal() as db:
            run_orm = await db.get(TestRun, run_id_val)
            if run_orm is not None:
                await RunRepository(db).update(run_orm, status="failed", outcome=outcome, error_message=str(exc), **failure_fields)
                await db.commit()
    finally:
        if mcp_client is not None:
            await mcp_client.stop_game()
        outcome = _normalize_run_outcome(outcome)
        recording_path = recorder.finalize()
        recording_metadata = recorder.validate(recording_path, outcome=outcome)
        progress_metrics = _lockstep_progress_metrics(lockstep_state)
        agent_quality_flags = _lockstep_quality_flags(lockstep_state, recording_metadata)
        completed_at = datetime.now(UTC)
        final_fields: dict[str, Any] = {
            "outcome": outcome,
            "completed_at": completed_at,
            "total_actions_taken": total_actions,
            "total_llm_calls": total_llm_calls,
            "recording_metadata": _json_safe(recording_metadata),
            "progress_metrics": _json_safe(progress_metrics),
            "agent_quality_flags": _json_safe(agent_quality_flags),
        }
        final_fields.update(failure_fields)
        if recording_path:
            final_fields["recording_mp4_path"] = str(recording_path)
        elif recorder.path.exists():
            final_fields["recording_mp4_path"] = str(recorder.path)
        if latest_event is not None:
            final_fields.update(
                {
                    "final_hp": latest_event.health,
                    "final_armor": latest_event.armor,
                    "total_kills": latest_event.kill_count,
                    "secrets_found": latest_event.secret_count,
                    "total_items_collected": (latest_event.item_count or 0) + sum(
                        1
                        for value in (lockstep_state.get("completed_object_ids") or {}).values()
                        if isinstance(value, dict) and value.get("target_type") == "weapon"
                    ),
                }
            )

        async with SessionLocal() as db:
            run_orm = await db.get(TestRun, run_id_val)
            if run_orm is None:
                RUN_TASKS.pop(run_id_val, None)
                return
            run_repo = RunRepository(db)
            run_started_at = run_orm.started_at
            if run_orm.status not in {"failed", "cancelled"}:
                final_fields["status"] = "completed"
            if run_started_at:
                final_fields["duration_seconds"] = int((completed_at - run_started_at).total_seconds())
            await run_repo.update(run_orm, **final_fields)
            await db.commit()
            await websocket_service.broadcast(
                run_id_val,
                {"type": "recording_status", "metadata": _json_safe(recording_metadata)},
            )
            await websocket_service.broadcast(
                run_id_val,
                {
                    "type": "quality_summary",
                    "progress_metrics": _json_safe(progress_metrics),
                    "agent_quality_flags": _json_safe(agent_quality_flags),
                },
            )
            if run_orm.status in {"completed", "cancelled", "failed"}:
                try:
                    await DefectService(db, gemini_service=gemini).detect_for_run(run_orm)
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.warning("Defect detection failed for run %s: %s", run_id_val, exc)
                for defect in await DefectRepository(db).list_by_run(run_id_val):
                    await websocket_service.broadcast(
                        run_id_val,
                        {
                            "type": "defect",
                            "defect_type": defect.defect_type,
                            "fingerprint": defect.fingerprint,
                            "title": defect.title,
                            "severity": defect.severity,
                            "detected_at_tick": defect.detected_at_tick,
                        },
                    )
                try:
                    events_result = await db.execute(select(GameEvent).where(GameEvent.run_id == run_id_val))
                    run_events = list(events_result.scalars().all())
                    defects_result = await db.execute(select(Defect).where(Defect.run_id == run_id_val))
                    run_defects = list(defects_result.scalars().all())
                    memory_svc = RunMemoryService(db)
                    await memory_svc.persist_spatial_memory(
                        run_id=run_id_val,
                        wad_file_id=wad_file_id,
                        map_name=map_name_val,
                        events=run_events,
                        defects=run_defects,
                    )
                    hyp_list = list(lockstep_state.get("hypotheses") or [])
                    await memory_svc.persist_hypotheses(
                        run_id=run_id_val,
                        wad_file_id=wad_file_id,
                        map_name=map_name_val,
                        in_run_hypotheses=hyp_list,
                        agent_quality_flags=agent_quality_flags,
                    )
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.warning("Reviewer analytics persistence failed for run %s: %s", run_id_val, exc)
                try:
                    await websocket_service.broadcast(run_id_val, {"type": "report_status", "status": "generating"})
                    await ReportService(db).generate(run_id_val)
                    await db.commit()
                    await websocket_service.broadcast(run_id_val, {"type": "report_status", "status": "complete"})
                except Exception as exc:
                    await db.rollback()
                    await ReportService(db).mark_error(run_id_val, str(exc))
                    await db.commit()
                    await websocket_service.broadcast(
                        run_id_val,
                        {"type": "report_status", "status": "error", "error": str(exc)},
                    )
                    refreshed_run = await db.get(TestRun, run_id_val)
                    if refreshed_run is not None:
                        await RunRepository(db).update(
                            refreshed_run,
                            error_message=(refreshed_run.error_message or f"Report generation failed: {exc}"),
                        )
                        await db.commit()
            await websocket_service.broadcast(run_id_val, {"type": "state", "status": run_orm.status, "tick": max_ticks})
            RUN_TASKS.pop(run_id_val, None)
            await websocket_service.cleanup_run(run_id_val)


def _situation_finished(situation: dict[str, Any]) -> bool:
    return bool(
        situation.get("episode_finished")
        or situation.get("episode_timeout")
        or situation.get("level_completed")
        or situation.get("next_map")
        or situation.get("dead")
    )


def _normalize_run_outcome(outcome: str | None) -> str:
    value = str(outcome or "timeout").strip().lower()
    aliases = {
        "completed": "qa_completed",
        "complete": "qa_completed",
        "qa_complete": "qa_completed",
        "agent_died": "player_died",
        "death": "player_died",
        "died": "player_died",
        "softlock": "inconclusive_agent_stall",
        "stuck": "inconclusive_agent_stall",
        "agent_stall": "inconclusive_agent_stall",
    }
    return aliases.get(value, value)


async def _safe_context_tool(mcp: McpDoomClient, tool_name: str) -> dict[str, Any]:
    try:
        result = await mcp.call_tool(tool_name, {})
        state, _ = normalize_mcp_state(result)
        return _json_safe(state) if isinstance(state, dict) else {"result": _summary(result)}
    except Exception as exc:
        return {"error": str(exc), "tool": tool_name}


def _classify_startup_failure(exc: McpStartupError) -> tuple[str, dict[str, Any]]:
    exc_msg = str(exc)
    if "PWAD_CRASH:" in exc_msg:
        return "pwad_crash", _pwad_crash_fields(exc, "wad_loading")
    return "error", _infrastructure_failure_fields(exc, "mcp_connect_retry_exhausted")


def _history_position_from_state(state: dict[str, Any]) -> tuple[float, float, int]:
    variables = normalize_variables(state)
    return (
        float(variables.get("x", 0) or 0),
        float(variables.get("y", 0) or 0),
        int(variables.get("angle", 0) or 0),
    )


async def _execute_tool(
    mcp: McpDoomClient,
    decision: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    from app.services.run_constants import (
        COMPOUND_TELEMETRY_TOOLS,
        EXPLORE_MAX_TICS_UPPER,
        OBJECT_ID_TOOLS,
        TOOL_PARAM_ALLOWLIST,
    )

    tool = str(decision.get("mcp_tool") or "")
    raw_params = decision.get("mcp_params")
    raw_params = dict(raw_params) if isinstance(raw_params, dict) else {}
    params = _normalize_mcp_params(tool, dict(raw_params))
    validation_error = _validate_tool_request(tool, params, raw_params, TOOL_PARAM_ALLOWLIST, OBJECT_ID_TOOLS)
    if validation_error:
        decision["mcp_tool"] = tool
        decision["mcp_params"] = params
        output = {
            **(state or {}),
            "action_summary": {
                "stop_reason": "invalid_params",
                "validation_error": validation_error,
                "lockstep_control": True,
            },
        }
        return output, {
            "service": "backend-validation",
            "tool": tool or "invalid_tool",
            "input": _json_safe(params),
            "output": _json_safe(output),
        }
    if tool == "explore":
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=EXPLORE_MAX_TICS_UPPER, lower=20, upper=EXPLORE_MAX_TICS_UPPER)
        params.setdefault("stop_on_enemy", True)
        params.setdefault("stop_on_item", True)
    elif tool in {"aim_and_shoot", "strafe_and_shoot"}:
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=90, lower=10, upper=120)
    elif tool == "move_to":
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=140, lower=20, upper=180)
    elif tool == "retreat":
        params["tics"] = _bounded_int(params.get("tics"), default=35, lower=8, upper=70)
    if tool in COMPOUND_TELEMETRY_TOOLS:
        params.setdefault("capture_telemetry", True)
        params.setdefault("telemetry_stride", max(1, get_settings().recording_telemetry_stride))
    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    call_tool_name = tool
    call_params = dict(params)
    if tool == "step":
        call_tool_name = "take_action"
    if tool == "take_action" and "actions" not in params:
        call_params = {"actions": params, "tics": 4}
    response = await mcp.call_tool(call_tool_name, call_params)
    output = _compact_mcp_output(response)
    if call_tool_name == "take_action" and isinstance(output, dict) and "action_summary" not in output:
        output["action_summary"] = {
            "stop_reason": "tics_complete",
            "tics": call_params.get("tics"),
            "actions": call_params.get("actions") or {},
            "lockstep_control": True,
        }
    return response, {
        "service": "mcp-doom",
        "tool": call_tool_name,
        "input": _json_safe(call_params),
        "output": _json_safe(output),
    }


def _validate_tool_request(
    tool: str,
    params: dict[str, Any],
    raw_params: dict[str, Any],
    allowlist: dict[str, set[str]],
    object_id_tools: set[str],
) -> str | None:
    valid_tools = set(allowlist) | {"take_action"}
    if tool not in valid_tools:
        return f"Unsupported MCP tool: {tool or '<missing>'}"
    if tool in object_id_tools and not isinstance(params.get("object_id"), int):
        return f"{tool} requires an integer object_id"
    if tool == "select_weapon" and "weapon_slot" not in raw_params:
        return "select_weapon requires weapon_slot"
    if tool == "take_action":
        actions = params.get("actions")
        if not isinstance(actions, dict) or not actions:
            return "take_action requires at least one allowed action button"
    return None



def _estimate_total_map_cells(analysis: Any) -> int | None:
    width = getattr(analysis, "map_width_units", None)
    height = getattr(analysis, "map_height_units", None)
    try:
        parsed_width = float(width)
        parsed_height = float(height)
    except (TypeError, ValueError):
        return None
    if parsed_width <= 0 or parsed_height <= 0:
        return None
    return max(1, math.ceil(parsed_width / CELL_SIZE) * math.ceil(parsed_height / CELL_SIZE))
