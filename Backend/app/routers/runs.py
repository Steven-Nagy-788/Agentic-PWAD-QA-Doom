from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.defect_repository import DefectRepository
from app.repositories.game_event_repository import GameEventRepository
from app.repositories.run_repository import RunRepository
from app.serializers.defect_serializers import DefectOut
from app.serializers.game_event_serializers import PositionTrailOut, TraceEntryOut
from app.serializers.run_serializers import RunCreate, RunOut
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["Runs"])


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).create_run(payload)


@router.get("", response_model=list[RunOut])
async def list_runs(limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db)) -> list[RunOut]:
    return await RunRepository(db).list(limit=limit)


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


@router.delete("/{run_id}", response_model=RunOut)
async def cancel_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run_post(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.post("/{run_id}/force-stop", response_model=RunOut)
async def force_stop_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.get("/{run_id}/trace", response_model=list[TraceEntryOut], tags=["Trace"])
async def get_trace(
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TraceEntryOut]:
    return await GameEventRepository(db).list_trace(run_id, page, page_size)


@router.get("/{run_id}/events", response_model=list[TraceEntryOut], tags=["Trace"])
async def get_events(
    run_id: UUID,
    type: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[TraceEntryOut]:
    event_types = [value.strip() for value in (type or "").split(",") if value.strip()]
    return await GameEventRepository(db).list_events(run_id, event_types)


@router.get("/{run_id}/defects", response_model=list[DefectOut], tags=["Reports"])
async def get_defects(run_id: UUID, db: AsyncSession = Depends(get_db)) -> list[DefectOut]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return await DefectRepository(db).list_by_run(run_id)


@router.get("/{run_id}/position-trail", response_model=list[PositionTrailOut], tags=["Trace"])
async def get_position_trail(run_id: UUID, db: AsyncSession = Depends(get_db)) -> list[PositionTrailOut]:
    return await GameEventRepository(db).list_position_trail(run_id)


@router.get("/{run_id}/recording")
async def get_recording(run_id: UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None or not run.recording_mp4_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    path = Path(run.recording_mp4_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording file is missing")
    return FileResponse(path, media_type="video/mp4")
