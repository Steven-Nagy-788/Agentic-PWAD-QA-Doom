from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.agent_decision import AgentDecision
    from app.models.agent_position_trail import AgentPositionTrail
    from app.models.defect import Defect
    from app.models.game_event import GameEvent
    from app.models.notable_event_screenshot import NotableEventScreenshot
    from app.models.static_analysis_result import StaticAnalysisResult
    from app.models.test_report import TestReport
    from app.models.wad_file import WadFile


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint("difficulty_level BETWEEN 1 AND 5"),
        Index("idx_test_runs_wad_file_id", "wad_file_id"),
        Index("idx_test_runs_status", "status"),
        Index("idx_test_runs_created_at", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    wad_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wad_files.id", ondelete="RESTRICT"),
        nullable=False,
    )
    static_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("static_analysis_results.id", ondelete="SET NULL"),
    )
    map_name: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("3"))
    iwad_used: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'freedoom2'"))
    llm_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("'gemini-2.5-flash'"),
    )
    max_ticks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3000"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    failure_category: Mapped[str | None] = mapped_column(String(32))
    failure_stage: Mapped[str | None] = mapped_column(String(64))
    failure_summary: Mapped[str | None] = mapped_column(Text)
    failure_diagnostics: Mapped[dict | None] = mapped_column(JSONB)
    final_hp: Mapped[int | None] = mapped_column(SmallInteger)
    final_armor: Mapped[int | None] = mapped_column(SmallInteger)
    total_kills: Mapped[int | None] = mapped_column(SmallInteger)
    total_deaths: Mapped[int | None] = mapped_column(SmallInteger)
    secrets_found: Mapped[int | None] = mapped_column(SmallInteger)
    total_items_collected: Mapped[int | None] = mapped_column(SmallInteger)
    total_actions_taken: Mapped[int | None] = mapped_column(Integer)
    total_llm_calls: Mapped[int | None] = mapped_column(Integer)
    recording_mp4_path: Mapped[str | None] = mapped_column(Text)
    report_pdf_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    wad_file: Mapped[WadFile] = relationship("WadFile", back_populates="test_runs")
    static_analysis: Mapped[StaticAnalysisResult | None] = relationship(
        "StaticAnalysisResult",
        back_populates="test_runs",
        foreign_keys=[static_analysis_id],
    )
    game_events: Mapped[list[GameEvent]] = relationship(
        "GameEvent",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    agent_decisions: Mapped[list[AgentDecision]] = relationship(
        "AgentDecision",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    screenshots: Mapped[list[NotableEventScreenshot]] = relationship(
        "NotableEventScreenshot",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    position_trail: Mapped[list[AgentPositionTrail]] = relationship(
        "AgentPositionTrail",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    report: Mapped[TestReport | None] = relationship(
        "TestReport",
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    defects: Mapped[list[Defect]] = relationship(
        "Defect",
        back_populates="run",
        cascade="all, delete-orphan",
        foreign_keys="Defect.run_id",
    )
