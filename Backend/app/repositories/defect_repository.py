from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Defect


class DefectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, defect: Defect) -> Defect:
        values = {
            column.name: getattr(defect, column.name)
            for column in Defect.__table__.columns
            if column.name != "id" and getattr(defect, column.name) is not None
        }
        statement = (
            insert(Defect)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["run_id", "defect_type", "detected_at_tick"])
            .returning(Defect.id)
        )
        result = await self.db.execute(statement)
        defect_id = result.scalar_one_or_none()
        if defect_id is not None:
            created = await self.db.get(Defect, defect_id)
            assert created is not None
            return created

        existing = await self.db.execute(
            select(Defect).where(
                Defect.run_id == values["run_id"],
                Defect.defect_type == values["defect_type"],
                Defect.detected_at_tick == values["detected_at_tick"],
            )
        )
        return existing.scalar_one()

    async def list_by_run(self, run_id: UUID) -> list[Defect]:
        result = await self.db.execute(select(Defect).where(Defect.run_id == run_id).order_by(Defect.severity))
        return list(result.scalars().all())
