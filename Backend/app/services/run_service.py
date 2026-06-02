from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.behavior_profiles import PROFILES
from app.models import GameEvent, TestRun
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.config_repository import ConfigRepository
from app.repositories.defect_repository import DefectRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.serializers.run_serializers import RunCreate
from app.services.analysis_service import AnalysisService, player_start_counts
from app.services.defect_service import DefectService
from app.services.mcp_client_service import McpDoomClient, probe_mcp_sse_url
from app.services.report_service import ReportService
from app.services.run_constants import (
    RUN_TASKS,
    _ACTIVE_RUN_LOCK_ID,
)
from app.services.run_loop import agent_run_task
from app.services.run_utils import (
    _bounded_int,
    _ensure_aware,
)

logger = logging.getLogger(__name__)


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
        uses_deathmatch_normalization = start_counts["player_one"] == 0 and start_counts["deathmatch"] > 0
        if uses_deathmatch_normalization and not data.allow_deathmatch_start_normalization:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Map {map_name} has no Player 1 start. It can only run by converting one deathmatch start "
                "into a temporary Player 1 start. Set allow_deathmatch_start_normalization=true to opt in.",
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

        behavior_profile = data.behavior_profile or str(
            runtime_value("default_agent_behavior", self.settings.default_agent_behavior)
        )
        if behavior_profile not in PROFILES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown behavior profile")
        if (analysis.thing_count_enemies or 0) == 0 and behavior_profile == "thorough":
            behavior_profile = "fast"
            logger.info("Map %s has 0 enemies; using 'fast' behavior profile instead of 'thorough'", map_name)
        queue_mode = runtime_value("run_worker_mode", self.settings.run_worker_mode)
        seed = data.seed if data.seed is not None else random.SystemRandom().randint(0, 2_147_483_647)
        run = await self.repo.create(
            TestRun(
                wad_file_id=wad.id,
                static_analysis_id=analysis.id,
                map_name=map_name,
                difficulty_level=data.difficulty_level,
                iwad_used=wad.iwad_required,
                llm_model=str(runtime_value("llm_model", self.settings.llm_model)),
                max_ticks=max_ticks,
                seed=seed,
                start_normalization={
                    "mode": (
                        "deathmatch_to_player_one"
                        if uses_deathmatch_normalization
                        else "multiple_player_starts_to_player_one"
                        if start_counts["player_starts"] > 1
                        else "native_player_one"
                    ),
                    "player_one_starts": start_counts["player_one"],
                    "player_starts": start_counts["player_starts"],
                    "deathmatch_starts": start_counts["deathmatch"],
                },
                behavior_profile=behavior_profile,
                status="queued" if queue_mode else "pending",
            )
        )
        await self.db.commit()
        if queue_mode:
            logger.info("Run %s queued for worker (run_worker_mode=True)", run.id)
        else:
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
        await ReportService(db).mark_error(run.id, str(exc))
        await db.commit()
        refreshed_run = await db.get(TestRun, run.id)
        if refreshed_run is not None:
            await run_repo.update(
                refreshed_run,
                error_message=(refreshed_run.error_message or f"Report generation failed: {exc}"),
            )
            await db.commit()
    await db.refresh(run)
    return run
