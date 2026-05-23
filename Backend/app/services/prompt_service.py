from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR
from app.models import StaticAnalysisResult, TestRun, WadFile
from app.services.analysis_service import selected_skill_spawn_summary


def _sanitize_prompt_value(value: Any) -> str:
    text = str(value)
    return text.replace("{", "(").replace("}", ")")


def render_agent_prompt(wad: WadFile, analysis: StaticAnalysisResult, run: TestRun) -> str:
    template = (BASE_DIR / "app" / "prompts" / "agent_system_prompt.md").read_text()
    skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
    spawned_enemies = int(skill_summary.get("thing_count_enemies", analysis.thing_count_enemies) or 0)
    raw_enemies = int(analysis.thing_count_enemies or 0)
    spawn_warning = ""
    if raw_enemies and spawned_enemies < raw_enemies:
        spawn_warning = (
            f"Raw map analysis found {raw_enemies} enemies, but only {spawned_enemies} "
            f"spawn at difficulty {run.difficulty_level} because of Doom skill flags."
        )
    map_features = (analysis.spawn_summary_by_skill or {}).get("_map_features") or {}
    key_req = map_features.get("key_requirements") or {}
    key_summary_parts = []
    if key_req.get("red"):
        key_summary_parts.append("red")
    if key_req.get("yellow"):
        key_summary_parts.append("yellow")
    if key_req.get("blue"):
        key_summary_parts.append("blue")
    key_summary = ", ".join(key_summary_parts) if key_summary_parts else "none"

    values: dict[str, Any] = {
        "map_name": analysis.map_name,
        "map_display_name": analysis.map_display_name or analysis.map_name,
        "iwad_used": wad.iwad_required,
        "difficulty_level": run.difficulty_level,
        "estimated_difficulty": skill_summary.get("estimated_difficulty") or analysis.estimated_difficulty or "unknown",
        "thing_count_enemies": spawned_enemies,
        "raw_thing_count_enemies": raw_enemies,
        "enemy_breakdown_summary": json.dumps(skill_summary.get("enemy_breakdown") or {}, ensure_ascii=True),
        "raw_enemy_breakdown_summary": json.dumps(analysis.enemy_breakdown, ensure_ascii=True),
        "hitscanner_percent": str(skill_summary.get("hitscanner_percent", analysis.hitscanner_percent) or "unknown"),
        "health_ratio": str(skill_summary.get("health_ratio", analysis.health_ratio) or "unknown"),
        "ammo_ratio": str(skill_summary.get("ammo_ratio", analysis.ammo_ratio) or "unknown"),
        "secret_sector_count": analysis.secret_sector_count,
        "map_width_units": analysis.map_width_units or "unknown",
        "map_height_units": analysis.map_height_units or "unknown",
        "total_health_pickup_pts": skill_summary.get("total_health_pickup_pts", analysis.total_health_pickup_pts) or 0,
        "spawn_warning": spawn_warning or "None.",
        "door_count": map_features.get("door_count", "unknown"),
        "locked_door_count": map_features.get("locked_door_count", "unknown"),
        "key_requirements": key_summary,
        "teleporter_count": map_features.get("teleporter_count", "unknown"),
        "lift_count": map_features.get("lift_count", "unknown"),
    }
    for key, value in values.items():
        template = template.replace("{" + key + "}", _sanitize_prompt_value(value))
    return template


def report_prompt_path() -> Path:
    return BASE_DIR / "app" / "prompts" / "report_generation_prompt.md"
