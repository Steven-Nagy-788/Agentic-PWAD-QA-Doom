from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import NotableEventScreenshot, TestRun
from app.core.config import get_settings
from app.models import WadFile
from app.repositories.wad_repository import WadRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.run_repository import RunRepository
from app.serializers.wad_serializers import WadMapOut
from app.services.analysis_service import (
    AnalysisService,
    detect_iwad_requirement,
    detect_map_names,
    map_bounds_for_wad,
    map_metadata_for_wad,
    player_start_counts,
)


class WadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = WadRepository(db)

    async def upload(self, file: UploadFile) -> WadFile:
        self.settings.wad_storage_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.settings.wad_storage_dir / f".{uuid.uuid4()}.upload"
        digest = hashlib.sha256()
        size = 0
        header = b""
        previous_tail = b""
        try:
            with temp_path.open("wb") as staged:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_wad_upload_bytes:
                        raise HTTPException(
                            status.HTTP_413_CONTENT_TOO_LARGE,
                            f"WAD exceeds the {self.settings.max_wad_upload_bytes}-byte upload limit",
                        )
                    if len(header) < 12:
                        header += chunk[: 12 - len(header)]
                        if len(header) >= 4:
                            self._validate_binary(header, require_full_header=False)
                    if b"TEXTMAP" in previous_tail + chunk:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST, "UDMF maps are not supported")
                    previous_tail = chunk[-6:]
                    digest.update(chunk)
                    staged.write(chunk)
            self._validate_binary(header)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        sha256_hash = digest.hexdigest()
        existing = await self.repo.get_by_hash(sha256_hash)
        if existing is not None:
            temp_path.unlink(missing_ok=True)
            return existing

        wad_id = uuid.uuid4()
        stored_path = self.settings.wad_storage_dir / f"{wad_id}.wad"
        temp_path.replace(stored_path)

        try:
            map_names = await asyncio.to_thread(detect_map_names, str(stored_path))
        except Exception as exc:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse WAD maps: {exc}") from exc

        if not map_names:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "PWAD contains no supported Doom maps")

        count_results = await asyncio.gather(
            *(asyncio.to_thread(player_start_counts, str(stored_path), map_name) for map_name in map_names)
        )
        start_counts = dict(zip(map_names, count_results))
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
            file_size_bytes=size,
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
    def _validate_binary(data: bytes, *, require_full_header: bool = True) -> None:
        if require_full_header and len(data) < 12:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is too small to be a WAD")
        if len(data) < 4:
            return
        magic = data[:4]
        if magic == b"IWAD":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "IWAD files are not accepted; upload a PWAD")
        if magic != b"PWAD":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid WAD header; expected PWAD")

    async def get(self, wad_id: uuid.UUID) -> WadFile:
        wad = await self.repo.get_by_id(wad_id)
        if wad is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "WAD not found")
        return wad

    async def list(self, limit: int = 100, offset: int = 0) -> list[WadFile]:
        return await self.repo.list(limit=limit, offset=offset)

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

    async def delete(self, wad_id: uuid.UUID) -> None:
        wad = await self.get(wad_id)
        if await RunRepository(self.db).has_active_for_wad(wad_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete a WAD while a run is pending or running")

        analyses = await AnalysisRepository(self.db).list_by_wad(wad_id)
        run_result = await self.db.execute(select(TestRun).where(TestRun.wad_file_id == wad_id))
        runs = list(run_result.scalars().all())
        screenshot_result = await self.db.execute(
            select(NotableEventScreenshot).where(NotableEventScreenshot.run_id.in_([run.id for run in runs]))
        )
        for screenshot in screenshot_result.scalars().all():
            Path(screenshot.screenshot_path).unlink(missing_ok=True)
        for run in runs:
            if run.recording_mp4_path:
                recording_path = Path(run.recording_mp4_path)
                recording_path.unlink(missing_ok=True)
                recording_path.with_name(f"{recording_path.stem}.source.mp4").unlink(missing_ok=True)
            await self.db.delete(run)
        for analysis in analyses:
            if analysis.map_overview_png_path:
                Path(analysis.map_overview_png_path).unlink(missing_ok=True)
            await self.db.delete(analysis)
        Path(wad.stored_path).unlink(missing_ok=True)
        await self.db.delete(wad)
        await self.db.commit()

    async def schedule_reanalysis(self, wad_id: uuid.UUID) -> WadFile:
        wad = await self.get(wad_id)
        asyncio.create_task(reanalyze_wad_task(wad_id))
        return wad

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
        metadata = await asyncio.to_thread(map_metadata_for_wad, wad.stored_path, wad.original_filename)
        maps = []
        for map_name in wad.detected_maps or []:
            analysis = await repo.get_by_wad_and_map(wad.id, map_name)
            map_metadata = metadata.get(map_name, {})
            bounds = await self._map_bounds(wad, map_name, analysis)
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
                    map_min_x=bounds.get("min_x") if bounds else None,
                    map_max_x=bounds.get("max_x") if bounds else None,
                    map_min_y=bounds.get("min_y") if bounds else None,
                    map_max_y=bounds.get("max_y") if bounds else None,
                    map_width_units=analysis.map_width_units if analysis else None,
                    map_height_units=analysis.map_height_units if analysis else None,
                )
            )
        return maps

    async def _map_bounds(self, wad: WadFile, map_name: str, analysis) -> dict[str, int] | None:
        bounds = _analysis_map_bounds(analysis)
        if bounds:
            return bounds
        try:
            return await asyncio.to_thread(map_bounds_for_wad, wad.stored_path, map_name)
        except Exception:
            return None


def _analysis_map_bounds(analysis) -> dict[str, int] | None:
    if analysis is None:
        return None
    features = (analysis.spawn_summary_by_skill or {}).get("_map_features")
    if not isinstance(features, dict):
        return None
    bounds = features.get("bounds")
    if not isinstance(bounds, dict):
        return None
    try:
        min_x = int(bounds["min_x"])
        max_x = int(bounds["max_x"])
        min_y = int(bounds["min_y"])
        max_y = int(bounds["max_y"])
    except (KeyError, TypeError, ValueError):
        return None
    if min_x == max_x or min_y == max_y:
        return None
    return {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}


async def reanalyze_wad_task(wad_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        wad = await WadRepository(db).get_by_id(wad_id)
        if wad is None:
            return
        analyses = await AnalysisRepository(db).list_by_wad(wad_id)
        for analysis in analyses:
            if analysis.map_overview_png_path:
                Path(analysis.map_overview_png_path).unlink(missing_ok=True)
            await db.delete(analysis)
        await db.flush()
        await AnalysisService(db).analyze_wad(wad)
        await db.commit()
