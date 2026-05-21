from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import AgentDecision, GameEvent, StaticAnalysisResult, TestRun
from app.repositories.agent_decision_repository import AgentDecisionRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.defect_repository import DefectRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.serializers.run_serializers import RunCreate
from app.services.analysis_service import AnalysisService, player_start_counts, selected_skill_spawn_summary
from app.services.collector_service import CollectorService, normalize_variables
from app.services.defect_service import DefectService
from app.services.gemini_service import GeminiService
from app.services.mcp_client_service import McpDoomClient, normalize_mcp_state
from app.services.prompt_service import render_agent_prompt
from app.services.recording_service import RecordingService, jpeg_b64, png_bytes_to_frame
from app.services.report_service import ReportService
from app.services.websocket_service import websocket_service


RUN_TASKS: dict[UUID, asyncio.Task] = {}
COMPOUND_TELEMETRY_TOOLS = {"explore", "move_to", "aim_and_shoot", "strafe_and_shoot", "retreat", "take_action"}
OBJECT_ID_TOOLS = {"aim_and_shoot", "strafe_and_shoot", "move_to"}
COMBAT_TOOLS = {"aim_and_shoot", "strafe_and_shoot"}
STUCK_RUN_ABORT_THRESHOLD = 5
WASTED_COMBAT_ABORT_THRESHOLD = 3
LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD = 2
LOW_VALUE_EXPLORE_STUCK_LIMIT = 6
QA_PROBE_BURST_LIMIT = 4
EXPLORE_MAX_TICS_UPPER = 80
REPEATED_ACTION_ABORT_THRESHOLD = 4
BLOCKED_DECISION_ABORT_THRESHOLD = 6
PICKUP_OBJECT_TYPES = {"item", "ammo", "weapon", "key"}
DIRECTOR_POLL_SECONDS = 1.25
DIRECTOR_STUCK_POLL_THRESHOLD = 5
DIRECTOR_STUCK_RECOVERY_LIMIT = 4
PWAD_CRASH_CATEGORY = "pwad_crash"
TAKE_ACTION_BUTTONS = {
    "TURN_LEFT_RIGHT_DELTA",
    "LOOK_UP_DOWN_DELTA",
    "MOVE_FORWARD_BACKWARD_DELTA",
    "MOVE_LEFT_RIGHT_DELTA",
    "ATTACK",
    "USE",
    "SPEED",
    "SELECT_NEXT_WEAPON",
    "SELECT_PREV_WEAPON",
    "JUMP",
    "CROUCH",
}
TAKE_ACTION_BINARY_BUTTONS = {
    "ATTACK",
    "USE",
    "SPEED",
    "SELECT_NEXT_WEAPON",
    "SELECT_PREV_WEAPON",
    "JUMP",
    "CROUCH",
}
CARDINAL_DIRECTION_ANGLES = {"east": 0.0, "north": 90.0, "west": 180.0, "south": 270.0}
OBJECT_ID_ALIASES: dict[str, tuple[str, ...]] = {
    "aim_and_shoot": ("object_id", "enemy_id", "target_id", "monster_id"),
    "strafe_and_shoot": ("object_id", "enemy_id", "target_id", "monster_id"),
    "move_to": ("object_id", "target_id", "item_id", "pickup_id", "enemy_id", "monster_id"),
}
TOOL_PARAM_ALLOWLIST: dict[str, set[str]] = {
    "aim_and_shoot": {"object_id", "shots", "max_tics", "capture_telemetry", "telemetry_stride"},
    "strafe_and_shoot": {"object_id", "direction", "shots", "max_tics", "capture_telemetry", "telemetry_stride"},
    "move_to": {"object_id", "max_tics", "use", "stop_on_enemy", "capture_telemetry", "telemetry_stride"},
    "explore": {"max_tics", "stop_on_enemy", "stop_on_item", "capture_telemetry", "telemetry_stride"},
    "retreat": {"tics", "backpedal", "capture_telemetry", "telemetry_stride"},
    "get_state": {"include_sectors", "include_depth"},
    "get_threat_assessment": set(),
    "get_navigation_info": set(),
}


class RunService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = RunRepository(db)

    async def create_run(self, data: RunCreate) -> TestRun:
        await self.db.execute(text("SELECT pg_advisory_xact_lock(42770001)"))
        await self._fail_orphaned_active_runs()
        active_run = await self.repo.get_active()
        if active_run is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Another test run is already active: {active_run.id}",
            )

        wad = await WadRepository(self.db).get_by_id(data.wad_file_id)
        if wad is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "WAD not found")
        map_name = data.map_name.upper()
        if map_name not in (wad.detected_maps or []):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "map_name is not in wad_files.detected_maps")
        start_counts = player_start_counts(wad.stored_path, map_name)
        if start_counts["player_one"] == 0 and start_counts["deathmatch"] == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Map {map_name} has no Player 1 or deathmatch start. "
                "QA runs need a start position that can be normalized for single-player.",
            )

        analysis = await AnalysisRepository(self.db).get_by_wad_and_map(wad.id, map_name)
        if analysis is None:
            analysis = await AnalysisService(self.db).analyze_map(wad, map_name)

        max_ticks = max(1, min(data.max_ticks or self.settings.default_run_ticks, self.settings.max_run_ticks))
        run = await self.repo.create(
            TestRun(
                wad_file_id=wad.id,
                static_analysis_id=analysis.id,
                map_name=map_name,
                difficulty_level=data.difficulty_level,
                iwad_used=wad.iwad_required,
                llm_model=self.settings.llm_model,
                max_ticks=max_ticks,
                status="pending",
            )
        )
        await self.db.commit()
        RUN_TASKS[run.id] = asyncio.create_task(agent_run_task(run.id))
        return run

    async def cancel(self, run_id: UUID) -> TestRun:
        run = await self.repo.get_by_id(run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        task = RUN_TASKS.get(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=30)
            except asyncio.TimeoutError:
                await self.force_stop_external_game()
            except asyncio.CancelledError:
                pass
            await self.db.refresh(run)
            if run.completed_at is not None and run.report_pdf_path:
                return run
        else:
            if run.status in {"completed", "failed", "cancelled"} and run.completed_at is not None and run.report_pdf_path:
                return run
            await self.force_stop_external_game()

        await finalize_stopped_run(self.db, run.id, outcome="cancelled")
        await self.db.refresh(run)
        return run

    async def force_stop_external_game(self) -> None:
        try:
            async with McpDoomClient() as mcp:
                await mcp.stop_game()
        except Exception:
            pass

    async def _fail_orphaned_active_runs(self) -> None:
        active = await self.repo.get_active()
        if active is None:
            return
        task = RUN_TASKS.get(active.id)
        if task is not None and not task.done():
            return
        if active.status == "pending" and active.started_at is None:
            await self.repo.update(
                active,
                status="failed",
                outcome="error",
                error_message="Run task was orphaned before startup.",
                completed_at=datetime.now(UTC),
            )
            return
        if active.status == "running":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Run {active.id} is marked running. Cancel it before starting another test.",
            )


