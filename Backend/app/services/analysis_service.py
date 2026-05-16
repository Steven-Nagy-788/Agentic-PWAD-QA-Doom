from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from omg import MapEditor, WAD
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import StaticAnalysisResult, WadFile
from app.repositories.analysis_repository import AnalysisRepository
from app.services.analysis_constants import ENEMY_TYPES, ITEM_TYPES, KEY_TYPES, WEAPON_TYPES


def detect_iwad_requirement(map_names: list[str]) -> str:
    if any(re.match(r"^E\dM\d$", name.upper()) for name in map_names):
        return "freedoom1"
    if any(re.match(r"^MAP\d{2}$", name.upper()) for name in map_names):
        return "freedoom2"
    return "freedoom2"


def detect_map_names(wad_path: str) -> list[str]:
    wad = WAD(wad_path)
    names = [name.upper() for name in wad.maps.keys()]
    return sorted(names)


class AnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = AnalysisRepository(db)

    async def analyze_wad(self, wad_file: WadFile) -> list[StaticAnalysisResult]:
        map_names = detect_map_names(wad_file.stored_path)
        wad_file.detected_maps = map_names
        wad_file.iwad_required = detect_iwad_requirement(map_names)
        results = []
        for map_name in map_names:
            results.append(await self.analyze_map(wad_file, map_name))
        return results

    async def analyze_map(self, wad_file: WadFile, map_name: str) -> StaticAnalysisResult:
        map_name = map_name.upper()
        existing = await self.repo.get_by_wad_and_map(wad_file.id, map_name)
        if existing is not None and self._overview_path_is_current(existing.map_overview_png_path):
            return existing

        wad = WAD(wad_file.stored_path)
        if map_name not in wad.maps:
            raise ValueError(f"Map {map_name} not found in WAD")

        editor = MapEditor(wad.maps[map_name])
        if existing is not None:
            existing.map_overview_png_path = str(self._render_overview(wad_file.id, map_name, editor))
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        thing_counts = Counter(int(thing.type) for thing in editor.things)
        enemy_breakdown, total_monster_hp, hitscanner_count = self._enemy_breakdown(thing_counts)
        item_breakdown, health_pts, armor_pts, ammo_score = self._item_breakdown(thing_counts)

        vertices = editor.vertexes
        if vertices:
            xs = [int(vertex.x) for vertex in vertices]
            ys = [int(vertex.y) for vertex in vertices]
            map_width = max(xs) - min(xs)
            map_height = max(ys) - min(ys)
        else:
            map_width = None
            map_height = None

        enemy_count = sum(item["count"] for item in enemy_breakdown.values())
        hitscanner_percent = round((hitscanner_count / enemy_count) * 100, 2) if enemy_count else None
        health_ratio = round(health_pts / total_monster_hp, 4) if total_monster_hp else None
        ammo_ratio = round(ammo_score / total_monster_hp, 4) if total_monster_hp else None
        estimated_difficulty = self._difficulty(enemy_count, hitscanner_percent, health_ratio, ammo_ratio)
        overview_path = self._render_overview(wad_file.id, map_name, editor)

        analysis = StaticAnalysisResult(
            wad_file_id=wad_file.id,
            map_name=map_name,
            thing_count_total=len(editor.things),
            thing_count_enemies=enemy_count,
            thing_count_items=sum(1 for thing_type in thing_counts for _ in range(thing_counts[thing_type]) if thing_type in ITEM_TYPES),
            thing_count_keys=sum(thing_counts[key] for key in KEY_TYPES),
            thing_count_weapons=sum(thing_counts[key] for key in WEAPON_TYPES),
            linedef_count=len(editor.linedefs),
            sector_count=len(editor.sectors),
            secret_sector_count=sum(1 for sector in editor.sectors if int(sector.type) == 9),
            vertex_count=len(editor.vertexes),
            map_width_units=map_width,
            map_height_units=map_height,
            total_monster_hp=total_monster_hp,
            total_health_pickup_pts=health_pts,
            total_armor_pickup_pts=armor_pts,
            hitscanner_percent=hitscanner_percent,
            health_ratio=health_ratio,
            ammo_ratio=ammo_ratio,
            estimated_difficulty=estimated_difficulty,
            enemy_breakdown=enemy_breakdown,
            item_breakdown=item_breakdown,
            map_overview_png_path=str(overview_path),
        )
        return await self.repo.upsert(analysis)

    def _enemy_breakdown(self, counts: Counter[int]) -> tuple[dict[str, Any], int, int]:
        breakdown: dict[str, Any] = {}
        total_hp = 0
        hitscanners = 0
        for thing_type, count in counts.items():
            if thing_type not in ENEMY_TYPES:
                continue
            name, hp, is_hitscanner = ENEMY_TYPES[thing_type]
            total = count * hp
            breakdown[name] = {"count": count, "hp": hp, "total_hp": total, "hitscanner": is_hitscanner}
            total_hp += total
            if is_hitscanner:
                hitscanners += count
        return breakdown, total_hp, hitscanners

    def _item_breakdown(self, counts: Counter[int]) -> tuple[dict[str, Any], int, int, int]:
        breakdown: dict[str, Any] = {}
        health_pts = 0
        armor_pts = 0
        ammo_score = 0
        for thing_type, count in counts.items():
            if thing_type not in ITEM_TYPES:
                continue
            name, value, category = ITEM_TYPES[thing_type]
            total = count * value
            breakdown[name] = {"count": count, "value": value, "total": total, "category": category}
            if category == "health":
                health_pts += total
            elif category == "armor":
                armor_pts += total
            else:
                ammo_score += total
        return breakdown, health_pts, armor_pts, ammo_score

    @staticmethod
    def _difficulty(
        enemy_count: int,
        hitscanner_percent: float | None,
        health_ratio: float | None,
        ammo_ratio: float | None,
    ) -> str:
        score = 0
        if enemy_count > 80:
            score += 2
        elif enemy_count > 30:
            score += 1
        if hitscanner_percent and hitscanner_percent > 40:
            score += 1
        if health_ratio is not None and health_ratio < 0.15:
            score += 1
        if ammo_ratio is not None and ammo_ratio < 0.8:
            score += 1
        if score >= 4:
            return "slaughter"
        if score >= 2:
            return "hard"
        if score == 1:
            return "fair"
        return "easy"

    def _render_overview(self, wad_id: UUID, map_name: str, editor: MapEditor) -> Path:
        output = self.settings.analysis_storage_dir / f"{wad_id}_{map_name}_overview.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        size = 1024
        image = Image.new("RGB", (size, size), "black")
        draw = ImageDraw.Draw(image)
        vertices = editor.vertexes
        if not vertices:
            image.save(output)
            return output

        xs = [int(vertex.x) for vertex in vertices]
        ys = [int(vertex.y) for vertex in vertices]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        scale = min((size - 40) / max(max_x - min_x, 1), (size - 40) / max(max_y - min_y, 1))

        def point(index: int) -> tuple[int, int]:
            vertex = vertices[index]
            x = int((int(vertex.x) - min_x) * scale + 20)
            y = int(size - ((int(vertex.y) - min_y) * scale + 20))
            return x, y

        for linedef in editor.linedefs:
            color = (255, 80, 80) if getattr(linedef, "secret", False) else (190, 190, 190)
            draw.line([point(int(linedef.vx_a)), point(int(linedef.vx_b))], fill=color, width=2)

        image.save(output)
        return output

    def _overview_path_is_current(self, path: str | None) -> bool:
        if not path:
            return False
        overview = Path(path)
        return overview.exists() and overview.parent == self.settings.analysis_storage_dir
