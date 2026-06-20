from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.path_security import resolve_path_within
from app.serializers.wad_serializers import WadFileOut, WadMapOut
from app.services.wad_service import WadService

router = APIRouter(prefix="/wads", tags=["WADs"])


@router.post("/upload", response_model=WadFileOut)
async def upload_wad(
    file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
) -> WadFileOut:
    return await WadService(db).upload(file)


@router.get("", response_model=list[WadFileOut])
async def list_wads(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[WadFileOut]:
    return await WadService(db).list(limit=limit, offset=offset)


@router.get("/maps", response_model=list[WadMapOut])
async def get_all_wad_maps(
    wad_file_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[WadMapOut]:
    return await WadService(db).all_maps(
        wad_file_id=wad_file_id, limit=limit, offset=offset
    )


@router.get("/{wad_id}", response_model=WadFileOut)
async def get_wad(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> WadFileOut:
    return await WadService(db).get(wad_id)


@router.delete("/{wad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wad(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await WadService(db).delete(wad_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{wad_id}/reanalyze",
    response_model=WadFileOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reanalyze_wad(wad_id: UUID, db: AsyncSession = Depends(get_db)) -> WadFileOut:
    return await WadService(db).schedule_reanalysis(wad_id)


@router.get("/{wad_id}/maps", response_model=list[WadMapOut])
async def get_wad_maps(
    wad_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[WadMapOut]:
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
    from app.core.config import get_settings
    from fastapi import HTTPException as _HE

    try:
        resolved = resolve_path_within(path, get_settings().analysis_storage_dir)
    except ValueError:
        raise _HE(status.HTTP_403_FORBIDDEN, "Access denied")
    return FileResponse(resolved, media_type="image/png")
