from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    generation_status: str
    generation_error: str | None = None
    pdf_path: str | None = None
    generated_at: datetime
    report_purpose: str | None = None
    test_items_summary: str | None = None
    defect_summary_narrative: str | None = None
    pass_fail_summary: dict[str, Any] | None = None