async def agent_run_task(run_id: UUID) -> None:
    async with SessionLocal() as db:
        run = await db.get(TestRun, run_id)
        if run is None:
            return
        wad = await WadRepository(db).get_by_id(run.wad_file_id)
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
        prompt = render_agent_prompt(wad, analysis, run)
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
        lockstep_state: dict[str, Any] = _initial_lockstep_state()

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
                    frame = png_bytes_to_frame(screenshot_png)
                    if frame is not None:
                        last_record_frame = frame
                        recorder.write_frame(frame, game_tick=tick)
                    recent = await _recent_trace(db, run.id)
                    threat_assessment = await _safe_context_tool(mcp, "get_threat_assessment")
                    navigation_info = await _safe_context_tool(mcp, "get_navigation_info")
                    llm_input = {
                        "tick": tick,
                        **_compact_state_for_llm(state),
                        "threat_assessment": threat_assessment,
                        "navigation_info": navigation_info,
                        "recent_trace": recent,
                        "lockstep_state": _lockstep_state_snapshot(lockstep_state),
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
                    decision = await gemini.decide(prompt, llm_input)
                    total_llm_calls += 1
                    llm_duration_ms = (time.monotonic() - llm_started) * 1000
                    decision = _apply_lockstep_recovery(decision, state, navigation_info, lockstep_state)
                    decision = _guard_lockstep_decision(decision, state, lockstep_state, navigation_info)
                    await decision_repo.update(
                        decision_row,
                        status="llm_complete",
                        llm_decision=_json_safe(decision),
                        reasoning_summary=decision.get("reasoning_summary"),
                        llm_duration_ms=llm_duration_ms,
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

                    throttle_seconds = max(0.0, get_settings().llm_throttle_seconds)
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
            failure_fields = _pwad_crash_fields(exc, runtime_stage)
            outcome = PWAD_CRASH_CATEGORY
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


async def _safe_context_tool(mcp: McpDoomClient, tool_name: str) -> dict[str, Any]:
    try:
        result = await mcp.call_tool(tool_name, {})
        state, _ = normalize_mcp_state(result)
        return _json_safe(state) if isinstance(state, dict) else {"result": _summary(result)}
    except Exception as exc:
        return {"error": str(exc), "tool": tool_name}


def _compact_state_for_llm(state: dict[str, Any]) -> dict[str, Any]:
    compact = {key: value for key, value in state.items() if key not in {"screenshot_png", "sectors"}}
    if isinstance(compact.get("objects"), list):
        objects = []
        for obj in compact["objects"][:30]:
            if not isinstance(obj, dict):
                continue
            objects.append(
                {
                    key: obj.get(key)
                    for key in (
                        "id",
                        "name",
                        "type",
                        "threat",
                        "attack_type",
                        "distance",
                        "angle_to_aim",
                        "is_visible",
                        "screen_x",
                        "screen_y",
                    )
                    if key in obj
                }
            )
        compact["objects"] = objects
    return _json_safe(compact)


def _lockstep_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "no_progress_polls": int(state.get("no_progress_polls") or 0),
        "recovery_count": int(state.get("recovery_count") or 0),
        "wasted_combat_count": int(state.get("wasted_combat_count") or 0),
        "consecutive_explore_max_tics": int(state.get("consecutive_explore_max_tics") or 0),
        "low_value_explore_total": int(state.get("low_value_explore_total") or 0),
        "low_value_explore_cumulative": int(state.get("low_value_explore_cumulative") or 0),
        "qa_probe_count": int(state.get("qa_probe_count") or 0),
        "invisible_target_failures": dict(state.get("invisible_target_failures") or {}),
        "completed_object_ids": dict(state.get("completed_object_ids") or {}),
        "failed_object_ids": dict(state.get("failed_object_ids") or {}),
        "out_of_ammo_targets": dict(state.get("out_of_ammo_targets") or {}),
        "blocked_decision_count": int(state.get("blocked_decision_count") or 0),
        "progress_score": int(state.get("progress_score") or 0),
        "quality_warnings": list(state.get("quality_warnings") or [])[-8:],
    }


def _initial_lockstep_state() -> dict[str, Any]:
    return {
        "last_signature": None,
        "no_progress_polls": 0,
        "recovery_count": 0,
        "last_tick": -1,
        "invisible_target_failures": {},
        "wasted_combat_count": 0,
        "consecutive_explore_max_tics": 0,
        "low_value_explore_total": 0,
        "low_value_explore_cumulative": 0,
        "qa_probe_count": 0,
        "completed_object_ids": {},
        "failed_object_ids": {},
        "out_of_ammo_targets": {},
        "action_signature_counts": {},
        "blocked_decision_count": 0,
        "progress_score": 0,
        "meaningful_progress_events": 0,
        "quality_warnings": [],
    }


def _apply_lockstep_recovery(
    decision: dict[str, Any],
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: dict[str, Any],
) -> dict[str, Any]:
    selected_tool = str(decision.get("mcp_tool") or "explore")
    low_value_explores = int(lockstep_state.get("low_value_explore_total") or 0)
    if selected_tool == "explore" and low_value_explores >= LOW_VALUE_EXPLORE_OVERRIDE_THRESHOLD:
        probe_count = int(lockstep_state.get("qa_probe_count") or 0)
        if probe_count < QA_PROBE_BURST_LIMIT:
            return _qa_probe_decision(
                state,
                navigation_info,
                lockstep_state,
                (
                    "Recent explore calls consumed their tic budget without enemies, items, exits, or other QA "
                    "progress, so I am taking direct lockstep control to break the circular movement pattern."
                ),
            )
        lockstep_state["qa_probe_count"] = 0
        lockstep_state["low_value_explore_total"] = 0

    signature = _lockstep_progress_signature(state, navigation_info)
    if signature != lockstep_state.get("last_signature"):
        lockstep_state["last_signature"] = signature
        lockstep_state["no_progress_polls"] = 0
        lockstep_state["should_stop_stuck"] = False
        return decision

    lockstep_state["no_progress_polls"] = int(lockstep_state.get("no_progress_polls") or 0) + 1
    if int(lockstep_state["no_progress_polls"]) < STUCK_RUN_ABORT_THRESHOLD:
        return decision

    recovery_count = int(lockstep_state.get("recovery_count") or 0) + 1
    lockstep_state["recovery_count"] = recovery_count
    lockstep_state["no_progress_polls"] = 0
    if recovery_count >= DIRECTOR_STUCK_RECOVERY_LIMIT:
        lockstep_state["should_stop_stuck"] = True
    if recovery_count % 2:
        return _qa_probe_decision(
            state,
            navigation_info,
            lockstep_state,
            "Progress has not changed across repeated lockstep decisions, so I am forcing a bounded QA recovery probe.",
        )
    return {
        "reasoning_summary": (
            "The previous recovery did not create measurable progress, so I am exploring from the new angle with "
            "enemy and item stops enabled."
        ),
        "mcp_tool": "explore",
        "mcp_params": {"max_tics": EXPLORE_MAX_TICS_UPPER, "stop_on_enemy": True, "stop_on_item": True},
        "event_type_override": "stuck",
        "observed_issue": None,
    }


def _qa_probe_decision(
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    probe_index = int(lockstep_state.get("qa_probe_count") or 0)
    lockstep_state["qa_probe_count"] = probe_index + 1
    variables = normalize_variables(state)
    angle = _bounded_float(variables.get("angle"), 0.0)
    suggested = str(navigation_info.get("suggested_direction") or "").lower()
    nearby_doors = navigation_info.get("nearby_doors") if isinstance(navigation_info, dict) else None
    phase = probe_index % QA_PROBE_BURST_LIMIT

    if phase == 0 and isinstance(nearby_doors, list) and nearby_doors:
        return {
            "reasoning_summary": f"{reason} A nearby door-like sector is known, so I am pressing USE and nudging forward.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"USE": 1, "MOVE_FORWARD_BACKWARD_DELTA": 8}, "tics": 4},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    if phase == 0:
        turn = _turn_delta_for_direction(suggested, angle)
        if turn == 0:
            turn = 35.0
        return {
            "reasoning_summary": (
                f"{reason} I am facing a fresh unexplored direction first, then I will move in short bounded steps."
            ),
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"TURN_LEFT_RIGHT_DELTA": turn}, "tics": 1},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    if phase == 1:
        return {
            "reasoning_summary": f"{reason} I am advancing straight under direct control instead of letting explore arc in place.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"MOVE_FORWARD_BACKWARD_DELTA": 25, "SPEED": 1}, "tics": 6},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    if phase == 2:
        return {
            "reasoning_summary": f"{reason} I am probing for a switch or door interaction before declaring the area blocked.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"USE": 1}, "tics": 3},
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    return {
        "reasoning_summary": f"{reason} The direct probes did not progress yet, so I am retreating and rotating out of the loop.",
        "mcp_tool": "retreat",
        "mcp_params": {"tics": 28, "backpedal": False},
        "event_type_override": "stuck",
        "observed_issue": None,
    }


def _turn_delta_for_direction(direction: str, current_angle: float) -> float:
    target_angle = CARDINAL_DIRECTION_ANGLES.get(direction)
    if target_angle is None:
        return 0.0
    diff = (target_angle - current_angle + 180.0) % 360.0 - 180.0
    return round(max(-45.0, min(45.0, -diff)), 1)


def _guard_lockstep_decision(
    decision: dict[str, Any],
    state: dict[str, Any],
    lockstep_state: dict[str, Any],
    navigation_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tool = decision.get("mcp_tool") or "explore"
    params = _normalize_mcp_params(tool, dict(decision.get("mcp_params") or {}))
    invisible_failures = lockstep_state.get("invisible_target_failures") or {}
    object_id = params.get("object_id")
    signature = _action_signature(tool, params)
    signature_count = int((lockstep_state.get("action_signature_counts") or {}).get(signature, 0))
    if signature_count >= REPEATED_ACTION_ABORT_THRESHOLD:
        return _blocked_decision_fallback(
            f"The requested action repeats a recent no-progress signature ({tool}), so I am switching tactics.",
            state,
            navigation_info or {},
            lockstep_state,
        )
    if tool == "move_to" and object_id is not None:
        completed = lockstep_state.get("completed_object_ids") or {}
        failed = lockstep_state.get("failed_object_ids") or {}
        if str(object_id) in completed:
            return _blocked_decision_fallback(
                f"Object {object_id} was already reached or collected in this run, so I will not target it again.",
                state,
                navigation_info or {},
                lockstep_state,
            )
        if int(failed.get(str(object_id), 0) or 0) >= 2:
            return _blocked_decision_fallback(
                f"Object {object_id} has failed repeatedly, so I am changing route instead of looping on it.",
                state,
                navigation_info or {},
                lockstep_state,
            )
    if tool in COMBAT_TOOLS:
        out_of_ammo_targets = lockstep_state.get("out_of_ammo_targets") or {}
        if object_id is not None and str(object_id) in out_of_ammo_targets:
            return _blocked_decision_fallback(
                f"Combat target {object_id} already returned out_of_ammo, so I need resources or another tactic first.",
                state,
                navigation_info or {},
                lockstep_state,
                prefer_resources=True,
            )
        if object_id is not None and str(object_id) in invisible_failures:
            return {
                "reasoning_summary": (
                    f"Target {object_id} was recently rejected as not visible, so I am exploring instead of firing "
                    "through geometry."
                ),
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": True},
                "observed_issue": None,
            }
        if not _combat_target_is_visible(state, object_id):
            return {
                "reasoning_summary": (
                    f"The requested combat target {object_id} is not a visible monster in the current state, so I am "
                    "switching to exploration rather than shooting through a wall."
                ),
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": True},
                "observed_issue": None,
            }
    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    return decision


def _blocked_decision_fallback(
    reason: str,
    state: dict[str, Any],
    navigation_info: dict[str, Any],
    lockstep_state: dict[str, Any],
    prefer_resources: bool = False,
) -> dict[str, Any]:
    lockstep_state["blocked_decision_count"] = int(lockstep_state.get("blocked_decision_count") or 0) + 1
    warnings = list(lockstep_state.get("quality_warnings") or [])
    warnings.append(reason)
    lockstep_state["quality_warnings"] = warnings[-20:]
    if int(lockstep_state["blocked_decision_count"]) >= BLOCKED_DECISION_ABORT_THRESHOLD:
        lockstep_state["should_stop_stuck"] = True
        lockstep_state["stop_outcome"] = "stuck"

    pickup = _nearest_available_pickup(state, lockstep_state, prefer_resources=prefer_resources)
    if pickup is not None:
        return {
            "reasoning_summary": f"{reason} I am switching to available pickup {pickup.get('name', 'object')} first.",
            "mcp_tool": "move_to",
            "mcp_params": {"object_id": pickup["id"], "max_tics": 80, "stop_on_enemy": True},
            "event_type_override": "stuck",
            "observed_issue": None,
        }
    if prefer_resources:
        return {
            "reasoning_summary": f"{reason} No visible pickup is available, so I am switching weapon before reassessing.",
            "mcp_tool": "take_action",
            "mcp_params": {"actions": {"SELECT_NEXT_WEAPON": 1}, "tics": 2},
            "event_type_override": "stuck",
            "observed_issue": None,
        }
    return _qa_probe_decision(state, navigation_info, lockstep_state, reason)


def _nearest_available_pickup(
    state: dict[str, Any],
    lockstep_state: dict[str, Any],
    prefer_resources: bool = False,
) -> dict[str, Any] | None:
    completed = {str(key) for key in (lockstep_state.get("completed_object_ids") or {})}
    failed = lockstep_state.get("failed_object_ids") or {}
    candidates = []
    for obj in state.get("objects") or []:
        if not isinstance(obj, dict) or obj.get("id") is None:
            continue
        if str(obj.get("id")) in completed or int(failed.get(str(obj.get("id")), 0) or 0) >= 2:
            continue
        obj_type = obj.get("type")
        if obj_type not in PICKUP_OBJECT_TYPES:
            continue
        if prefer_resources and obj_type not in {"ammo", "weapon", "item"}:
            continue
        if not obj.get("is_visible"):
            continue
        candidates.append(obj)
    if not candidates:
        return None
    return min(candidates, key=lambda obj: float(obj.get("distance") or 999999))


def _action_signature(tool: str, params: dict[str, Any]) -> str:
    compact_params = {
        key: params.get(key)
        for key in sorted(params)
        if key not in {"capture_telemetry", "telemetry_stride"}
    }
    return f"{tool}:{json.dumps(_json_safe(compact_params), sort_keys=True, default=str)}"


def _update_lockstep_after_action(
    decision: dict[str, Any],
    mcp_call: dict[str, Any],
    lockstep_state: dict[str, Any],
) -> None:
    summary = _mcp_action_summary(mcp_call)
    tool = str(mcp_call.get("tool") or decision.get("mcp_tool") or "")
    stop_reason = str(summary.get("stop_reason") or "")
    params = mcp_call.get("input") if isinstance(mcp_call.get("input"), dict) else {}
    object_id = params.get("object_id")
    signature = _action_signature(tool, params if isinstance(params, dict) else {})
    signature_counts = dict(lockstep_state.get("action_signature_counts") or {})
    signature_counts[signature] = int(signature_counts.get(signature, 0)) + 1
    lockstep_state["action_signature_counts"] = dict(list(signature_counts.items())[-50:])

    if tool == "explore" and stop_reason == "max_tics":
        lockstep_state["consecutive_explore_max_tics"] = int(lockstep_state.get("consecutive_explore_max_tics") or 0) + 1
        lockstep_state["low_value_explore_total"] = int(lockstep_state.get("low_value_explore_total") or 0) + 1
        lockstep_state["low_value_explore_cumulative"] = int(lockstep_state.get("low_value_explore_cumulative") or 0) + 1
    elif tool == "explore" and stop_reason in {"enemy_spotted", "item_found", "episode_finished", "player_died"}:
        lockstep_state["consecutive_explore_max_tics"] = 0
        lockstep_state["low_value_explore_total"] = 0
        lockstep_state["low_value_explore_cumulative"] = 0
        lockstep_state["qa_probe_count"] = 0
    elif tool in {"move_to", "aim_and_shoot", "strafe_and_shoot"} and stop_reason not in {"target_not_visible", "no_target"}:
        lockstep_state["consecutive_explore_max_tics"] = 0
        lockstep_state["low_value_explore_total"] = 0
        lockstep_state["low_value_explore_cumulative"] = 0
        lockstep_state["qa_probe_count"] = 0
    else:
        lockstep_state["consecutive_explore_max_tics"] = 0

    if (
        int(lockstep_state.get("low_value_explore_total") or 0) >= LOW_VALUE_EXPLORE_STUCK_LIMIT
        or int(lockstep_state.get("low_value_explore_cumulative") or 0) >= LOW_VALUE_EXPLORE_STUCK_LIMIT
    ):
        lockstep_state["should_stop_stuck"] = True

    if tool == "move_to" and object_id is not None:
        if stop_reason == "arrived":
            completed = dict(lockstep_state.get("completed_object_ids") or {})
            key = str(object_id)
            if key not in completed:
                lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 2
                lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
            completed[key] = {
                "target_name": summary.get("target_name"),
                "target_type": summary.get("target_type"),
                "stop_reason": stop_reason,
            }
            lockstep_state["completed_object_ids"] = completed
            lockstep_state["blocked_decision_count"] = 0
        elif stop_reason in {"stuck", "pickup_not_collected", "arrival_blocked", "target_lost", "max_tics"}:
            failed = dict(lockstep_state.get("failed_object_ids") or {})
            key = str(object_id)
            failed[key] = int(failed.get(key, 0)) + 1
            lockstep_state["failed_object_ids"] = failed
    if tool in COMBAT_TOOLS and stop_reason == "out_of_ammo" and object_id is not None:
        out_of_ammo = dict(lockstep_state.get("out_of_ammo_targets") or {})
        key = str(object_id)
        out_of_ammo[key] = int(out_of_ammo.get(key, 0)) + 1
        lockstep_state["out_of_ammo_targets"] = out_of_ammo
        warnings = list(lockstep_state.get("quality_warnings") or [])
        warnings.append(f"Combat against target {object_id} stopped with out_of_ammo.")
        lockstep_state["quality_warnings"] = warnings[-20:]
    if stop_reason in {"target_killed", "shots_complete"} and (_int_like(summary.get("hits_landed")) or _int_like(summary.get("kills"))):
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 3
        lockstep_state["meaningful_progress_events"] = int(lockstep_state.get("meaningful_progress_events") or 0) + 1
        lockstep_state["blocked_decision_count"] = 0
    if stop_reason in {"item_found", "enemy_spotted"}:
        lockstep_state["progress_score"] = int(lockstep_state.get("progress_score") or 0) + 1

    if summary.get("stop_reason") == "target_not_visible":
        params = decision.get("mcp_params") if isinstance(decision.get("mcp_params"), dict) else {}
        object_id = params.get("object_id")
        if object_id is not None:
            failures = dict(lockstep_state.get("invisible_target_failures") or {})
            failures[str(object_id)] = int(failures.get(str(object_id), 0)) + 1
            lockstep_state["invisible_target_failures"] = failures
    if _is_wasted_combat_decision(decision, mcp_call):
        lockstep_state["wasted_combat_count"] = int(lockstep_state.get("wasted_combat_count") or 0) + 1
    else:
        lockstep_state["wasted_combat_count"] = 0
    if int(lockstep_state.get("wasted_combat_count") or 0) >= WASTED_COMBAT_ABORT_THRESHOLD:
        lockstep_state["no_progress_polls"] = STUCK_RUN_ABORT_THRESHOLD


def _lockstep_should_stop_as_stuck(lockstep_state: dict[str, Any]) -> bool:
    return bool(lockstep_state.get("should_stop_stuck"))


def _lockstep_stop_outcome(lockstep_state: dict[str, Any]) -> str:
    outcome = str(lockstep_state.get("stop_outcome") or "stuck")
    return outcome if outcome in {"stuck", "incomplete_coverage"} else "stuck"


def _lockstep_progress_metrics(lockstep_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "progress_score": int(lockstep_state.get("progress_score") or 0),
        "meaningful_progress_events": int(lockstep_state.get("meaningful_progress_events") or 0),
        "completed_object_count": len(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_count": len(lockstep_state.get("failed_object_ids") or {}),
        "out_of_ammo_target_count": len(lockstep_state.get("out_of_ammo_targets") or {}),
        "blocked_decision_count": int(lockstep_state.get("blocked_decision_count") or 0),
        "low_value_explore_count": int(lockstep_state.get("low_value_explore_cumulative") or 0),
        "recovery_count": int(lockstep_state.get("recovery_count") or 0),
    }


def _lockstep_quality_flags(lockstep_state: dict[str, Any], recording_metadata: dict[str, Any]) -> dict[str, Any]:
    warnings = list(lockstep_state.get("quality_warnings") or [])
    warnings.extend(recording_metadata.get("validation_warnings") or [])
    return {
        "quality_status": "warning" if warnings else "ok",
        "warnings": warnings[-30:],
        "completed_object_ids": dict(lockstep_state.get("completed_object_ids") or {}),
        "failed_object_ids": dict(lockstep_state.get("failed_object_ids") or {}),
        "out_of_ammo_targets": dict(lockstep_state.get("out_of_ammo_targets") or {}),
        "recording_quality_status": recording_metadata.get("quality_status"),
    }


def _unique_lockstep_tick(state: dict[str, Any], lockstep_state: dict[str, Any]) -> int:
    previous = lockstep_state.get("last_tick")
    last_tick = int(previous) if previous is not None else -1
    raw_tick = _bounded_int(state.get("tic"), default=last_tick + 1, lower=0)
    tick = max(raw_tick, last_tick + 1)
    lockstep_state["last_tick"] = tick
    return tick


def _lockstep_progress_signature(state: dict[str, Any], navigation_info: dict[str, Any]) -> tuple[Any, ...]:
    variables = normalize_variables(state)
    x = float(variables.get("x") or 0)
    y = float(variables.get("y") or 0)
    return (
        round(x / 128),
        round(y / 128),
        int(variables.get("kill_count") or 0),
        int(variables.get("item_count") or 0),
        int(variables.get("secret_count") or 0),
        int(navigation_info.get("cells_explored") or 0),
        len(navigation_info.get("keys_found") or []),
    )


def _state_report_call(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "service": "mcp-doom",
        "tool": "get_state",
        "input": {},
        "output": _json_safe(
            {
                **_compact_state_for_llm(state),
                "action_summary": {
                    "stop_reason": "episode_finished" if state.get("episode_finished") else "state_report",
                    "executor_control": False,
                    "lockstep_control": True,
                },
            }
        ),
    }


def _initial_strategy_decision(analysis: StaticAnalysisResult, run: TestRun) -> dict[str, Any]:
    skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
    spawned_enemies = int(skill_summary.get("thing_count_enemies") or 0)
    return {
        "reasoning_summary": (
            "Initializing async gameplay strategy from selected-difficulty static analysis."
        ),
        "mcp_tool": "set_strategy",
        "mcp_params": {
            "aggression": 0.8 if spawned_enemies else 0.35,
            "health_retreat_threshold": 25,
            "health_collect_threshold": 65,
            "ammo_switch_threshold": 3,
            "engage_range": 1400 if spawned_enemies else 700,
            "collect_range": 1100,
            "prefer_cover": bool(spawned_enemies),
        },
    }


def _initial_objective_decision(analysis: StaticAnalysisResult, run: TestRun) -> dict[str, Any]:
    skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
    spawned_enemies = int(skill_summary.get("thing_count_enemies") or 0)
    return {
        "reasoning_summary": (
            "Starting the async executor with broad exploration; combat and pickup handling continue autonomously."
        ),
        "mcp_tool": "set_objective",
        "mcp_params": {
            "objective_type": "explore",
            "priority": 40 if spawned_enemies else 25,
            "timeout_tics": 420,
            "replace": True,
        },
    }


async def _execute_director_tool(
    mcp: McpDoomClient,
    decision: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    tool = decision.get("mcp_tool") or "get_situation_report"
    params = dict(decision.get("mcp_params") or {})
    if tool == "set_objective":
        params = _normalize_director_objective_params(params)
        response = await mcp.set_objective(**params)
        stop_reason = "objective_set"
    elif tool == "set_strategy":
        params = _normalize_director_strategy_params(params)
        if not params:
            tool = "get_situation_report"
            response = await mcp.call_tool("get_situation_report", {})
            stop_reason = "strategy_unchanged"
        else:
            response = await mcp.set_strategy(**params)
            stop_reason = "strategy_updated"
    else:
        tool = "get_situation_report"
        params = {}
        response = await mcp.call_tool("get_situation_report", {})
        stop_reason = "situation_report"

    output = _compact_mcp_output(response)
    if not isinstance(output, dict):
        output = {"result": output}
    output.setdefault(
        "action_summary",
        {
            "stop_reason": stop_reason,
            "director_tool": tool,
            "objective_type": params.get("objective_type"),
            "executor_control": True,
        },
    )
    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    return response, {
        "service": "mcp-doom",
        "tool": tool,
        "input": _json_safe(params),
        "output": _json_safe(output),
    }


def _normalize_director_objective_params(params: dict[str, Any]) -> dict[str, Any]:
    valid = {"explore", "kill", "move_to_pos", "move_to_obj", "collect", "use_object", "retreat", "hold_position"}
    objective_type = str(params.get("objective_type") or params.get("type") or "explore")
    if objective_type not in valid:
        objective_type = "explore"
    objective_params = params.get("params") if isinstance(params.get("params"), dict) else {}
    if "object_id" in params and "object_id" not in objective_params:
        with contextlib.suppress(TypeError, ValueError):
            objective_params["object_id"] = int(params["object_id"])
    for coord in ("x", "y"):
        if coord in params and coord not in objective_params:
            with contextlib.suppress(TypeError, ValueError):
                objective_params[coord] = float(params[coord])
    return {
        "objective_type": objective_type,
        "params": objective_params,
        "priority": _bounded_int(params.get("priority"), default=25, lower=0, upper=200),
        "timeout_tics": _bounded_int(params.get("timeout_tics"), default=350, lower=0, upper=2000),
        "replace": bool(params.get("replace", False)),
    }


def _normalize_director_strategy_params(params: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "aggression",
        "health_retreat_threshold",
        "health_collect_threshold",
        "ammo_switch_threshold",
        "engage_range",
        "collect_range",
        "prefer_cover",
    }
    normalized = {key: params[key] for key in allowed if key in params}
    if "aggression" in normalized:
        normalized["aggression"] = max(0.0, min(1.0, _bounded_float(normalized["aggression"], 0.5)))
    for key in ("health_retreat_threshold", "health_collect_threshold", "ammo_switch_threshold"):
        if key in normalized:
            normalized[key] = _bounded_int(normalized[key], default=0, lower=0, upper=200)
    for key in ("engage_range", "collect_range"):
        if key in normalized:
            normalized[key] = max(1.0, min(5000.0, _bounded_float(normalized[key], 1000.0)))
    if "prefer_cover" in normalized:
        normalized["prefer_cover"] = bool(normalized["prefer_cover"])
    return normalized


def _apply_director_recovery(
    decision: dict[str, Any],
    situation: dict[str, Any],
    director_state: dict[str, Any],
) -> dict[str, Any]:
    signature = _director_progress_signature(situation)
    if signature != director_state.get("last_signature"):
        director_state["last_signature"] = signature
        director_state["no_progress_polls"] = 0
        director_state["should_stop_stuck"] = False
    else:
        director_state["no_progress_polls"] = int(director_state.get("no_progress_polls") or 0) + 1

    progress = situation.get("executor_progress") if isinstance(situation.get("executor_progress"), dict) else {}
    stuck_recovery_count = int(progress.get("stuck_recovery_count") or 0)
    if stuck_recovery_count > int(director_state.get("last_stuck_recovery_count") or 0):
        director_state["no_progress_polls"] = max(
            int(director_state.get("no_progress_polls") or 0),
            DIRECTOR_STUCK_POLL_THRESHOLD,
        )
    director_state["last_stuck_recovery_count"] = stuck_recovery_count

    if int(director_state.get("no_progress_polls") or 0) >= DIRECTOR_STUCK_POLL_THRESHOLD:
        recovery_count = int(director_state.get("recovery_count") or 0) + 1
        director_state["recovery_count"] = recovery_count
        director_state["no_progress_polls"] = 0
        if recovery_count >= DIRECTOR_STUCK_RECOVERY_LIMIT:
            director_state["should_stop_stuck"] = True
        objective = "retreat" if recovery_count % 2 else "explore"
        return {
            "reasoning_summary": (
                f"Coverage progress stalled for repeated director polls; replacing the queue with {objective} recovery."
            ),
            "mcp_tool": "set_objective",
            "mcp_params": {
                "objective_type": objective,
                "priority": 120,
                "timeout_tics": 210,
                "replace": True,
            },
            "event_type_override": "stuck",
            "observed_issue": None,
        }

    objectives = situation.get("objectives") if isinstance(situation.get("objectives"), list) else []
    if not objectives and decision.get("mcp_tool") == "get_situation_report":
        return {
            "reasoning_summary": "Executor had no queued objective, so directing exploration coverage.",
            "mcp_tool": "set_objective",
            "mcp_params": {
                "objective_type": "explore",
                "priority": 45,
                "timeout_tics": 350,
                "replace": False,
            },
            "observed_issue": None,
        }
    return decision


def _director_progress_signature(situation: dict[str, Any]) -> tuple[Any, ...]:
    variables = normalize_variables(situation)
    exploration = situation.get("exploration") if isinstance(situation.get("exploration"), dict) else {}
    x = float(variables.get("x") or 0)
    y = float(variables.get("y") or 0)
    return (
        round(x / 128),
        round(y / 128),
        int(variables.get("kill_count") or 0),
        int(variables.get("item_count") or 0),
        int(variables.get("secret_count") or 0),
        int(exploration.get("cells_explored") or 0),
        len(exploration.get("keys_found") or []),
    )


def _director_should_stop_as_stuck(director_state: dict[str, Any]) -> bool:
    return bool(director_state.get("should_stop_stuck"))


def _unique_director_tick(situation: dict[str, Any], director_state: dict[str, Any]) -> int:
    previous = director_state.get("last_tick")
    last_tick = int(previous) if previous is not None else -1
    raw_tick = _bounded_int(situation.get("tic"), default=last_tick + 1, lower=0)
    tick = max(raw_tick, last_tick + 1)
    director_state["last_tick"] = tick
    return tick


def _situation_finished(situation: dict[str, Any]) -> bool:
    return bool(
        situation.get("episode_finished")
        or situation.get("episode_timeout")
        or situation.get("level_completed")
        or situation.get("next_map")
        or situation.get("dead")
    )


def _situation_report_call(situation: dict[str, Any]) -> dict[str, Any]:
    return {
        "service": "mcp-doom",
        "tool": "get_situation_report",
        "input": {},
        "output": _json_safe(
            {
                **_compact_situation(situation),
                "action_summary": {
                    "stop_reason": "episode_finished" if situation.get("episode_finished") else "situation_report",
                    "director_tool": "get_situation_report",
                    "executor_control": True,
                },
            }
        ),
    }


def _compact_situation(situation: dict[str, Any]) -> dict[str, Any]:
    compact = {key: value for key, value in situation.items() if key not in {"screenshot_png", "depth", "sectors"}}
    if isinstance(compact.get("objects"), list):
        compact["objects"] = compact["objects"][:20]
    if isinstance(compact.get("events"), list):
        compact["events"] = compact["events"][-20:]
    return _json_safe(compact)


def _pwad_crash_fields(exc: Exception, stage: str) -> dict[str, Any]:
    raw_error = str(exc)
    summary = "PWAD crashed or failed to initialize under the configured ViZDoom/Freedoom test environment."
    if stage == "gameplay":
        summary = "PWAD runtime crashed or disconnected during the automated playthrough."
    return {
        "failure_category": PWAD_CRASH_CATEGORY,
        "failure_stage": stage,
        "failure_summary": summary,
        "failure_diagnostics": {
            "raw_error": raw_error,
            "exception_type": exc.__class__.__name__,
            "user_facing_outcome": PWAD_CRASH_CATEGORY,
        },
    }


def _bounded_int(value: Any, default: int, lower: int = 0, upper: int | None = None) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    parsed = max(lower, parsed)
    if upper is not None:
        parsed = min(upper, parsed)
    return parsed


def _bounded_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _execute_tool(
    mcp: McpDoomClient,
    decision: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
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


def _normalize_mcp_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    if tool == "step":
        return params
    if tool == "take_action":
        return _normalize_take_action_params(params)

    if tool in OBJECT_ID_TOOLS and "object_id" not in params:
        for alias in OBJECT_ID_ALIASES.get(tool, ("object_id",)):
            if alias in params:
                params["object_id"] = params[alias]
                break

    if "object_id" in params:
        with contextlib.suppress(TypeError, ValueError):
            params["object_id"] = int(params["object_id"])

    allowed = TOOL_PARAM_ALLOWLIST.get(tool)
    if allowed is not None:
        params = {key: value for key, value in params.items() if key in allowed}

    return _bound_mcp_tool_params(tool, params)


def _bound_mcp_tool_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    if tool == "explore":
        params["max_tics"] = _bounded_int(
            params.get("max_tics"),
            default=EXPLORE_MAX_TICS_UPPER,
            lower=20,
            upper=EXPLORE_MAX_TICS_UPPER,
        )
        if "stop_on_enemy" in params:
            params["stop_on_enemy"] = bool(params["stop_on_enemy"])
        if "stop_on_item" in params:
            params["stop_on_item"] = bool(params["stop_on_item"])
    elif tool in {"aim_and_shoot", "strafe_and_shoot"}:
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=90, lower=10, upper=120)
        if "shots" in params:
            params["shots"] = _bounded_int(params.get("shots"), default=5, lower=1, upper=8)
        if tool == "strafe_and_shoot":
            direction = str(params.get("direction") or "auto").lower()
            params["direction"] = direction if direction in {"left", "right", "auto"} else "auto"
    elif tool == "move_to":
        params["max_tics"] = _bounded_int(params.get("max_tics"), default=140, lower=20, upper=180)
        if "use" in params:
            params["use"] = bool(params["use"])
        if "stop_on_enemy" in params:
            params["stop_on_enemy"] = bool(params["stop_on_enemy"])
    elif tool == "retreat":
        params["tics"] = _bounded_int(params.get("tics"), default=35, lower=8, upper=70)
        if "backpedal" in params:
            params["backpedal"] = bool(params["backpedal"])
    if tool in COMPOUND_TELEMETRY_TOOLS and "telemetry_stride" in params:
        params["telemetry_stride"] = _bounded_int(params.get("telemetry_stride"), default=2, lower=1, upper=10)
    return params


def _normalize_take_action_params(params: dict[str, Any]) -> dict[str, Any]:
    actions_source = params.get("actions")
    if not isinstance(actions_source, dict):
        actions_source = {key: value for key, value in params.items() if key in TAKE_ACTION_BUTTONS}

    actions: dict[str, float | int] = {}
    for key, value in actions_source.items():
        name = str(key).upper()
        if name not in TAKE_ACTION_BUTTONS:
            continue
        if name in TAKE_ACTION_BINARY_BUTTONS:
            actions[name] = 1 if _bounded_float(value, 0.0) > 0 else 0
        elif name in {"TURN_LEFT_RIGHT_DELTA", "LOOK_UP_DOWN_DELTA"}:
            actions[name] = round(max(-45.0, min(45.0, _bounded_float(value, 0.0))), 2)
        else:
            actions[name] = round(max(-50.0, min(50.0, _bounded_float(value, 0.0))), 2)

    return {
        "actions": actions,
        "tics": _bounded_int(params.get("tics"), default=4, lower=1, upper=8),
    }


def _combat_target_is_visible(state: dict[str, Any] | None, object_id: Any) -> bool:
    if object_id is None or not isinstance(state, dict):
        return False
    for obj in state.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        if obj.get("id") == object_id and obj.get("type") == "monster":
            return bool(obj.get("is_visible"))
    return False


def _is_stuck_decision(event: Any, mcp_call: dict[str, Any]) -> bool:
    if getattr(event, "event_type", None) == "stuck":
        return True
    summary = _mcp_action_summary(mcp_call)
    return summary.get("stop_reason") == "stuck"


def _is_wasted_combat_decision(decision: dict[str, Any], mcp_call: dict[str, Any]) -> bool:
    if decision.get("mcp_tool") not in COMBAT_TOOLS:
        return False
    summary = _mcp_action_summary(mcp_call)
    stop_reason = summary.get("stop_reason")
    if stop_reason == "target_not_visible":
        return True
    shots = _int_like(summary.get("shots_fired"))
    hits = _int_like(summary.get("hits_landed"))
    kills = _int_like(summary.get("kills"))
    return shots > 0 and hits == 0 and kills == 0


def _int_like(value: Any) -> int:
    with contextlib.suppress(TypeError, ValueError):
        return int(float(value))
    return 0


def _mcp_action_summary(mcp_call: dict[str, Any]) -> dict[str, Any]:
    output = mcp_call.get("output")
    if not isinstance(output, dict):
        return {}
    summary = output.get("action_summary")
    return summary if isinstance(summary, dict) else {}


def _pop_telemetry_frames(state: dict[str, Any]) -> list[dict[str, Any]]:
    frames = state.pop("telemetry_frames", None) if isinstance(state, dict) else None
    if not isinstance(frames, list):
        return []
    return [frame for frame in frames if isinstance(frame, dict)]


async def _record_telemetry_frames(
    run_id: UUID,
    tick: int,
    telemetry_frames: list[dict[str, Any]],
    collector: CollectorService,
    recorder: RecordingService,
) -> None:
    for index, sample in enumerate(telemetry_frames):
        sample_tick = _telemetry_sample_tick(sample, fallback=tick + index + 1)
        sample_state = {
            "game_variables": sample.get("game_variables") or sample.get("variables") or sample,
            "level_completed": sample.get("level_completed"),
            "map_exit": sample.get("map_exit"),
            "next_map": sample.get("next_map"),
        }
        await collector.collect_position(run_id, sample_tick, sample_state)

        png_b64 = sample.get("screenshot_png_b64") or sample.get("screenshot_b64")
        if not isinstance(png_b64, str) or not png_b64:
            continue
        try:
            png_bytes = base64.b64decode(png_b64, validate=True)
        except (binascii.Error, ValueError):
            continue
        frame = png_bytes_to_frame(png_bytes)
        recorder.write_frame(frame, game_tick=sample_tick)


def _telemetry_sample_tick(sample: dict[str, Any], fallback: int) -> int:
    with contextlib.suppress(TypeError, ValueError):
        raw = sample.get("tic")
        if raw is not None:
            return max(0, int(float(raw)))
    return fallback


def _write_realtime_frame(
    recorder: RecordingService,
    frame: Any,
    last_record_frame_at: float | None,
) -> float | None:
    if frame is None:
        return last_record_frame_at
    now = time.monotonic()
    if last_record_frame_at is None:
        recorder.write_frame(frame)
        return now
    elapsed = max(0.0, now - last_record_frame_at)
    repeats = max(1, min(60, int(round(elapsed * recorder.fps))))
    for _ in range(repeats):
        recorder.write_frame(frame)
    return now


async def _recent_trace(db: AsyncSession, run_id: UUID) -> list[dict[str, Any]]:
    from sqlalchemy import select
    from app.models import GameEvent

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


async def _broadcast_state(
    run: TestRun,
    event: Any,
    decision: dict[str, Any],
    screenshot_b64: str | None = None,
) -> None:
    await websocket_service.broadcast(
        run.id,
        {
            "type": "state",
            "tick": event.tick_number,
            "status": run.status,
            "health": event.health,
            "armor": event.armor,
            "kills": event.kill_count,
            "ammo": {
                "bullets": event.ammo_bullets,
                "shells": event.ammo_shells,
                "rockets": event.ammo_rockets,
                "cells": event.ammo_cells,
            },
            "position": {"x": event.player_x, "y": event.player_y, "angle": event.player_angle},
            "event_type": event.event_type,
            "llm_reasoning": event.llm_reasoning,
            "action": {"mcp_tool": decision.get("mcp_tool"), "mcp_params": decision.get("mcp_params") or {}},
            "screenshot_b64": screenshot_b64,
        },
    )


def _compact_mcp_output(value: Any) -> Any:
    state, _ = normalize_mcp_state(value)
    if not isinstance(state, dict):
        return _summary(value)
    compact = {key: val for key, val in state.items() if key not in {"telemetry_frames", "depth", "sectors"}}
    if isinstance(compact.get("objects"), list):
        compact["objects"] = compact["objects"][:12]
    if "action_summary" in state:
        compact["action_summary"] = state["action_summary"]
    return compact


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _summary(value: Any) -> str:
    text = json.dumps(_json_safe(value), default=str) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= 1000 else text[:1000] + "..."


async def finalize_stopped_run(db: AsyncSession, run_id: UUID, outcome: str) -> TestRun:
    run = await db.get(TestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    run_repo = RunRepository(db)
    result = await db.execute(
        select(GameEvent).where(GameEvent.run_id == run_id).order_by(GameEvent.tick_number.desc()).limit(1)
    )
    latest_event = result.scalar_one_or_none()
    if latest_event is not None:
        await run_repo.update(
            run,
            final_hp=latest_event.health,
            final_armor=latest_event.armor,
            total_kills=latest_event.kill_count,
            secrets_found=latest_event.secret_count,
            total_items_collected=latest_event.item_count,
        )

    count_result = await db.execute(select(GameEvent).where(GameEvent.run_id == run_id))
    events = list(count_result.scalars().all())
    completed_at = datetime.now(UTC)
    fields: dict[str, Any] = {
        "total_actions_taken": sum(1 for event in events if event.action_taken),
        "total_llm_calls": sum(1 for event in events if event.llm_reasoning),
        "status": "cancelled" if outcome == "cancelled" else "completed",
        "outcome": outcome,
        "completed_at": completed_at,
    }
    if run.started_at:
        fields["duration_seconds"] = int((completed_at - run.started_at).total_seconds())
    await run_repo.update(run, **fields)
    await db.commit()
    await DefectService(db).detect_for_run(run)
    await db.commit()
    try:
        await ReportService(db).generate(run.id)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        refreshed_run = await db.get(TestRun, run.id)
        if refreshed_run is not None:
            await run_repo.update(
                refreshed_run,
                error_message=(refreshed_run.error_message or f"Report generation failed: {exc}"),
            )
            await db.commit()
    await db.refresh(run)
    return run
