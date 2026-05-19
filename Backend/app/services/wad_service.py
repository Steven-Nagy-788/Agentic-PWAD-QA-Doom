from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import WadFile
from app.repositories.wad_repository import WadRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.serializers.wad_serializers import WadMapOut
from app.services.analysis_service import (
    AnalysisService,
    detect_iwad_requirement,
    detect_map_names,
    map_metadata_for_wad,
    player_start_counts,
)


class WadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = WadRepository(db)

    async def upload(self, file: UploadFile) -> WadFile:
        data = await file.read()
        self._validate_binary(data)
        sha256_hash = hashlib.sha256(data).hexdigest()
        existing = await self.repo.get_by_hash(sha256_hash)
        if existing is not None:
            return existing

        self.settings.wad_storage_dir.mkdir(parents=True, exist_ok=True)
        wad_id = uuid.uuid4()
        stored_path = self.settings.wad_storage_dir / f"{wad_id}.wad"
        stored_path.write_bytes(data)

        try:
            map_names = detect_map_names(str(stored_path))
        except Exception as exc:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse WAD maps: {exc}") from exc

        if not map_names:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "PWAD contains no supported Doom maps")

        start_counts = {
            map_name: player_start_counts(str(stored_path), map_name)
            for map_name in map_names
        }
        unplayable_maps = [
            map_name
            for map_name, counts in start_counts.items()
            if counts["player_one"] == 0 and counts["deathmatch"] == 0
        ]
        if unplayable_maps:
            stored_path.unlink(missing_ok=True)
            maps = ", ".join(
                f"{map_name} (no Player 1 or deathmatch starts)"
                for map_name in unplayable_maps
            )
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Map(s) {maps} are not valid for QA runs. "
                "Each map must have a Player 1 start or a deathmatch start that can be normalized.",
            )

        wad_file = WadFile(
            id=wad_id,
            original_filename=file.filename or "upload.wad",
            stored_path=str(stored_path.resolve()),
            file_size_bytes=len(data),
            sha256_hash=sha256_hash,
            validation_status="valid_pwad",
            detected_maps=map_names,
            iwad_required=detect_iwad_requirement(map_names),
        )
        await self.repo.create(wad_file)
        await AnalysisService(self.db).analyze_wad(wad_file)
        await self.db.commit()
        await self.db.refresh(wad_file)
        return wad_file

    @staticmethod
    def _validate_binary(data: bytes) -> None:
        if len(data) < 12:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is too small to be a WAD")
        magic = data[:4]
        if magic == b"IWAD":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "IWAD files are not accepted; upload a PWAD")
        if magic != b"PWAD":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid WAD header; expected PWAD")
        if b"TEXTMAP" in data[: min(len(data), 1024 * 1024)] or b"TEXTMAP" in data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "UDMF maps are not supported")

    async def get(self, wad_id: uuid.UUID) -> WadFile:
        wad = await self.repo.get_by_id(wad_id)
        if wad is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "WAD not found")
        return wad

    async def map_png_path(self, wad_id: uuid.UUID, map_name: str | None) -> Path:
        wad = await self.get(wad_id)
        selected = (map_name or (wad.detected_maps or [""])[0]).upper()
        analysis = await AnalysisService(self.db).analyze_map(wad, selected)
        if not analysis.map_overview_png_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Map overview PNG not found")
        return Path(analysis.map_overview_png_path)

    async def maps(self, wad_id: uuid.UUID) -> list[WadMapOut]:
        wad = await self.get(wad_id)
        return await self._maps_for_wad(wad)

    async def all_maps(
        self,
        wad_file_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WadMapOut]:
        if wad_file_id is not None:
            return await self.maps(wad_file_id)

        maps: list[WadMapOut] = []
        for wad in await self.repo.list(limit=limit, offset=offset):
            maps.extend(await self._maps_for_wad(wad))
        return maps

    async def _maps_for_wad(self, wad: WadFile) -> list[WadMapOut]:
        repo = AnalysisRepository(self.db)
        metadata = map_metadata_for_wad(wad.stored_path, wad.original_filename)
        maps = []
        for map_name in wad.detected_maps or []:
            analysis = await repo.get_by_wad_and_map(wad.id, map_name)
            map_metadata = metadata.get(map_name, {})
            maps.append(
                WadMapOut(
                    wad_file_id=wad.id,
                    map_name=map_name,
                    map_title=analysis.map_title if analysis else map_metadata.get("map_title"),
                    map_display_name=(
                        analysis.map_display_name if analysis else map_metadata.get("map_display_name")
                    ),
                    map_title_source=(
                        analysis.map_title_source if analysis else map_metadata.get("map_title_source")
                    ),
                    iwad_required=wad.iwad_required,
                    analyzed=analysis is not None,
                    thing_count_enemies=analysis.thing_count_enemies if analysis else None,
                    thing_count_items=analysis.thing_count_items if analysis else None,
                    secret_sector_count=analysis.secret_sector_count if analysis else None,
                    estimated_difficulty=analysis.estimated_difficulty if analysis else None,
                    spawn_summary_by_skill=analysis.spawn_summary_by_skill if analysis else None,
                    map_overview_png_url=(
                        f"/wads/{wad.id}/map-png?map_name={map_name}" if analysis and analysis.map_overview_png_path else None
                    ),
                )
            )
        return maps
