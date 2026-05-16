from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "wad_file_id": "9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001",
                "map_name": "MAP01",
                "difficulty_level": 3,
                "max_ticks": 3000,
            }
        }
    )

    wad_file_id: UUID
    map_name: str
    difficulty_level: int = Field(default=3, ge=1, le=5)
    max_ticks: int | None = Field(default=None, ge=1)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wad_file_id: UUID
    static_analysis_id: UUID | None = None
    map_name: str
    difficulty_level: int
    iwad_used: str
    llm_model: str
    max_ticks: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    outcome: str | None = None
    error_message: str | None = None
    final_hp: int | None = None
    final_armor: int | None = None
    total_kills: int | None = None
    total_deaths: int | None = None
    secrets_found: int | None = None
    total_items_collected: int | None = None
    total_actions_taken: int | None = None
    total_llm_calls: int | None = None
    recording_mp4_path: str | None = None
    report_pdf_path: str | None = None
    created_at: datetime
