from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class StaticAnalysisOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "68e08fe5-0a88-4f9b-80ee-5f38fb2ac001",
                "wad_file_id": "9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001",
                "map_name": "MAP01",
                "thing_count_enemies": 12,
                "secret_sector_count": 2,
                "estimated_difficulty": "fair",
                "map_overview_png_url": "/wads/9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001/map-png?map_name=MAP01",
            }
        },
    )

    id: UUID
    wad_file_id: UUID
    map_name: str
    thing_count_total: int
    thing_count_enemies: int
    thing_count_items: int
    thing_count_keys: int
    thing_count_weapons: int
    linedef_count: int
    sector_count: int
    secret_sector_count: int
    vertex_count: int
    map_width_units: int | None = None
    map_height_units: int | None = None
    total_monster_hp: int | None = None
    total_health_pickup_pts: int | None = None
    total_armor_pickup_pts: int | None = None
    hitscanner_percent: Optional[float] = None
    health_ratio: Optional[float] = None
    ammo_ratio: Optional[float] = None
    estimated_difficulty: str | None = None
    enemy_breakdown: dict[str, Any]
    item_breakdown: dict[str, Any]
    map_overview_png_path: str | None = None
    map_overview_png_url: str | None = None
    analyzed_at: datetime

    @field_validator("hitscanner_percent", "health_ratio", "ammo_ratio", mode="before")
    @classmethod
    def coerce_decimal(cls, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)
