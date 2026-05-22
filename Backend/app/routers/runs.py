from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.defect_repository import DefectRepository
from app.repositories.agent_decision_repository import AgentDecisionRepository
from app.repositories.game_event_repository import GameEventRepository
from app.repositories.run_repository import RunRepository
from app.serializers.agent_decision_serializers import AgentDecisionOut
from app.serializers.defect_serializers import DefectOut
from app.serializers.game_event_serializers import PositionTrailOut, TraceEntryOut
from app.serializers.run_serializers import RunCompareOut, RunCreate, RunListOut, RunOut
from app.services.run_compare_service import RunCompareService
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["Runs"])


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).create_run(payload)


@router.get("", response_model=RunListOut)
async def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    wad_file_id: UUID | None = None,
    map_name: str | None = None,
    outcome: str | None = None,
    status: str | None = None,
    difficulty_level: int | None = Query(default=None, ge=1, le=5),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> RunListOut:
    repo = RunRepository(db)
    filters = {
        "wad_file_id": wad_file_id,
        "map_name": map_name,
        "outcome": outcome,
        "status": status,
        "difficulty_level": difficulty_level,
        "created_after": created_after,
        "created_before": created_before,
    }
    total = await repo.count(**filters)
    items = await repo.list(limit=limit, offset=offset, **filters)
    return RunListOut(total=total, items=items, offset=offset)


@router.get("/compare", response_model=RunCompareOut)
async def compare_runs(run_a: UUID, run_b: UUID, db: AsyncSession = Depends(get_db)) -> RunCompareOut:
    return await RunCompareService(db).compare(run_a, run_b)


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


@router.delete("/{run_id}", response_model=RunOut)
async def cancel_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.post("/{run_id}/force-stop", response_model=RunOut)
async def force_stop_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.get(
    "/{run_id}/trace",
    response_model=list[TraceEntryOut],
    tags=["Trace"],
    summary="Full ordered action trace",
)
async def get_trace(
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TraceEntryOut]:
    return await GameEventRepository(db).list_trace(run_id, page, page_size)


@router.get(
    "/{run_id}/events",
    response_model=list[TraceEntryOut],
    tags=["Trace"],
    summary="Notable or filtered run events",
)
async def get_events(
    run_id: UUID,
    type: Optional[str] = Query(
        default=None,
        description=(
            "Comma-separated list of event types to filter. "
            "When omitted, this endpoint returns only notable events where event_type != normal. "
            "Use /trace for the full ordered action history. "
            "Valid values: normal, kill, death, damage_taken, item_pickup, "
            "secret_found, map_exit, stuck. "
            "Example: ?type=kill,death,damage_taken"
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[TraceEntryOut]:
    event_types = [value.strip() for value in (type or "").split(",") if value.strip()]
    return await GameEventRepository(db).list_events(run_id, event_types)


@router.get(
    "/{run_id}/decisions",
    response_model=list[AgentDecisionOut],
    tags=["Trace"],
    summary="Full ordered LLM/MCP decision trace",
)
async def get_decisions(
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[AgentDecisionOut]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return await AgentDecisionRepository(db).list_by_run(run_id, page, page_size)


@router.get("/{run_id}/defects", response_model=list[DefectOut], tags=["Reports"])
async def get_defects(run_id: UUID, db: AsyncSession = Depends(get_db)) -> list[DefectOut]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return await DefectRepository(db).list_by_run(run_id)


@router.get("/{run_id}/position-trail", response_model=list[PositionTrailOut], tags=["Trace"])
async def get_position_trail(run_id: UUID, db: AsyncSession = Depends(get_db)) -> list[PositionTrailOut]:
    return await GameEventRepository(db).list_position_trail(run_id)


@router.get(
    "/{run_id}/recording",
    responses={200: {"content": {"video/mp4": {}}, "description": "MP4 recording"}},
    response_class=FileResponse,
)
async def get_recording(run_id: UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if not run.recording_mp4_path:
        if run.failure_category == "pwad_crash" or run.outcome == "pwad_crash":
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                {
                    "error": "recording_not_available",
                    "reason": "No recording exists because the PWAD crashed or failed before gameplay initialized.",
                    "failure_category": run.failure_category or "pwad_crash",
                    "failure_stage": run.failure_stage,
                },
            )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    path = Path(run.recording_mp4_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording file is missing")
    return FileResponse(path, media_type="video/mp4")
