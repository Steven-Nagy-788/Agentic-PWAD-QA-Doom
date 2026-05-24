from __future__ import annotations

import asyncio
import re
import struct
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


MAPINFO_LUMPS = {"MAPINFO", "UMAPINFO"}
MAP_NAME_RE = re.compile(r"^(?:MAP\d{2}|E\dM\d)$", re.IGNORECASE)


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


def map_metadata_for_wad(wad_path: str, original_filename: str) -> dict[str, dict[str, str | None]]:
    """Return UI-facing map title/display metadata keyed by map name."""
    titles = _parse_map_titles(wad_path)
    metadata: dict[str, dict[str, str | None]] = {}
    fallback_prefix = Path(original_filename or Path(wad_path).name).stem or Path(wad_path).stem
    for map_name in detect_map_names(wad_path):
        title_info = titles.get(map_name.upper())
        title = title_info[0] if title_info else None
        source = title_info[1] if title_info else "fallback_filename"
        display = f"{map_name} - {title}" if title else f"{fallback_prefix} - {map_name}"
        metadata[map_name] = {
            "map_title": title,
            "map_display_name": display,
            "map_title_source": source,
        }
    return metadata


def _parse_map_titles(wad_path: str) -> dict[str, tuple[str, str]]:
    titles: dict[str, tuple[str, str]] = {}
    for lump_name, text in _read_text_lumps(wad_path).items():
        titles.update(_parse_block_mapinfo_titles(text, lump_name))
        titles.update({key: value for key, value in _parse_inline_mapinfo_titles(text, lump_name).items() if key not in titles})
    return titles


def _read_text_lumps(wad_path: str) -> dict[str, str]:
    data = Path(wad_path).read_bytes()
    if len(data) < 12:
        return {}
    magic, lump_count, directory_offset = struct.unpack_from("<4sii", data, 0)
    if magic not in {b"IWAD", b"PWAD"} or lump_count < 0 or directory_offset < 0:
        return {}

    lumps: dict[str, str] = {}
    for index in range(lump_count):
        entry_offset = directory_offset + index * 16
        if entry_offset + 16 > len(data):
            break
        lump_offset, lump_size, raw_name = struct.unpack_from("<ii8s", data, entry_offset)
        name = raw_name.rstrip(b"\0").decode("ascii", errors="ignore").upper()
        if name not in MAPINFO_LUMPS or lump_size <= 0:
            continue
        blob = data[lump_offset : lump_offset + lump_size]
        lumps[name] = blob.decode("latin1", errors="replace")
    return lumps


