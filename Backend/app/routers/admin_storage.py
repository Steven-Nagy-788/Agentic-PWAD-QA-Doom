from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.path_security import unlink_if_within
from app.models import NotableEventScreenshot, TestRun
from app.repositories.run_repository import RunRepository

router = APIRouter(prefix="/admin/storage", tags=["Admin Storage"])


@router.get("/stats")
async def storage_stats() -> dict[str, object]:
    settings = get_settings()
    buckets = {
        "wads": settings.wad_storage_dir,
        "analysis": settings.analysis_storage_dir,
        "reports": settings.report_storage_dir,
        "recordings": settings.recording_storage_dir,
        "screenshots": settings.screenshot_storage_dir,
    }
    by_type = {name: await asyncio.to_thread(_path_stats, path) for name, path in buckets.items()}
    return {
        "total_bytes": sum(item["total_bytes"] for item in by_type.values()),
        "total_files": sum(item["file_count"] for item in by_type.values()),
        "by_type": by_type,
    }


@router.delete("/runs/{run_id}")
async def purge_run_storage(run_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    deleted = await _purge_run_files(db, run)
    await db.commit()
    return {"run_id": str(run_id), "deleted_files": deleted}


@router.delete("/cleanup")
async def cleanup_old_storage(
    older_than_days: int = Query(default=30, ge=1),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = await db.execute(
        select(TestRun).where(
            TestRun.completed_at.is_not(None),
            TestRun.completed_at < cutoff,
        )
    )
    deleted = 0
    runs = list(result.scalars().all())
    for run in runs:
        deleted += await _purge_run_files(db, run)
    await db.commit()
    return {"runs_checked": len(runs), "deleted_files": deleted, "older_than_days": older_than_days}


def _path_stats(path: Path) -> dict[str, int | str]:
    total = 0
    count = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                count += 1
                total += item.stat().st_size
    return {"path": str(path), "file_count": count, "total_bytes": total}


async def _purge_run_files(db: AsyncSession, run: TestRun) -> int:
    deleted = 0
    settings = get_settings()
    if run.recording_mp4_path:
        recording_path = Path(run.recording_mp4_path)
        for path in (recording_path, recording_path.with_name(f"{recording_path.stem}.source.mp4")):
            if unlink_if_within(path, settings.recording_storage_dir):
                deleted += 1
        run.recording_mp4_path = None
    result = await db.execute(select(NotableEventScreenshot).where(NotableEventScreenshot.run_id == run.id))
    for screenshot in result.scalars().all():
        if unlink_if_within(screenshot.screenshot_path, settings.screenshot_storage_dir):
            deleted += 1
        await db.delete(screenshot)
    await db.flush()
    return deleted
