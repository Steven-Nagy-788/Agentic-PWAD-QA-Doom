from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.pattern_service import PatternService

router = APIRouter(tags=["Patterns"])


@router.get("/runs/patterns")
async def get_run_patterns(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    return await PatternService(db).get_patterns(wad_id)