def _parse_block_mapinfo_titles(text: str, source: str) -> dict[str, tuple[str, str]]:
    titles: dict[str, tuple[str, str]] = {}
    pattern = re.compile(r"\bmap\s+([A-Za-z0-9_]+)\s*\{(?P<body>.*?)\}", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(text):
        map_name = match.group(1).upper()
        if not MAP_NAME_RE.match(map_name):
            continue
        body = match.group("body")
        title_match = re.search(
            r"\b(?:levelname|label)\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\n\r]+))",
            body,
            re.IGNORECASE,
        )
        if not title_match:
            continue
        title = _clean_title(next(group for group in title_match.groups() if group is not None))
        if title:
            titles[map_name] = (title, source.lower())
    return titles


def _parse_inline_mapinfo_titles(text: str, source: str) -> dict[str, tuple[str, str]]:
    titles: dict[str, tuple[str, str]] = {}
    pattern = re.compile(
        r"^\s*map\s+([A-Za-z0-9_]+)\s+(?:\"([^\"]+)\"|'([^']+)'|([^{}\n\r]+))",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in pattern.finditer(text):
        map_name = match.group(1).upper()
        if not MAP_NAME_RE.match(map_name):
            continue
        title = _clean_title(next(group for group in match.groups()[1:] if group is not None))
        if title:
            titles[map_name] = (title, source.lower())
    return titles


def _clean_title(value: str) -> str | None:
    title = value.strip().strip(",").strip()
    if not title:
        return None
    return re.sub(r"\s+", " ", title)


def player_one_start_count(wad_path: str, map_name: str) -> int:
    return player_start_counts(wad_path, map_name)["player_one"]


def player_start_counts(wad_path: str, map_name: str) -> dict[str, int]:
    wad = WAD(wad_path)
    map_name = map_name.upper()
    if map_name not in wad.maps:
        return {"player_one": 0, "deathmatch": 0}
    editor = MapEditor(wad.maps[map_name])
    return {
        "player_one": sum(1 for thing in editor.things if int(thing.type) == 1),
        "deathmatch": sum(1 for thing in editor.things if int(thing.type) == 11),
    }


def map_bounds_for_wad(wad_path: str, map_name: str) -> dict[str, int] | None:
    wad = WAD(wad_path)
    map_name = map_name.upper()
    if map_name not in wad.maps:
        return None
    return AnalysisService._map_bounds_from_editor(MapEditor(wad.maps[map_name]))


def map_has_single_player_start(wad_path: str, map_name: str) -> bool:
    return player_one_start_count(wad_path, map_name) == 1


def map_can_be_normalized_for_single_player(wad_path: str, map_name: str) -> bool:
    counts = player_start_counts(wad_path, map_name)
    return counts["player_one"] > 0 or counts["deathmatch"] > 0


def thing_spawns_at_skill(thing: Any, difficulty: int) -> bool:
    """Return whether a Doom-format thing appears in backend single-player mode."""
    skill_flag = "medium"
    if difficulty in {1, 2}:
        skill_flag = "easy"
    elif difficulty in {4, 5}:
        skill_flag = "hard"
    if not bool(getattr(thing, skill_flag, False)):
        return False
    if bool(getattr(thing, "multiplayer", False)):
        return False
    return True


def selected_skill_spawn_summary(analysis: StaticAnalysisResult | None, difficulty: int) -> dict[str, Any]:
    if analysis is None:
        return {}
    summaries = analysis.spawn_summary_by_skill or {}
    summary = summaries.get(str(difficulty)) or summaries.get(int(difficulty)) if isinstance(summaries, dict) else None
    if isinstance(summary, dict):
        return summary
    return {
        "difficulty_level": difficulty,
        "thing_count_total": analysis.thing_count_total,
        "thing_count_enemies": analysis.thing_count_enemies,
        "thing_count_items": analysis.thing_count_items,
        "thing_count_keys": analysis.thing_count_keys,
        "thing_count_weapons": analysis.thing_count_weapons,
        "total_monster_hp": analysis.total_monster_hp or 0,
        "total_health_pickup_pts": analysis.total_health_pickup_pts or 0,
        "total_armor_pickup_pts": analysis.total_armor_pickup_pts or 0,
        "hitscanner_percent": float(analysis.hitscanner_percent or 0),
        "health_ratio": float(analysis.health_ratio or 0),
        "ammo_ratio": float(analysis.ammo_ratio or 0),
        "estimated_difficulty": analysis.estimated_difficulty or "unknown",
        "enemy_breakdown": analysis.enemy_breakdown or {},
        "item_breakdown": analysis.item_breakdown or {},
    }


class AnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = AnalysisRepository(db)

    async def analyze_wad(self, wad_file: WadFile) -> list[StaticAnalysisResult]:
        map_names = await asyncio.to_thread(detect_map_names, wad_file.stored_path)
        wad_file.detected_maps = map_names
        wad_file.iwad_required = detect_iwad_requirement(map_names)
        results = []
        for map_name in map_names:
            results.append(await self.analyze_map(wad_file, map_name))
        return results

    async def analyze_map(self, wad_file: WadFile, map_name: str) -> StaticAnalysisResult:
        map_name = map_name.upper()
        existing = await self.repo.get_by_wad_and_map(wad_file.id, map_name)

        analysis_fields = await asyncio.to_thread(self._build_analysis_fields, wad_file, map_name, existing)
        analysis = StaticAnalysisResult(**analysis_fields)
        return await self.repo.upsert(analysis)

    def _build_analysis_fields(
        self,
        wad_file: WadFile,
        map_name: str,
        existing: StaticAnalysisResult | None,
    ) -> dict[str, Any]:
        wad = WAD(wad_file.stored_path)
        if map_name not in wad.maps:
            raise ValueError(f"Map {map_name} not found in WAD")

        editor = MapEditor(wad.maps[map_name])
        metadata = map_metadata_for_wad(wad_file.stored_path, wad_file.original_filename).get(map_name, {})

        thing_counts = Counter(int(thing.type) for thing in editor.things)
        enemy_breakdown, total_monster_hp, hitscanner_count = self._enemy_breakdown(thing_counts)
        item_breakdown, health_pts, armor_pts, ammo_score = self._item_breakdown(thing_counts)
        spawn_summary_by_skill = self._spawn_summary_by_skill(editor)
        map_features = self._extract_map_features(editor, thing_counts)
        map_bounds = self._map_bounds_from_editor(editor)
        if map_bounds:
            map_features["bounds"] = map_bounds
            map_width = map_bounds["max_x"] - map_bounds["min_x"]
            map_height = map_bounds["max_y"] - map_bounds["min_y"]
        else:
            map_width = None
            map_height = None

        enemy_count = sum(item["count"] for item in enemy_breakdown.values())
        hitscanner_percent = round((hitscanner_count / enemy_count) * 100, 2) if enemy_count else 0.0
        health_ratio = round(health_pts / total_monster_hp, 4) if total_monster_hp else 0.0
        ammo_ratio = round(ammo_score / total_monster_hp, 4) if total_monster_hp else 0.0
        estimated_difficulty = self._difficulty(enemy_count, hitscanner_percent, health_ratio, ammo_ratio)
        overview_path = self._render_overview(wad_file.id, map_name, editor)

        analysis_fields: dict[str, Any] = dict(
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
            map_title=metadata.get("map_title"),
            map_display_name=metadata.get("map_display_name") or f"{wad_file.original_filename} - {map_name}",
            map_title_source=metadata.get("map_title_source") or "fallback_filename",
            spawn_summary_by_skill={**spawn_summary_by_skill, "_map_features": map_features},
            map_overview_png_path=str(overview_path),
        )
        if existing is not None:
            analysis_fields["id"] = existing.id
        return analysis_fields

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

    def _spawn_summary_by_skill(self, editor: MapEditor) -> dict[str, Any]:
        summaries: dict[str, Any] = {}
        for difficulty in range(1, 6):
            counts = Counter(
                int(thing.type)
                for thing in editor.things
                if thing_spawns_at_skill(thing, difficulty)
            )
            enemy_breakdown, total_monster_hp, hitscanner_count = self._enemy_breakdown(counts)
            item_breakdown, health_pts, armor_pts, ammo_score = self._item_breakdown(counts)
            enemy_count = sum(item["count"] for item in enemy_breakdown.values())
            hitscanner_percent = round((hitscanner_count / enemy_count) * 100, 2) if enemy_count else 0.0
            health_ratio = round(health_pts / total_monster_hp, 4) if total_monster_hp else 0.0
            ammo_ratio = round(ammo_score / total_monster_hp, 4) if total_monster_hp else 0.0
            summaries[str(difficulty)] = {
                "difficulty_level": difficulty,
                "thing_count_total": sum(counts.values()),
                "thing_count_enemies": enemy_count,
                "thing_count_items": sum(count for thing_type, count in counts.items() if thing_type in ITEM_TYPES),
                "thing_count_keys": sum(counts[key] for key in KEY_TYPES),
                "thing_count_weapons": sum(counts[key] for key in WEAPON_TYPES),
                "total_monster_hp": total_monster_hp,
                "total_health_pickup_pts": health_pts,
                "total_armor_pickup_pts": armor_pts,
                "hitscanner_percent": hitscanner_percent,
                "health_ratio": health_ratio,
                "ammo_ratio": ammo_ratio,
                "estimated_difficulty": self._difficulty(enemy_count, hitscanner_percent, health_ratio, ammo_ratio),
                "enemy_breakdown": enemy_breakdown,
                "item_breakdown": item_breakdown,
            }
        return summaries

    @staticmethod
    def _extract_map_features(editor: MapEditor, thing_counts: Counter[int]) -> dict[str, Any]:
        door_specials = {1, 26, 31, 32, 33, 34, 46, 61, 62, 90, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118}
        key_lock_specials = {32, 33, 34, 103, 106, 109}
        lift_specials = {10, 14, 62, 66, 67, 68, 69, 70, 87, 88, 95, 100, 121, 122, 123, 124, 125, 126, 127, 128}
        teleporter_things = {39, 97}

        door_count = 0
        locked_door_count = 0
        lift_count = 0
        teleporter_count = sum(thing_counts[t] for t in teleporter_things if t in thing_counts)

        red_key_count = thing_counts.get(13, 0) + thing_counts.get(38, 0)
        yellow_key_count = thing_counts.get(6, 0) + thing_counts.get(39, 0)
        blue_key_count = thing_counts.get(5, 0) + thing_counts.get(40, 0)

        for linedef in editor.linedefs:
            special = int(getattr(linedef, "special", 0) or 0)
            if special in door_specials:
                door_count += 1
                if special in key_lock_specials:
                    locked_door_count += 1
            if special in lift_specials:
                lift_count += 1

        return {
            "door_count": door_count,
            "locked_door_count": locked_door_count,
            "key_requirements": {
                "red": red_key_count > 0,
                "yellow": yellow_key_count > 0,
                "blue": blue_key_count > 0,
            },
            "teleporter_count": teleporter_count,
            "lift_count": lift_count,
        }

    @staticmethod
    def _map_bounds_from_editor(editor: MapEditor) -> dict[str, int] | None:
        vertices = editor.vertexes
        if not vertices:
            return None
        xs = [int(vertex.x) for vertex in vertices]
        ys = [int(vertex.y) for vertex in vertices]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if min_x == max_x or min_y == max_y:
            return None
        return {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}

    @staticmethod
    def _difficulty(
        enemy_count: int,
        hitscanner_percent: float | None,
        health_ratio: float | None,
        ammo_ratio: float | None,
    ) -> str:
        if enemy_count == 0:
            return "easy"
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
