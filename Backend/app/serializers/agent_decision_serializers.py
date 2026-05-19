from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AgentDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    sequence_number: int
    tick_before: int | None = None
    tick_after: int | None = None
    game_event_id: int | None = None
    status: str
    error_message: str | None = None
    llm_input_summary: dict[str, Any] | None = None
    llm_decision: dict[str, Any] | None = None
    reasoning_summary: str | None = None
    mcp_tool: str | None = None
    mcp_input: dict[str, Any] | None = None
    mcp_output: dict[str, Any] | None = None
    mcp_stop_reason: str | None = None
    llm_duration_ms: float | None = None
    mcp_duration_ms: float | None = None
    created_at: datetime
