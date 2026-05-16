from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.static_analysis_result import StaticAnalysisResult
    from app.models.test_run import TestRun


class WadFile(Base):
    __tablename__ = "wad_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    validation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'pending'"),
    )
    validation_error: Mapped[str | None] = mapped_column(Text)
    detected_maps: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    iwad_required: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'freedoom2'"))

    static_analysis_results: Mapped[list[StaticAnalysisResult]] = relationship(
        "StaticAnalysisResult",
        back_populates="wad_file",
        cascade="all, delete-orphan",
    )
    test_runs: Mapped[list[TestRun]] = relationship("TestRun", back_populates="wad_file")
