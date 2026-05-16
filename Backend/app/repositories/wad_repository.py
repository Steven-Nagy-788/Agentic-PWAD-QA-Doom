from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WadFile


class WadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, wad_id: UUID) -> WadFile | None:
        return await self.db.get(WadFile, wad_id)

    async def get_by_hash(self, sha256_hash: str) -> WadFile | None:
        result = await self.db.execute(select(WadFile).where(WadFile.sha256_hash == sha256_hash))
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[WadFile]:
        result = await self.db.execute(
            select(WadFile).order_by(WadFile.uploaded_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, wad_file: WadFile) -> WadFile:
        self.db.add(wad_file)
        await self.db.flush()
        await self.db.refresh(wad_file)
        return wad_file
