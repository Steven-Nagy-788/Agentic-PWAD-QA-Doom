from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import GameEvent, StaticAnalysisResult, TestRun
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.serializers.run_serializers import RunCreate
from app.services.analysis_service import AnalysisService, player_start_counts
from app.services.collector_service import CollectorService, normalize_variables
from app.services.defect_service import DefectService
from app.services.gemini_service import GeminiService
from app.services.mcp_client_service import McpDoomClient, normalize_mcp_state
from app.services.prompt_service import render_agent_prompt
from app.services.recording_service import RecordingService, jpeg_b64, png_bytes_to_frame
from app.services.report_service import ReportService
from app.services.websocket_service import websocket_service


RUN_TASKS: dict[UUID, asyncio.Task] = {}
COMPOUND_TELEMETRY_TOOLS = {"explore", "move_to", "aim_and_shoot", "strafe_and_shoot", "retreat"}
OBJECT_ID_TOOLS = {"aim_and_shoot", "strafe_and_shoot", "move_to"}
OBJECT_ID_ALIASES: dict[str, tuple[str, ...]] = {
    "aim_and_shoot": ("object_id", "enemy_id", "target_id", "monster_id"),
    "strafe_and_shoot": ("object_id", "enemy_id", "target_id", "monster_id"),
    "move_to": ("object_id", "target_id", "item_id", "pickup_id", "enemy_id", "monster_id"),
}
TOOL_PARAM_ALLOWLIST: dict[str, set[str]] = {
    "aim_and_shoot": {"object_id", "shots", "max_tics"},
    "strafe_and_shoot": {"object_id", "direction", "shots", "max_tics"},
    "move_to": {"object_id", "max_tics", "use", "stop_on_enemy"},
    "explore": {"max_tics", "stop_on_enemy", "stop_on_item"},
    "retreat": {"tics", "backpedal"},
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
        recorder = RecordingService(str(run.id), fps=max(1.0, get_settings().live_frame_fps))
        gemini = GeminiService()
        total_actions = 0
        total_llm_calls = 0
        last_frame_at = 0.0
        outcome = "timeout"
        latest_event = None
        mcp_client: McpDoomClient | None = None

        try:
            async with McpDoomClient() as mcp:
                mcp_client = mcp
                await mcp.start_game(
                    wad=run.iwad_used,
                    scenario_wad=wad.stored_path,
                    map_name=run.map_name,
                    difficulty=run.difficulty_level,
                    episode_timeout=run.max_ticks,
                )
                await run_repo.update(run, status="running", started_at=datetime.now(UTC))
                await db.commit()

                for tick in range(run.max_ticks):
                    state, screenshot_png = await mcp.get_state()
                    frame = png_bytes_to_frame(screenshot_png)
                    variables = normalize_variables(state)
                    recent = await _recent_trace(db, run.id)
                    llm_input = {
                        "tick": tick,
                        "game_variables": variables,
                        "objects": state.get("objects", [])[:20],
                        "episode_finished": state.get("episode_finished", False),
                        "recent_trace": recent,
                    }
                    decision = await gemini.decide(prompt, llm_input)
                    total_llm_calls += 1
                    response = await _execute_tool(mcp, decision)
                    response_state, response_png = normalize_mcp_state(response)
                    telemetry_frames = _pop_telemetry_frames(response_state)
                    if decision.get("mcp_tool") in COMPOUND_TELEMETRY_TOOLS and not telemetry_frames:
                        decision["recording_fidelity_warning"] = (
                            "MCP tool did not return telemetry_frames; recording contains final decision frames only."
                        )
                    if response_state:
                        if not response_state.get("game_variables") and state.get("game_variables"):
                            response_state["game_variables"] = state["game_variables"]
                        state = response_state
                    if response_png:
                        response_frame = png_bytes_to_frame(response_png)
                        if response_frame is not None:
                            frame = response_frame
                    await _record_telemetry_frames(run.id, tick, telemetry_frames, collector, recorder)
                    total_actions += 1
                    latest_event = await collector.collect(
                        run.id,
                        tick,
                        state,
                        llm_input,
                        decision,
                        _summary(response),
                    )
                    event_screenshot_b64 = None
                    if latest_event.event_type in {"kill", "death", "damage_taken"} and frame is not None:
                        screenshot_path = recorder.save_screenshot(frame, latest_event.id)
                        await collector.attach_screenshot(run.id, latest_event, str(screenshot_path))
                        event_screenshot_b64 = jpeg_b64(frame)
                    recorder.write_frame(frame)
                    await _broadcast_state(run, latest_event, decision, event_screenshot_b64)
                    now = time.monotonic()
                    if frame is not None and now - last_frame_at >= 1 / max(get_settings().live_frame_fps, 0.1):
                        encoded = jpeg_b64(frame)
                        if encoded:
                            await websocket_service.broadcast(
                                run.id,
                                {"type": "frame", "tick": tick, "mime_type": "image/jpeg", "frame_b64": encoded},
                            )
                        last_frame_at = now
                    await db.commit()
                    if latest_event.event_type == "map_exit" or state.get("level_completed") or state.get("next_map"):
                        outcome = "map_completed"
                        break
                    if latest_event.health <= 0:
                        outcome = "player_died"
                        break
                    throttle_seconds = max(0.0, get_settings().llm_throttle_seconds)
                    if throttle_seconds:
                        await websocket_service.broadcast(
                            run.id,
                            {
                                "type": "status",
                                "status": run.status,
                                "phase": "llm_throttle",
                                "message": f"Waiting {throttle_seconds:g}s before next LLM call.",
                                "sleep_seconds": throttle_seconds,
                                "tick": tick,
                            },
                        )
                        await asyncio.sleep(throttle_seconds)
        except asyncio.CancelledError:
            outcome = "cancelled"
            await run_repo.update(run, status="cancelled")
        except Exception as exc:
            outcome = "error"
            await run_repo.update(run, status="failed", error_message=str(exc))
        finally:
            if mcp_client is not None:
                await mcp_client.stop_game()
            recording_path = recorder.finalize()
            completed_at = datetime.now(UTC)
            final_fields: dict[str, Any] = {
                "outcome": outcome,
                "completed_at": completed_at,
                "total_actions_taken": total_actions,
                "total_llm_calls": total_llm_calls,
            }
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
            if run.status in {"completed", "cancelled"}:
                await DefectService(db).detect_for_run(run)
                await ReportService(db).generate(run.id)
                await db.commit()
            await websocket_service.broadcast(run.id, {"type": "state", "status": run.status, "tick": run.max_ticks})
            RUN_TASKS.pop(run.id, None)


async def _execute_tool(mcp: McpDoomClient, decision: dict[str, Any]) -> Any:
    tool = decision.get("mcp_tool") or "explore"
    params = _normalize_mcp_params(tool, dict(decision.get("mcp_params") or {}))
    if tool in OBJECT_ID_TOOLS and "object_id" not in params:
        decision["tool_param_warning"] = f"{tool} requested without an object_id; fallback explore used."
        tool = "explore"
        params = {}
    decision["mcp_tool"] = tool
    decision["mcp_params"] = params
    if tool == "step":
        tool = "take_action"
    if tool == "take_action" and "actions" not in params:
        params = {"actions": params, "tics": 4}
    return await mcp.call_tool(tool, params)


def _normalize_mcp_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    if tool == "step":
        return params

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

    return params


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
        sample_tick = tick * 1000 + index + 1
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
        recorder.write_frame(frame)


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


def _summary(value: Any) -> str:
    if isinstance(value, dict):
        value = {key: val for key, val in value.items() if key != "telemetry_frames"}
    elif isinstance(value, list):
        compact = []
        for item in value:
            if isinstance(item, dict):
                compact.append({key: val for key, val in item.items() if key != "telemetry_frames"})
            else:
                compact.append(item)
        value = compact
    text = str(value)
    return text if len(text) <= 500 else text[:500] + "..."


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
    await ReportService(db).generate(run.id)
    await db.commit()
    await db.refresh(run)
    return run
