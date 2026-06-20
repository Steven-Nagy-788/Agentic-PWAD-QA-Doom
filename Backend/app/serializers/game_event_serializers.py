from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


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

    @computed_field
    @property
    def mcp_tool(self) -> str | None:
        return (self.action_taken or {}).get("mcp_tool")

    @computed_field
    @property
    def mcp_executed_tool(self) -> str | None:
        action = self.action_taken or {}
        return action.get("mcp_executed_tool") or action.get("mcp_tool")

    @computed_field
    @property
    def mcp_params(self) -> dict[str, Any] | None:
        return (self.action_taken or {}).get("mcp_params")

    @computed_field
    @property
    def mcp_action_summary(self) -> dict[str, Any] | None:
        action = self.action_taken or {}
        if isinstance(action.get("mcp_action_summary"), dict):
            return action["mcp_action_summary"]
        output = action.get("mcp_output")
        if not isinstance(output, dict):
            return None
        summary = output.get("action_summary")
        return summary if isinstance(summary, dict) else None

    @computed_field
    @property
    def mcp_stop_reason(self) -> str | None:
        action = self.action_taken or {}
        if action.get("mcp_stop_reason") is not None:
            return str(action["mcp_stop_reason"])
        summary = self.mcp_action_summary
        if not summary:
            return None
        value = summary.get("stop_reason")
        return str(value) if value is not None else None


class PositionTrailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: UUID
    tick_number: int
    x: float
    y: float
    angle: float
    health: int
    is_sentinel: bool = False
