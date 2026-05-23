from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.types import LockstepState
from app.models import AgentDecision, GameEvent, TestRun
from app.repositories.agent_decision_repository import AgentDecisionRepository
from app.repositories.defect_repository import DefectRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.services.collector_service import CollectorService
from app.services.defect_service import DefectService
from app.services.gemini_service import GeminiService, get_last_token_usage
from app.services.mcp_client_service import McpDoomClient, McpStartupError, McpToolTimeoutError, normalize_mcp_state
from app.services.prompt_service import render_agent_prompt
from app.services.recording_service import RecordingService, jpeg_b64, png_bytes_to_frame
from app.services.report_service import ReportService
from app.services.run_constants import RUN_TASKS
from app.services.run_guards import (
    _apply_lockstep_recovery,
    _combat_target_is_visible,
    _guard_lockstep_decision,
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
    _write_realtime_frame,
)
from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _compact_mcp_output,
    _compact_state_for_llm,
    _compute_dynamic_stride,
    _compute_dynamic_throttle,
    _finalize_lockstep_decision,
    _infrastructure_failure_fields,
    _initial_lockstep_state,
    _json_safe,
    _lockstep_state_snapshot,
    _merge_hypotheses,
    _mcp_action_summary,
    _normalize_mcp_params,
    _normalize_take_action_params,
    _pwad_crash_fields,
    _state_report_call,
    _structured_memory_snapshot,
    _summary,
    _track_explored_sectors,
    _track_visited_cell,
    _unique_lockstep_tick,
    get_behavior_profile,
)
from app.services.websocket_service import websocket_service


