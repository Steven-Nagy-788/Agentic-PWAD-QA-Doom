from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


class RunCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "wad_file_id": "9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001",
                "map_name": "MAP01",
                "difficulty_level": 3,
                "max_ticks": 3000,
                "seed": 42,
            }
        }
    )

    wad_file_id: UUID
    map_name: str
    difficulty_level: int = Field(default=3, ge=1, le=5)
    max_ticks: int | None = Field(default=None, ge=1)
    behavior_profile: str | None = None
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    allow_deathmatch_start_normalization: bool = False


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wad_file_id: UUID
    static_analysis_id: UUID | None = None
    map_name: str
    map_display_name: str | None = None
    difficulty_level: int
    iwad_used: str
    llm_model: str
    max_ticks: int
    seed: int | None = None
    start_normalization: dict[str, Any] | None = None
    behavior_profile: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    outcome: str | None = None
    error_message: str | None = None
    failure_category: str | None = None
    failure_stage: str | None = None
    failure_summary: str | None = None
    failure_diagnostics: dict[str, Any] | None = None
    final_hp: int | None = None
    final_armor: int | None = None
    total_kills: int | None = None
    total_deaths: int | None = None
    secrets_found: int | None = None
    total_items_collected: int | None = None
    total_actions_taken: int | None = None
    total_llm_calls: int | None = None
    recording_mp4_path: str | None = None
    recording_metadata: dict[str, Any] | None = None
    progress_metrics: dict[str, Any] | None = None
    agent_quality_flags: dict[str, Any] | None = None
    environment_metadata: dict[str, Any] | None = None
    report_pdf_path: str | None = None
    recording_mp4_url: str | None = None
    report_pdf_url: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _compute_urls(self) -> "RunOut":
        self.recording_mp4_url = (
            f"/runs/{self.id}/recording" if self.recording_mp4_path else None
        )
        self.report_pdf_url = (
            f"/runs/{self.id}/report/pdf" if self.report_pdf_path else None
        )
        return self

    @model_serializer(mode="wrap")
    def _strip_paths(self, handler) -> dict[str, Any]:
        result = handler(self)
        result.pop("recording_mp4_path", None)
        result.pop("report_pdf_path", None)
        return result


class RunListOut(BaseModel):
    total: int
    items: list[RunOut]
    offset: int


class RunCompareOut(BaseModel):
    run_a: UUID
    run_b: UUID
    same_map: bool
    outcome_change: dict[str, str | None]
    defects: dict[str, list[dict[str, Any]]]
    kill_coverage_delta: dict[str, int | None]
    movement_coverage_delta: dict[str, float]
    resource_delta: dict[str, int | None]
