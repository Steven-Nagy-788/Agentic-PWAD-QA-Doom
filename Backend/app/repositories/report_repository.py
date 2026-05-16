from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TestReport


class ReportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_run(self, run_id: UUID) -> TestReport | None:
        result = await self.db.execute(select(TestReport).where(TestReport.run_id == run_id))
        return result.scalar_one_or_none()

    async def create(self, report: TestReport) -> TestReport:
        self.db.add(report)
        await self.db.flush()
        await self.db.refresh(report)
        return report

    async def update(self, report: TestReport, **fields: object) -> TestReport:
        for key, value in fields.items():
            setattr(report, key, value)
        await self.db.flush()
        await self.db.refresh(report)
        return report