async def agent_run_task(run_id: UUID) -> None:
    async with SessionLocal() as db:
        run = await db.get(TestRun, run_id)
        if run is None:
            return
        wad = await WadRepository(db).get_by_id(run.wad_file_id)
        from app.models import StaticAnalysisResult

        analysis = await db.get(StaticAnalysisResult, run.static_analysis_id) if run.static_analysis_id else None
        run_repo = RunRepository(db)
        if wad is None or analysis is None:
            await run_repo.update(
                run,
                status="failed",
                outcome="error",
                error_message="Run is missing WAD or static analysis",
            )
            await db.commit()
            return
        cross_run_memory = await RunMemoryService(db).build_cross_run_memory(
            run.wad_file_id,
            run.map_name,
            current_run_id=run.id,
        )
        profile = get_behavior_profile(run)
        prompt = (
            render_agent_prompt(wad, analysis, run, cross_run_memory=cross_run_memory["prompt"])
            + "\n\n"
            + profile.system_prompt_addendum
        )
        collector = CollectorService(db)
        recorder = RecordingService(str(run.id), fps=max(15.0, get_settings().recording_fps))
        gemini = GeminiService()
        total_actions = 0
        total_llm_calls = 0
        last_frame_at = 0.0
        outcome = "timeout"
        latest_event = None
        mcp_client: McpDoomClient | None = None
        runtime_stage = "startup"
        failure_fields: dict[str, Any] = {}
        last_record_frame: Any = None
        lockstep_state: LockstepState = _initial_lockstep_state()

        try:
            async with McpDoomClient() as mcp:
                mcp_client = mcp
                await mcp.start_game(
                    wad=run.iwad_used,
                    scenario_wad=wad.stored_path,
                    map_name=run.map_name,
                    difficulty=run.difficulty_level,
                    episode_timeout=run.max_ticks,
                    async_player=False,
                )
                await run_repo.update(run, status="running", started_at=datetime.now(UTC))
                await db.commit()
                runtime_stage = "gameplay"
                decision_repo = AgentDecisionRepository(db)
                sequence_number = 0

                while True:
                    state, screenshot_png = await mcp.get_state()
                    tick = _unique_lockstep_tick(state, lockstep_state)
                    _track_visited_cell(state, lockstep_state)
                    frame = png_bytes_to_frame(screenshot_png)
                    if frame is not None:
                        last_record_frame = frame
                        recorder.write_frame(frame, game_tick=tick)
                    recent = await _recent_trace(db, run.id)
                    threat_assessment = await _safe_context_tool(mcp, "get_threat_assessment")
                    navigation_info = await _safe_context_tool(mcp, "get_navigation_info")
                    _track_explored_sectors(state, navigation_info, lockstep_state)
                    visited_count = len(lockstep_state.get("visited_cells") or {})
                    ticks_remaining = max(0, run.max_ticks - tick)
                    total_cells = lockstep_state.get("total_map_cells_estimate", 225) or 225
                    coverage_percent = round(visited_count / max(total_cells, 1) * 100, 1)
                    coverage_warning = None
                    if coverage_percent < 20 and ticks_remaining < run.max_ticks * 0.5:
                        coverage_warning = (
                            f"WARNING: Coverage is {coverage_percent}% with {ticks_remaining} ticks remaining. "
                            "Prioritize exploration over combat immediately."
                        )
                    llm_input = {
                        "tick": tick,
                        "ticks_remaining": ticks_remaining,
                        **_compact_state_for_llm(state),
                        "threat_assessment": threat_assessment,
                        "navigation_info": navigation_info,
                        "recent_trace": recent,
                        "structured_memory": _structured_memory_snapshot(lockstep_state),
                        "cross_run_memory": cross_run_memory,
                        "lockstep_state": _lockstep_state_snapshot(lockstep_state),
                        "exploration_coverage": {
                            "visited_cells_count": visited_count,
                            "coverage_percent": coverage_percent,
                            "coverage_warning": coverage_warning,
                        },
                    }

                    if _situation_finished(state):
                        decision = {
                            "reasoning_summary": "Runtime reported the episode finished; recording final situation.",
                            "mcp_tool": "get_state",
                            "mcp_params": {},
                        }
                        mcp_call = _state_report_call(state)
                        decision_row = await decision_repo.create(
                            AgentDecision(
                                run_id=run.id,
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
                            )
                        )
                        sequence_number += 1
                        latest_event = await collector.collect(
                            run.id,
                            tick,
                            state,
                            llm_input,
                            decision,
                            mcp_call,
                            agent_decision_id=decision_row.id,
                        )
                        await decision_repo.update(decision_row, game_event_id=latest_event.id)
                        await _broadcast_state(run, latest_event, decision)
                        await db.commit()
                        if latest_event.event_type == "map_exit" or state.get("level_completed") or state.get("next_map"):
                            outcome = "map_completed"
                        elif latest_event.health <= 0 or state.get("dead"):
                            outcome = "player_died"
                        elif state.get("episode_timeout"):
                            outcome = "timeout"
                        break

                    await websocket_service.broadcast(
                        run.id,
                        {"type": "llm_start", "sequence_number": sequence_number, "tick": tick},
                    )
                    decision_row = await decision_repo.create(
                        AgentDecision(
                            run_id=run.id,
                            sequence_number=sequence_number,
                            tick_before=tick,
                            status="started",
                            llm_input_summary=_json_safe(llm_input),
                        )
                    )
                    sequence_number += 1

                    llm_started = time.monotonic()
                    decision = await gemini.decide(prompt, llm_input, screenshot_png=screenshot_png)
                    total_llm_calls += 1
                    llm_duration_ms = (time.monotonic() - llm_started) * 1000
                    token_usage = get_last_token_usage()
                    raw_decision = dict(decision)
                    _merge_hypotheses(lockstep_state, raw_decision)
                    decision = _apply_lockstep_recovery(decision, state, navigation_info, lockstep_state)
                    decision = _guard_lockstep_decision(decision, state, lockstep_state, navigation_info)
                    guard_status = "kept"
                    if (
                        decision.get("mcp_tool") != raw_decision.get("mcp_tool")
                        or decision.get("mcp_params") != raw_decision.get("mcp_params")
                    ):
                        guard_status = "modified"
                    await decision_repo.update(
                        decision_row,
                        status="llm_complete",
                        llm_decision=_json_safe(decision),
                        reasoning_summary=decision.get("reasoning_summary"),
                        llm_duration_ms=llm_duration_ms,
                        llm_input_tokens=token_usage.get("prompt_tokens"),
                        llm_output_tokens=token_usage.get("completion_tokens"),
                        llm_cost_estimate_usd=round(token_usage.get("completion_tokens", 0) * 0.00000015 + token_usage.get("prompt_tokens", 0) * 0.000000075, 6),
                    )
                    await websocket_service.broadcast(
                        run.id,
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
                            "llm_input_tokens": token_usage.get("prompt_tokens"),
                            "llm_output_tokens": token_usage.get("completion_tokens"),
                            "llm_cost_estimate_usd": round(
                                token_usage.get("completion_tokens", 0) * 0.00000015
                                + token_usage.get("prompt_tokens", 0) * 0.000000075,
                                6,
                            ),
                        },
                    )

                    await websocket_service.broadcast(
                        run.id,
                        {
                            "type": "mcp_call_start",
                            "sequence_number": decision_row.sequence_number,
                            "tick": tick,
                            "mcp_tool": decision.get("mcp_tool"),
                            "mcp_params": decision.get("mcp_params") or {},
                        },
                    )
                    decision.setdefault("mcp_params", {})
                    if "telemetry_stride" not in decision["mcp_params"]:
                        decision["mcp_params"]["telemetry_stride"] = _compute_dynamic_stride(
                            state, lockstep_state,
                            default_stride=profile.default_stride,
                            combat_stride=profile.combat_stride,
                            stuck_stride=profile.stuck_stride,
                        )
                    mcp_started = time.monotonic()
                    response, mcp_call = await _execute_tool(mcp, decision, state)
                    mcp_duration_ms = (time.monotonic() - mcp_started) * 1000
                    total_actions += 1

                    result_state, result_screenshot_png = normalize_mcp_state(response)
                    telemetry_frames = _pop_telemetry_frames(result_state)
                    await _record_telemetry_frames(run.id, tick, telemetry_frames, collector, recorder)
                    frame = png_bytes_to_frame(result_screenshot_png)
                    if frame is None:
                        frame = png_bytes_to_frame(screenshot_png)
                    if not isinstance(result_state, dict) or "game_variables" not in result_state:
                        result_state = state
                    result_tick = _unique_lockstep_tick(result_state, lockstep_state)
                    if frame is not None:
                        last_record_frame = frame
                        recorder.write_frame(frame, game_tick=result_tick)
                    record_frame = frame if frame is not None else last_record_frame
                    _update_lockstep_after_action(decision, mcp_call, lockstep_state)
                    _track_visited_cell(result_state, lockstep_state)
                    _finalize_lockstep_decision(lockstep_state)

                    latest_event = await collector.collect(
                        run.id,
                        result_tick,
                        result_state,
                        llm_input,
                        decision,
                        mcp_call,
                        agent_decision_id=decision_row.id,
                    )
                    summary = _mcp_action_summary(mcp_call)
                    await decision_repo.update(
                        decision_row,
                        status="complete",
                        tick_after=result_tick,
                        game_event_id=latest_event.id,
                        mcp_tool=mcp_call.get("tool") or decision.get("mcp_tool"),
                        mcp_input=_json_safe(mcp_call.get("input") or {}),
                        mcp_output=_json_safe(mcp_call.get("output") or {}),
                        mcp_stop_reason=str(summary.get("stop_reason")) if summary.get("stop_reason") is not None else None,
                        mcp_duration_ms=mcp_duration_ms,
                    )
                    await websocket_service.broadcast(
                        run.id,
                        {
                            "type": "mcp_call_result",
                            "sequence_number": decision_row.sequence_number,
                            "tick": result_tick,
                            "mcp_tool": mcp_call.get("tool") or decision.get("mcp_tool"),
                            "mcp_stop_reason": summary.get("stop_reason"),
                            "mcp_output": _json_safe(mcp_call.get("output") or {}),
                            "mcp_duration_ms": round(mcp_duration_ms, 1),
                            "guard_status": guard_status,
                        },
                    )
                    progress_payload = _lockstep_progress_metrics(lockstep_state)
                    await websocket_service.broadcast(
                        run.id,
                        {"type": "progress", "tick": result_tick, **progress_payload},
                    )
                    event_screenshot_b64 = None
                    if latest_event.event_type in {"kill", "death", "damage_taken", "stuck"} and record_frame is not None:
                        screenshot_path = recorder.save_screenshot(record_frame, latest_event.id)
                        await collector.attach_screenshot(run.id, latest_event, str(screenshot_path))
                        event_screenshot_b64 = jpeg_b64(record_frame)
                    await _broadcast_state(run, latest_event, decision, event_screenshot_b64)
                    now = time.monotonic()
                    if record_frame is not None and now - last_frame_at >= 1 / max(get_settings().live_frame_fps, 0.1):
                        encoded = jpeg_b64(record_frame)
                        if encoded:
                            await websocket_service.broadcast(
                                run.id,
                                {"type": "frame", "tick": result_tick, "mime_type": "image/jpeg", "frame_b64": encoded},
                            )
                        last_frame_at = now
                    await db.commit()

                    if latest_event.event_type == "map_exit" or result_state.get("level_completed") or result_state.get("next_map"):
                        outcome = "map_completed"
                        break
                    if latest_event.health <= 0 or result_state.get("dead"):
                        outcome = "player_died"
                        break
                    if _lockstep_should_stop_as_stuck(lockstep_state):
                        outcome = _lockstep_stop_outcome(lockstep_state)
                        break
                    if result_state.get("episode_finished") or result_state.get("episode_timeout"):
                        outcome = "timeout"
                        break
                    if result_tick >= run.max_ticks:
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
                    if throttle_seconds:
                        await websocket_service.broadcast(
                            run.id,
                            {
                                "type": "status",
                                "status": run.status,
                                "phase": "lockstep_throttle",
                                "message": f"Game is paused in PLAYER mode for {throttle_seconds:g}s before the next LLM decision.",
                                "sleep_seconds": throttle_seconds,
                                "tick": result_tick,
                            },
                        )
                        await asyncio.sleep(throttle_seconds)
        except asyncio.CancelledError:
            outcome = "cancelled"
            await run_repo.update(run, status="cancelled")
        except Exception as exc:
            if isinstance(exc, McpStartupError):
                failure_fields = _infrastructure_failure_fields(exc, "mcp_connect_retry_exhausted")
                outcome = "error"
            elif isinstance(exc, McpToolTimeoutError):
                failure_fields = _infrastructure_failure_fields(exc, "mcp_tool_timeout")
                outcome = "error"
            else:
                failure_fields = _pwad_crash_fields(exc, runtime_stage)
                outcome = "pwad_crash"
            await run_repo.update(run, status="failed", outcome=outcome, error_message=str(exc), **failure_fields)
        finally:
            if mcp_client is not None:
                await mcp_client.stop_game()
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
            if run.status not in {"failed", "cancelled"}:
                final_fields["status"] = "completed"
            if run.started_at:
                final_fields["duration_seconds"] = int((completed_at - run.started_at).total_seconds())
            if latest_event is not None:
                final_fields.update(
                    {
                        "final_hp": latest_event.health,
                        "final_armor": latest_event.armor,
                        "total_kills": latest_event.kill_count,
                        "secrets_found": latest_event.secret_count,
                        "total_items_collected": latest_event.item_count,
                    }
                )
            await run_repo.update(run, **final_fields)
            await db.commit()
            await websocket_service.broadcast(
                run.id,
                {"type": "recording_status", "metadata": _json_safe(recording_metadata)},
            )
            await websocket_service.broadcast(
                run.id,
                {
                    "type": "quality_summary",
                    "progress_metrics": _json_safe(progress_metrics),
                    "agent_quality_flags": _json_safe(agent_quality_flags),
                },
            )
            if run.status in {"completed", "cancelled", "failed"}:
                await DefectService(db).detect_for_run(run)
                await db.commit()
                for defect in await DefectRepository(db).list_by_run(run.id):
                    await websocket_service.broadcast(
                        run.id,
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
                    await websocket_service.broadcast(run.id, {"type": "report_status", "status": "generating"})
                    await ReportService(db).generate(run.id)
                    await db.commit()
                    await websocket_service.broadcast(run.id, {"type": "report_status", "status": "complete"})
                except Exception as exc:
                    await db.rollback()
                    await websocket_service.broadcast(
                        run.id,
                        {"type": "report_status", "status": "error", "error": str(exc)},
                    )
                    refreshed_run = await db.get(TestRun, run.id)
                    if refreshed_run is not None:
                        await run_repo.update(
                            refreshed_run,
                            error_message=(refreshed_run.error_message or f"Report generation failed: {exc}"),
                        )
                        await db.commit()
            await websocket_service.broadcast(run.id, {"type": "state", "status": run.status, "tick": run.max_ticks})
            RUN_TASKS.pop(run.id, None)
            await websocket_service.cleanup_run(run.id)


def _situation_finished(situation: dict[str, Any]) -> bool:
    return bool(
        situation.get("episode_finished")
        or situation.get("episode_timeout")
        or situation.get("level_completed")
        or situation.get("next_map")
        or situation.get("dead")
    )


async def _safe_context_tool(mcp: McpDoomClient, tool_name: str) -> dict[str, Any]:
    try:
        result = await mcp.call_tool(tool_name, {})
        state, _ = normalize_mcp_state(result)
        return _json_safe(state) if isinstance(state, dict) else {"result": _summary(result)}
    except Exception as exc:
        return {"error": str(exc), "tool": tool_name}


async def _execute_tool(
    mcp: McpDoomClient,
    decision: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    from app.services.run_constants import (
        COMBAT_TOOLS,
        COMPOUND_TELEMETRY_TOOLS,
        EXPLORE_MAX_TICS_UPPER,
        OBJECT_ID_TOOLS,
    )

    tool = decision.get("mcp_tool") or "explore"
    params = _normalize_mcp_params(tool, dict(decision.get("mcp_params") or {}))
    if tool in OBJECT_ID_TOOLS and "object_id" not in params:
        decision["tool_param_warning"] = f"{tool} requested without an object_id; fallback explore used."
        tool = "explore"
        params = {}
    if tool in COMBAT_TOOLS and not _combat_target_is_visible(state, params.get("object_id")):
        decision["tool_param_warning"] = (
            f"{tool} target {params.get('object_id')} is not a visible monster in the current state; "
            "fallback explore used."
        )
        tool = "explore"
        params = {}
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


async def _recent_trace(db: AsyncSession, run_id: UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        select(GameEvent).where(GameEvent.run_id == run_id).order_by(GameEvent.tick_number.desc()).limit(20)
    )
    all_events = list(reversed(result.scalars().all()))
    meaningful = [
        event
        for event in all_events
        if event.llm_reasoning
        and not event.llm_reasoning.startswith("Rate limited")
        and "RESOURCE_EXHAUSTED" not in event.llm_reasoning
        and "429" not in event.llm_reasoning
    ][-5:]
    return [
        {"tick": event.tick_number, "event_type": event.event_type, "reasoning": event.llm_reasoning}
        for event in meaningful
    ]
