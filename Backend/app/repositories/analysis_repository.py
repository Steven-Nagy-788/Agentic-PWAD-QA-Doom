from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StaticAnalysisResult


class AnalysisRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_wad_and_map(self, wad_id: UUID, map_name: str) -> StaticAnalysisResult | None:
        result = await self.db.execute(
            select(StaticAnalysisResult).where(
                StaticAnalysisResult.wad_file_id == wad_id,
                StaticAnalysisResult.map_name == map_name.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_wad(self, wad_id: UUID) -> list[StaticAnalysisResult]:
        result = await self.db.execute(
            select(StaticAnalysisResult)
            .where(StaticAnalysisResult.wad_file_id == wad_id)
            .order_by(StaticAnalysisResult.map_name)
        )
        return list(result.scalars().all())

    async def upsert(self, analysis: StaticAnalysisResult) -> StaticAnalysisResult:
        existing = await self.get_by_wad_and_map(analysis.wad_file_id, analysis.map_name)
        if existing is None:
            self.db.add(analysis)
            await self.db.flush()
            await self.db.refresh(analysis)
            return analysis

        for key, value in analysis.__dict__.items():
            if not key.startswith("_") and key not in {"id", "wad_file_id", "map_name"}:
                setattr(existing, key, value)
        await self.db.flush()
        await self.db.refresh(existing)
        return existing
