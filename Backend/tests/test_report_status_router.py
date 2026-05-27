from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.routers.reports import get_report_status


@pytest.mark.asyncio
async def test_report_status_missing_for_terminal_run_without_report_row() -> None:
    run_id = uuid4()
    with (
        patch("app.routers.reports.RunRepository") as run_repo_cls,
        patch("app.routers.reports.ReportRepository") as report_repo_cls,
    ):
        run_repo_cls.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(status="completed", error_message=None))
        report_repo_cls.return_value.get_by_run = AsyncMock(return_value=None)

        status = await get_report_status(run_id, AsyncMock())

    assert status.status == "missing"
    assert status.pdf_available is False


@pytest.mark.asyncio
async def test_report_status_pending_for_live_run_without_report_row() -> None:
    run_id = uuid4()
    with (
        patch("app.routers.reports.RunRepository") as run_repo_cls,
        patch("app.routers.reports.ReportRepository") as report_repo_cls,
    ):
        run_repo_cls.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(status="running", error_message=None))
        report_repo_cls.return_value.get_by_run = AsyncMock(return_value=None)

        status = await get_report_status(run_id, AsyncMock())

    assert status.status == "pending"


@pytest.mark.asyncio
async def test_report_status_exposes_terminal_generation_error_without_report_row() -> None:
    run_id = uuid4()
    with (
        patch("app.routers.reports.RunRepository") as run_repo_cls,
        patch("app.routers.reports.ReportRepository") as report_repo_cls,
    ):
        run_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=SimpleNamespace(status="failed", error_message="Report generation failed: disk full")
        )
        report_repo_cls.return_value.get_by_run = AsyncMock(return_value=None)

        status = await get_report_status(run_id, AsyncMock())

    assert status.status == "error"
    assert status.generation_error == "Report generation failed: disk full"
