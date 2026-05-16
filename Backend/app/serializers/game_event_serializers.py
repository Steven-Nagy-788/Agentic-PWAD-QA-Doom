from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TraceEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: UUID
    tick_number: int
    recorded_at: datetime
    player_x: float
    player_y: float
    player_angle: int
    health: int
    armor: int
    ammo_bullets: int
    ammo_shells: int
    ammo_rockets: int
    ammo_cells: int
    kill_count: int
    item_count: int
    secret_count: int
    weapon_selected: int
    event_type: str
    action_taken: dict[str, Any] | None = None
    llm_reasoning: str | None = None
    llm_input_summary: str | None = None
    killed_enemy_type: str | None = None
    damage_received: int | None = None


class PositionTrailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: UUID
    tick_number: int
    x: float
    y: float
    health: int
