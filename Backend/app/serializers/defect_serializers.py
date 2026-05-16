from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DefectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    report_id: UUID | None = None
    severity: int
    priority: int
    resolution_status: str
    defect_type: str
    title: str
    description: str
    reproduction_steps: str | None = None
    detected_at_tick: int | None = None
    position_x: float | None = None
    position_y: float | None = None
    screenshot_id: UUID | None = None
    recommendation: str | None = None
    created_at: datetime
