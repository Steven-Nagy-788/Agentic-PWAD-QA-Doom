from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.serializers.wad_serializers import WadFileOut, WadMapOut
from app.services.wad_service import WadService

router = APIRouter(prefix="/wads", tags=["WADs"])


@router.post("/upload", response_model=WadFileOut)
async def upload_wad(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)) -> WadFileOut:
    return await WadService(db).upload(file)


@router.get("/maps", response_model=list[WadMapOut])
async def get_all_wad_maps(
    wad_file_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[WadMapOut]:
    return await WadService(db).all_maps(wad_file_id=wad_file_id, limit=limit, offset=offset)


@router.get("/{wad_id}", response_model=WadFileOut)
async def get_wad(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> WadFileOut:
    return await WadService(db).get(wad_id)


@router.get("/{wad_id}/maps", response_model=list[WadMapOut])
async def get_wad_maps(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> list[WadMapOut]:
    return await WadService(db).maps(wad_id)


@router.get(
    "/{wad_id}/map-png",
    responses={200: {"content": {"image/png": {}}, "description": "Map overview PNG"}},
    response_class=FileResponse,
)
async def get_map_png(
    wad_id: UUID,
    map_name: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    path = await WadService(db).map_png_path(wad_id, map_name)
    return FileResponse(path, media_type="image/png")
