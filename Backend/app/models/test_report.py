from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.defect import Defect
    from app.models.test_run import TestRun


class TestReport(Base):
    __tablename__ = "test_reports"
    __table_args__ = (Index("idx_test_reports_generation_status", "generation_status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    report_purpose: Mapped[str | None] = mapped_column(Text)
    intended_audience: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'Game developers and QA engineers'"),
    )
    problem_and_escalation: Mapped[str | None] = mapped_column(Text)
    test_items_summary: Mapped[str | None] = mapped_column(Text)
    test_environment_summary: Mapped[str | None] = mapped_column(Text)
    hardware_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    software_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    variances_from_plan: Mapped[str | None] = mapped_column(Text)
    test_procedure_variances: Mapped[str | None] = mapped_column(Text)
    test_case_variances: Mapped[str | None] = mapped_column(Text)
    test_coverage_evaluation: Mapped[str | None] = mapped_column(Text)
    objectives_planned: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = (
        mapped_column(JSONB)
    )
    objectives_covered: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = (
        mapped_column(JSONB)
    )
    objectives_omitted: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = (
        mapped_column(JSONB)
    )
    uncovered_attributes: Mapped[str | None] = mapped_column(Text)
    test_process_changes: Mapped[str | None] = mapped_column(Text)
    defect_summary_narrative: Mapped[str | None] = mapped_column(Text)
    defect_patterns: Mapped[str | None] = mapped_column(Text)
    test_item_limitations: Mapped[str | None] = mapped_column(Text)
    dropped_features: Mapped[str | None] = mapped_column(Text)
    pass_fail_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    risk_areas: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = mapped_column(
        JSONB
    )
    good_quality_areas: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = (
        mapped_column(JSONB)
    )
    qa_sections: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = mapped_column(
        JSONB
    )
    evidence_matrix: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    major_activities_summary: Mapped[str | None] = mapped_column(Text)
    activity_variances: Mapped[str | None] = mapped_column(Text)
    elapsed_time_seconds: Mapped[int | None] = mapped_column(Integer)
    total_actions_taken: Mapped[int | None] = mapped_column(Integer)
    report_model: Mapped[str | None] = mapped_column(String(128))
    pdf_path: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'generating'"),
    )
    generation_error: Mapped[str | None] = mapped_column(Text)

    run: Mapped[TestRun] = relationship("TestRun", back_populates="report")
    defects: Mapped[list[Defect]] = relationship(
        "Defect",
        back_populates="report",
        foreign_keys="Defect.report_id",
    )
