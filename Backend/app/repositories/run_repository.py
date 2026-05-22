from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
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

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        wad_file_id: UUID | None = None,
        map_name: str | None = None,
        outcome: str | None = None,
        status: str | None = None,
        difficulty_level: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[TestRun]:
        query = self._filtered_query(
            wad_file_id=wad_file_id,
            map_name=map_name,
            outcome=outcome,
            status=status,
            difficulty_level=difficulty_level,
            created_after=created_after,
            created_before=created_before,
        )
        result = await self.db.execute(query.order_by(TestRun.created_at.desc()).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def count(
        self,
        wad_file_id: UUID | None = None,
        map_name: str | None = None,
        outcome: str | None = None,
        status: str | None = None,
        difficulty_level: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        filtered = self._filtered_query(
            wad_file_id=wad_file_id,
            map_name=map_name,
            outcome=outcome,
            status=status,
            difficulty_level=difficulty_level,
            created_after=created_after,
            created_before=created_before,
        ).subquery()
        result = await self.db.execute(select(func.count()).select_from(filtered))
        return int(result.scalar_one())

    async def get_active(self) -> TestRun | None:
        result = await self.db.execute(
            select(TestRun)
            .where(TestRun.status.in_(("pending", "analyzing", "running")))
            .order_by(TestRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_active_for_wad(self, wad_file_id: UUID) -> bool:
        result = await self.db.execute(
            select(TestRun.id)
            .where(
                TestRun.wad_file_id == wad_file_id,
                TestRun.status.in_(("pending", "analyzing", "running")),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    def _filtered_query(
        self,
        wad_file_id: UUID | None = None,
        map_name: str | None = None,
        outcome: str | None = None,
        status: str | None = None,
        difficulty_level: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> Select[tuple[TestRun]]:
        query = select(TestRun)
        if wad_file_id is not None:
            query = query.where(TestRun.wad_file_id == wad_file_id)
        if map_name:
            query = query.where(TestRun.map_name == map_name.upper())
        if outcome:
            query = query.where(TestRun.outcome == outcome)
        if status:
            query = query.where(TestRun.status == status)
        if difficulty_level is not None:
            query = query.where(TestRun.difficulty_level == difficulty_level)
        if created_after is not None:
            query = query.where(TestRun.created_at >= created_after)
        if created_before is not None:
            query = query.where(TestRun.created_at <= created_before)
        return query
