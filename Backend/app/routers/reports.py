from __future__ import annotations

from pathlib import Path
from uuid import UUID
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.report_repository import ReportRepository
from app.repositories.run_repository import RunRepository
from app.serializers.report_serializers import ReportOut, ReportStatusOut
from app.services.report_service import ReportService

router = APIRouter(prefix="/runs", tags=["Reports"])


@router.get("/{run_id}/report", response_model=ReportOut, response_model_exclude_none=True)
async def get_report(run_id: UUID, db: AsyncSession = Depends(get_db)) -> ReportOut:
    report = await ReportRepository(db).get_by_run(run_id)
    if report is None:
        try:
            report = await ReportService(db).generate(run_id)
            await db.commit()
        except ValueError as exc:
            await db.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Report generation failed: {exc}") from exc
    return report


@router.get("/{run_id}/report/status", response_model=ReportStatusOut)
async def get_report_status(run_id: UUID, db: AsyncSession = Depends(get_db)) -> ReportStatusOut:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    report = await ReportRepository(db).get_by_run(run_id)
    if report is None:
        terminal = run.status in {"completed", "cancelled", "failed"}
        recently_completed = bool(
            terminal
            and run.completed_at
            and (datetime.now(UTC) - run.completed_at).total_seconds() < 120
        )
        return ReportStatusOut(status="generating" if (not terminal or recently_completed) else "missing")
    pdf_available = bool(report.pdf_path and Path(report.pdf_path).exists())
    status_value = report.generation_status
    if status_value == "complete" and not pdf_available:
        status_value = "missing"
    return ReportStatusOut(
        status=status_value,
        report_id=report.id,
        pdf_available=pdf_available,
        pdf_path=report.pdf_path,
        generation_error=report.generation_error,
    )


@router.get(
    "/{run_id}/report/pdf",
    responses={200: {"content": {"application/pdf": {}}, "description": "QA report PDF"}},
    response_class=FileResponse,
)
async def get_report_pdf(run_id: UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    report = await ReportRepository(db).get_by_run(run_id)
    if report is None or not report.pdf_path:
        run = await RunRepository(db).get_by_id(run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        if run.status not in {"completed", "cancelled", "failed"}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report PDF not found")
        try:
            report = await ReportService(db).generate(run_id)
            await db.commit()
        except ValueError as exc:
            await db.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Report PDF generation failed: {exc}") from exc
    path = Path(report.pdf_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report PDF file is missing")
    return FileResponse(path, media_type="application/pdf")
