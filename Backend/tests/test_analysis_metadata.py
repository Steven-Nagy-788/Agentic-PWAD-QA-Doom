from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omg import MapEditor, WAD

from app.services.analysis_service import AnalysisService, map_metadata_for_wad, selected_skill_spawn_summary


ROOT = Path(__file__).resolve().parents[2]
WADS = ROOT / "Backend" / "storage" / "wads"


def test_spawn_summary_respects_doom_skill_flags() -> None:
    wad = WAD(str(WADS / "ac683d7a-65e6-4b06-b94f-b7c0cf8961af.wad"))
    editor = MapEditor(wad.maps["E1M1"])
    service = AnalysisService.__new__(AnalysisService)

    summary = service._spawn_summary_by_skill(editor)

    assert summary["3"]["thing_count_enemies"] == 8
    assert summary["5"]["thing_count_enemies"] == 0
    assert summary["3"]["enemy_breakdown"]["ZOMBIEMAN"]["count"] == 4


def test_map_metadata_falls_back_to_filename_and_map_name() -> None:
    metadata = map_metadata_for_wad(
        str(WADS / "ac683d7a-65e6-4b06-b94f-b7c0cf8961af.wad"),
        "thelonghallways.wad",
    )

    assert metadata["E1M1"]["map_display_name"] == "thelonghallways - E1M1"
    assert metadata["E1M1"]["map_title"] is None
    assert metadata["E1M1"]["map_title_source"] == "fallback_filename"


def test_selected_skill_summary_uses_spawn_json() -> None:
    analysis = SimpleNamespace(
        thing_count_total=10,
        thing_count_enemies=8,
        thing_count_items=1,
        thing_count_keys=0,
        thing_count_weapons=0,
        total_monster_hp=290,
        total_health_pickup_pts=0,
        total_armor_pickup_pts=100,
        hitscanner_percent=62.5,
        health_ratio=0,
        ammo_ratio=0,
        estimated_difficulty="hard",
        enemy_breakdown={},
        item_breakdown={},
        spawn_summary_by_skill={"5": {"difficulty_level": 5, "thing_count_enemies": 0}},
    )

    assert selected_skill_spawn_summary(analysis, 5)["thing_count_enemies"] == 0
