"""Finalization logic for the lockstep agent run loop.

Handles post-run cleanup: stop MCP game, finalize recording, compute metrics,
run defect detection, persist spatial memory, generate PDF report, update DB,
and cleanup WebSocket connections.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.types import LockstepState
from app.models import Defect, GameEvent, TestRun
from app.repositories.defect_repository import DefectRepository
from app.repositories.run_repository import RunRepository
from app.services.defect_service import DefectService
from app.services.gemini_service import GeminiService
from app.services.mcp_client_service import McpDoomClient
from app.services.recording_service import RecordingService
from app.services.report_service import ReportService
from app.services.run_constants import RUN_TASKS
from app.services.run_memory import RunMemoryService
from app.services.run_tracking import (
    _lockstep_progress_metrics,
    _lockstep_quality_flags,
)
from app.services.run_utils import _json_safe, _normalize_run_outcome
from app.services.websocket_service import websocket_service


logger = logging.getLogger(__name__)


async def finalize_run(
    run_id: UUID,
    *,
    outcome: str,
    mcp_client: McpDoomClient | None,
    recorder: RecordingService,
    lockstep_state: LockstepState,
    total_actions: int,
    total_llm_calls: int,
    latest_event: Any | None,
    failure_fields: dict[str, Any],
    wad_file_id: UUID,
    map_name: str,
    max_ticks: int,
    gemini: GeminiService,
) -> None:
    """Finalize a run after the main loop exits (normal or error).

    This function handles all cleanup in the `finally` block:
    1. Stop MCP game
    2. Finalize recording + validate
    3. Compute progress metrics + quality flags
    4. Update run in DB
    5. Broadcast recording/quality status
    6. Run defect detection
    7. Broadcast defects
    8. Persist spatial memory + hypotheses
    9. Generate PDF report
    10. Cleanup
    """
    # 1. Stop MCP game
    if mcp_client is not None:
        await mcp_client.stop_game()

    # 2. Finalize recording
    outcome = _normalize_run_outcome(outcome)
    recording_path = recorder.finalize()
    recording_metadata = recorder.validate(recording_path, outcome=outcome)

    # 3. Compute metrics
    progress_metrics = _lockstep_progress_metrics(lockstep_state)
    agent_quality_flags = _lockstep_quality_flags(lockstep_state, recording_metadata)
    completed_at = datetime.now(UTC)

    # 4. Build final fields
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
                "total_items_collected": (latest_event.item_count or 0)
                + sum(
                    1
                    for value in (
                        lockstep_state.get("completed_object_ids") or {}
                    ).values()
                    if isinstance(value, dict) and value.get("target_type") == "weapon"
                ),
            }
        )

    # 5. Update DB + broadcast
    async with SessionLocal() as db:
        run_orm = await db.get(TestRun, run_id)
        if run_orm is None:
            RUN_TASKS.pop(run_id, None)
            return
        run_repo = RunRepository(db)
        run_started_at = run_orm.started_at
        if run_orm.status not in {"failed", "cancelled"}:
            final_fields["status"] = "completed"
        if run_started_at:
            final_fields["duration_seconds"] = int(
                (completed_at - run_started_at).total_seconds()
            )
        await run_repo.update(run_orm, **final_fields)
        await db.commit()
        await websocket_service.broadcast(
            run_id,
            {"type": "recording_status", "metadata": _json_safe(recording_metadata)},
        )
        await websocket_service.broadcast(
            run_id,
            {
                "type": "quality_summary",
                "progress_metrics": _json_safe(progress_metrics),
                "agent_quality_flags": _json_safe(agent_quality_flags),
            },
        )

        # 6-7. Defect detection + broadcast
        if run_orm.status in {"completed", "cancelled", "failed"}:
            try:
                await DefectService(db, gemini_service=gemini).detect_for_run(run_orm)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning("Defect detection failed for run %s: %s", run_id, exc)
            for defect in await DefectRepository(db).list_by_run(run_id):
                await websocket_service.broadcast(
                    run_id,
                    {
                        "type": "defect",
                        "defect_type": defect.defect_type,
                        "fingerprint": defect.fingerprint,
                        "title": defect.title,
                        "severity": defect.severity,
                        "detected_at_tick": defect.detected_at_tick,
                    },
                )

            # 8. Persist spatial memory + hypotheses
            try:
                events_result = await db.execute(
                    select(GameEvent).where(GameEvent.run_id == run_id)
                )
                run_events = list(events_result.scalars().all())
                defects_result = await db.execute(
                    select(Defect).where(Defect.run_id == run_id)
                )
                run_defects = list(defects_result.scalars().all())
                memory_svc = RunMemoryService(db)
                await memory_svc.persist_spatial_memory(
                    run_id=run_id,
                    wad_file_id=wad_file_id,
                    map_name=map_name,
                    events=run_events,
                    defects=run_defects,
                )
                hyp_list = list(lockstep_state.get("hypotheses") or [])
                await memory_svc.persist_hypotheses(
                    run_id=run_id,
                    wad_file_id=wad_file_id,
                    map_name=map_name,
                    in_run_hypotheses=hyp_list,
                    agent_quality_flags=agent_quality_flags,
                )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning(
                    "Reviewer analytics persistence failed for run %s: %s", run_id, exc
                )

            # 9. Generate PDF report
            try:
                await websocket_service.broadcast(
                    run_id, {"type": "report_status", "status": "generating"}
                )
                await ReportService(db).generate(run_id)
                await db.commit()
                await websocket_service.broadcast(
                    run_id, {"type": "report_status", "status": "complete"}
                )
            except Exception as exc:
                await db.rollback()
                await ReportService(db).mark_error(run_id, str(exc))
                await db.commit()
                await websocket_service.broadcast(
                    run_id,
                    {"type": "report_status", "status": "error", "error": str(exc)},
                )
                refreshed_run = await db.get(TestRun, run_id)
                if refreshed_run is not None:
                    await RunRepository(db).update(
                        refreshed_run,
                        error_message=(
                            refreshed_run.error_message
                            or f"Report generation failed: {exc}"
                        ),
                    )
                    await db.commit()

        # 10. Final broadcast + cleanup
        await websocket_service.broadcast(
            run_id, {"type": "state", "status": run_orm.status, "tick": max_ticks}
        )
        RUN_TASKS.pop(run_id, None)
        await websocket_service.cleanup_run(run_id)
