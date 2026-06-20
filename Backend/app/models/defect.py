from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, REAL, SmallInteger, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.notable_event_screenshot import NotableEventScreenshot
    from app.models.test_report import TestReport
    from app.models.test_run import TestRun


class Defect(Base):
    __tablename__ = "defects"
    __table_args__ = (
        CheckConstraint("severity BETWEEN 1 AND 4"),
        CheckConstraint("priority BETWEEN 1 AND 3"),
        UniqueConstraint("run_id", "defect_type", "detected_at_tick", name="uq_defects_run_type_tick"),
        UniqueConstraint("run_id", "fingerprint", name="uq_defects_run_fingerprint"),
        Index("idx_defects_run_id", "run_id"),
        Index("idx_defects_severity", "run_id", "severity"),
        Index("idx_defects_fingerprint", "run_id", "fingerprint"),
        Index("idx_defects_report_id", "report_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_reports.id", ondelete="SET NULL"),
    )
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    resolution_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'open'"),
    )
    defect_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_steps: Mapped[str | None] = mapped_column(Text)
    detected_at_tick: Mapped[int | None] = mapped_column(Integer)
    position_x: Mapped[float | None] = mapped_column(REAL)
    position_y: Mapped[float | None] = mapped_column(REAL)
    screenshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notable_event_screenshots.id", ondelete="SET NULL"),
    )
    recommendation: Mapped[str | None] = mapped_column(Text)
    first_seen_tick: Mapped[int | None] = mapped_column(Integer)
    last_seen_tick: Mapped[int | None] = mapped_column(Integer)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[TestRun] = relationship(
        "TestRun",
        back_populates="defects",
        foreign_keys=[run_id],
    )
    report: Mapped[TestReport | None] = relationship(
        "TestReport",
        back_populates="defects",
        foreign_keys=[report_id],
    )
    screenshot: Mapped[NotableEventScreenshot | None] = relationship("NotableEventScreenshot")
