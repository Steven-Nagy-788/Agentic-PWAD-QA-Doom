from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.report_repository import ReportRepository
from app.serializers.report_serializers import ReportOut
from app.services.report_service import ReportService

router = APIRouter(prefix="/runs", tags=["Reports"])


@router.get("/{run_id}/report", response_model=ReportOut)
async def get_report(run_id: UUID, db: AsyncSession = Depends(get_db)) -> ReportOut:
    report = await ReportRepository(db).get_by_run(run_id)
    if report is None:
        report = await ReportService(db).generate(run_id)
        await db.commit()
    return report


@router.get("/{run_id}/report/pdf")
async def get_report_pdf(run_id: UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    report = await ReportRepository(db).get_by_run(run_id)
    if report is None or not report.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report PDF not found")
    path = Path(report.pdf_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report PDF file is missing")
    return FileResponse(path, media_type="application/pdf")
