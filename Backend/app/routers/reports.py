from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.repositories.report_repository import ReportRepository
from app.repositories.run_repository import RunRepository
from app.serializers.report_serializers import ReportOut, ReportStatusOut
from app.services.report_service import ReportService

router = APIRouter(prefix="/runs", tags=["Reports"])


@router.get("/{run_id}/report", response_model=ReportOut, response_model_exclude_none=True)
async def get_report(run_id: UUID, db: AsyncSession = Depends(get_db)) -> ReportOut:
    report = await ReportRepository(db).get_by_run(run_id)
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if report is None or (
        not report.pdf_path and run.status in {"completed", "cancelled", "failed"}
    ):
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
        if run.error_message and "Report generation failed:" in run.error_message:
            return ReportStatusOut(status="error", generation_error=run.error_message)
        return ReportStatusOut(status="missing" if terminal else "pending")
    pdf_available = bool(report.pdf_path and Path(get_settings().report_storage_dir.parent, report.pdf_path).exists())
    status_value = report.generation_status
    if status_value == "complete" and not pdf_available:
        status_value = "missing"
    if status_value == "generating" and not pdf_available and run.status in {"completed", "cancelled", "failed"}:
        status_value = "missing"
    return ReportStatusOut(
        status=status_value,
        report_id=report.id,
        pdf_available=pdf_available,
        pdf_url=f"/runs/{run_id}/report/pdf" if pdf_available else None,
        generation_error=report.generation_error,
    )


@router.post("/{run_id}/report/regenerate", response_model=ReportOut, response_model_exclude_none=True)
async def regenerate_report(run_id: UUID, db: AsyncSession = Depends(get_db)) -> ReportOut:
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if run.status not in {"completed", "cancelled", "failed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Report regeneration requires a terminal run")
    report_repo = ReportRepository(db)
    report = await report_repo.get_by_run(run_id)
    if report is not None:
        await report_repo.update(report, pdf_path=None, generation_status="generating", generation_error=None)
    await run_repo.update(run, report_pdf_path=None)
    await db.commit()
    try:
        return await ReportService(db).generate(run_id)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Report regeneration failed: {exc}") from exc


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
    if not report.pdf_path:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Report generation is still in progress, try again later")
    path = Path(get_settings().report_storage_dir.parent, report.pdf_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report PDF file is missing")
    resolved = path.resolve()
    allowed = get_settings().report_storage_dir.resolve()
    if not str(resolved).startswith(str(allowed)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return FileResponse(path, media_type="application/pdf")
