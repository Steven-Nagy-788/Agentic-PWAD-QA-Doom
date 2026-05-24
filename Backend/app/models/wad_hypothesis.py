from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.test_run import TestRun
    from app.models.wad_file import WadFile


HYPOTHESIS_TAGS = {"BLOCKED_PATH", "KEY_LOCATION", "RESOURCE_CACHE", "VISUAL_GLITCH", "ENCOUNTER_HOTSPOT", "NAVIGATION_GAP"}


class WadHypothesis(Base):
    __tablename__ = "wad_hypotheses"
    __table_args__ = (
        Index("idx_hypotheses_wad_map", "wad_file_id", "map_name"),
        Index("idx_hypotheses_tag", "wad_file_id", "map_name", "tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    wad_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wad_files.id", ondelete="CASCADE"), nullable=False
    )
    map_name: Mapped[str] = mapped_column(String(16), nullable=False)
    tag: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refuted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    wad_file: Mapped[WadFile] = relationship("WadFile")
    last_run: Mapped[TestRun | None] = relationship("TestRun")
