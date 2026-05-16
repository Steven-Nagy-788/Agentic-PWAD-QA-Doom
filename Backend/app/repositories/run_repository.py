from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TestRun


class RunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, run: TestRun) -> TestRun:
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def update(self, run: TestRun, **fields: object) -> TestRun:
        for key, value in fields.items():
            setattr(run, key, value)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def get_by_id(self, run_id: UUID) -> TestRun | None:
        return await self.db.get(TestRun, run_id)

    async def list(self, limit: int = 100) -> list[TestRun]:
        result = await self.db.execute(select(TestRun).order_by(TestRun.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_active(self) -> TestRun | None:
        result = await self.db.execute(
            select(TestRun)
            .where(TestRun.status.in_(("pending", "analyzing", "running")))
            .order_by(TestRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
