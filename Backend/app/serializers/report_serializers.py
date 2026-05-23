from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    generation_status: str
    generation_error: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_url: Optional[str] = None
    generated_at: datetime
    report_purpose: Optional[str] = None
    intended_audience: Optional[str] = None
    problem_and_escalation: Optional[str] = None
    test_items_summary: Optional[str] = None
    test_environment_summary: Optional[str] = None
    hardware_spec: Optional[dict[str, Any]] = None
    software_spec: Optional[dict[str, Any]] = None
    variances_from_plan: Optional[str] = None
    test_procedure_variances: Optional[str] = None
    test_case_variances: Optional[str] = None
    test_coverage_evaluation: Optional[str] = None
    objectives_planned: Optional[list[Any] | dict[str, Any]] = None
    objectives_covered: Optional[list[Any] | dict[str, Any]] = None
    objectives_omitted: Optional[list[Any] | dict[str, Any]] = None
    uncovered_attributes: Optional[str] = None
    test_process_changes: Optional[str] = None
    defect_summary_narrative: Optional[str] = None
    defect_patterns: Optional[str] = None
    test_item_limitations: Optional[str] = None
    dropped_features: Optional[str] = None
    pass_fail_summary: Optional[dict[str, Any]] = None
    risk_areas: Optional[list[Any] | dict[str, Any]] = None
    good_quality_areas: Optional[list[Any] | dict[str, Any]] = None
    major_activities_summary: Optional[str] = None
    activity_variances: Optional[str] = None
    elapsed_time_seconds: Optional[int] = None
    total_actions_taken: Optional[int] = None

    @model_validator(mode="after")
    def _compute_url(self) -> "ReportOut":
        self.pdf_url = f"/runs/{self.run_id}/report/pdf" if self.pdf_path else None
        return self

    @model_serializer(mode="wrap")
    def _strip_path(self, handler) -> dict[str, Any]:
        result = handler(self)
        result.pop("pdf_path", None)
        return result


class ReportStatusOut(BaseModel):
    status: str
    report_id: Optional[UUID] = None
    pdf_available: bool = False
    pdf_url: Optional[str] = None
    generation_error: Optional[str] = None
