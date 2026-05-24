from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import AgentDecision, AgentPositionTrail, Defect, GameEvent, StaticAnalysisResult, TestReport, TestRun
from app.repositories.agent_decision_repository import AgentDecisionRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.config_repository import ConfigRepository
from app.repositories.defect_repository import DefectRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.serializers.run_serializers import RunCreate
from app.services.analysis_service import AnalysisService, player_start_counts, selected_skill_spawn_summary
from app.services.collector_service import CollectorService
from app.services.defect_service import DefectService
from app.services.gemini_service import GeminiService
from app.services.mcp_client_service import McpDoomClient, McpStartupError, McpToolTimeoutError, normalize_mcp_state, probe_mcp_sse_url
from app.services.prompt_service import render_agent_prompt
from app.services.recording_service import RecordingService, jpeg_b64, png_bytes_to_frame
from app.services.report_service import ReportService
from app.services.run_constants import (
    DIRECTOR_POLL_SECONDS,
    DIRECTOR_STUCK_POLL_THRESHOLD,
    DIRECTOR_STUCK_RECOVERY_LIMIT,
    PWAD_CRASH_CATEGORY,
    RUN_TASKS,
    _ACTIVE_RUN_LOCK_ID,
)
from app.services.run_loop import agent_run_task
from app.services.run_memory import RunMemoryService
from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _compact_mcp_output,
    _ensure_aware,
    _json_safe,
)
from app.services.websocket_service import websocket_service


class RunService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = RunRepository(db)

    async def create_run(self, data: RunCreate) -> TestRun:
        wad = await WadRepository(self.db).get_by_id(data.wad_file_id)
        if wad is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "WAD not found")
        map_name = data.map_name.upper()
        if map_name not in (wad.detected_maps or []):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "map_name is not in wad_files.detected_maps")
        start_counts = await asyncio.to_thread(player_start_counts, wad.stored_path, map_name)
        if start_counts["player_one"] == 0 and start_counts["deathmatch"] == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Map {map_name} has no Player 1 or deathmatch start. "
                "QA runs need a start position that can be normalized for single-player.",
            )

        async with SessionLocal() as analysis_db:
            analysis = await AnalysisRepository(analysis_db).get_by_wad_and_map(wad.id, map_name)
            if analysis is None:
                analysis = await AnalysisService(analysis_db).analyze_map(wad, map_name)

        runtime_overrides = await ConfigRepository(self.db).get_all()

        def runtime_value(key: str, fallback: Any = None) -> Any:
            return runtime_overrides.get(key, getattr(self.settings, key, fallback))

        default_run_ticks = _bounded_int(runtime_value("default_run_ticks", self.settings.default_run_ticks), self.settings.default_run_ticks, lower=1)
        max_run_ticks = _bounded_int(runtime_value("max_run_ticks", self.settings.max_run_ticks), self.settings.max_run_ticks, lower=1)
        max_ticks = max(1, min(data.max_ticks or default_run_ticks, max_run_ticks))
        mcp_health = await probe_mcp_sse_url()
        if not mcp_health.get("reachable"):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {
                    "error": "mcp_unreachable",
                    "message": "mcp-doom is not reachable. Start the MCP server before creating a run.",
                    "health": mcp_health,
                },
            )

        await self.db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _ACTIVE_RUN_LOCK_ID})
        await self._fail_orphaned_active_runs()
        active_run = await self.repo.get_active()
        if active_run is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Another test run is already active: {active_run.id}",
            )

        behavior_profile = await RunMemoryService(self.db).recommend_behavior_profile(
            wad.id,
            map_name,
            data.behavior_profile,
            str(runtime_value("default_agent_behavior", self.settings.default_agent_behavior)),
        )
        run = await self.repo.create(
            TestRun(
                wad_file_id=wad.id,
                static_analysis_id=analysis.id,
                map_name=map_name,
                difficulty_level=data.difficulty_level,
                iwad_used=wad.iwad_required,
                llm_model=str(runtime_value("llm_model", self.settings.llm_model)),
                max_ticks=max_ticks,
                behavior_profile=behavior_profile,
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

        await finalize_stopped_run(self.db, run_id, outcome="cancelled")
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
        await _mark_run_orphaned(self.repo, active, "Orphaned by missing in-process run task.")


async def fail_orphaned_active_runs(db: AsyncSession, reason: str = "Orphaned by server restart") -> int:
    repo = RunRepository(db)
    result = await db.execute(
        select(TestRun)
        .where(TestRun.status.in_(("pending", "analyzing", "running")))
        .order_by(TestRun.created_at)
    )
    now = datetime.now(UTC)
    failed = 0
    for run in result.scalars().all():
        task = RUN_TASKS.get(run.id)
        if task is not None and not task.done():
            continue
        started_at = _ensure_aware(run.started_at or run.created_at)
        stale = started_at is None or started_at < now - timedelta(minutes=5)
        if task is None or stale:
            await _mark_run_orphaned(repo, run, reason)
            failed += 1
    return failed


async def _mark_run_orphaned(repo: RunRepository, run: TestRun, reason: str) -> None:
    await repo.update(
        run,
        status="failed",
        outcome="error",
        error_message=reason,
        failure_category="infrastructure",
        failure_stage="orphaned_run",
        failure_summary=reason,
        failure_diagnostics={
            "run_task_present": run.id in RUN_TASKS,
            "server_time": datetime.now(UTC).isoformat(),
        },
        completed_at=datetime.now(UTC),
    )


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


# ---------------------------------------------------------------------------
# Director (async player mode) — not used in the current lockstep loop
# ---------------------------------------------------------------------------

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
    from app.services.collector_service import normalize_variables

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
