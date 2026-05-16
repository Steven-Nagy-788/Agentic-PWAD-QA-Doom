from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.wad_repository import WadRepository
from app.serializers.analysis_serializers import StaticAnalysisOut
from app.services.analysis_service import AnalysisService

router = APIRouter(tags=["Analysis"])


@router.get("/wads/{wad_id}/analysis", response_model=list[StaticAnalysisOut])
async def get_analysis(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> list[StaticAnalysisOut]:
    wad = await WadRepository(db).get_by_id(wad_id)
    if wad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "WAD not found")
    results = await AnalysisService(db).analyze_wad(wad)
    await db.commit()
    return [
        StaticAnalysisOut.model_validate(result).model_copy(
            update={"map_overview_png_url": f"/wads/{wad_id}/map-png?map_name={result.map_name}"}
        )
        for result in results
    ]
