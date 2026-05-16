from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR
from app.models import StaticAnalysisResult, TestRun, WadFile


class SafeDict(defaultdict):
    def __missing__(self, key: str) -> str:
        return "unknown"


def render_agent_prompt(wad: WadFile, analysis: StaticAnalysisResult, run: TestRun) -> str:
    template = (BASE_DIR / "app" / "prompts" / "agent_system_prompt.md").read_text()
    values: dict[str, Any] = {
        "map_name": analysis.map_name,
        "iwad_used": wad.iwad_required,
        "difficulty_level": run.difficulty_level,
        "estimated_difficulty": analysis.estimated_difficulty or "unknown",
        "thing_count_enemies": analysis.thing_count_enemies,
        "enemy_breakdown_summary": json.dumps(analysis.enemy_breakdown, ensure_ascii=True),
        "hitscanner_percent": str(analysis.hitscanner_percent or "unknown"),
        "health_ratio": str(analysis.health_ratio or "unknown"),
        "ammo_ratio": str(analysis.ammo_ratio or "unknown"),
        "secret_sector_count": analysis.secret_sector_count,
        "map_width_units": analysis.map_width_units or "unknown",
        "map_height_units": analysis.map_height_units or "unknown",
        "total_health_pickup_pts": analysis.total_health_pickup_pts or 0,
    }
    return template.format_map(SafeDict(str, values))


def report_prompt_path() -> Path:
    return BASE_DIR / "app" / "prompts" / "report_generation_prompt.md"
