from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, SmallInteger, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.test_run import TestRun
    from app.models.wad_file import WadFile


class WadSpatialMemory(Base):
    __tablename__ = "wad_spatial_memory"
    __table_args__ = (
        UniqueConstraint("wad_file_id", "map_name", "cell_x", "cell_y", "event_type", name="uq_spatial_cell_event"),
        Index("idx_spatial_wad_map", "wad_file_id", "map_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    wad_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wad_files.id", ondelete="CASCADE"), nullable=False
    )
    map_name: Mapped[str] = mapped_column(String(16), nullable=False)
    cell_x: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cell_y: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
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
