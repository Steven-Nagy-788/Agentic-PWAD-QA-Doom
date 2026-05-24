from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.wad_file import WadFile


class WadKnowledgeBase(Base):
    __tablename__ = "wad_knowledge_base"
    __table_args__ = (
        UniqueConstraint("wad_file_id", "map_name", name="uq_knowledge_wad_map"),
        Index("idx_knowledge_wad_map", "wad_file_id", "map_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    wad_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wad_files.id", ondelete="CASCADE"), nullable=False
    )
    map_name: Mapped[str] = mapped_column(String(16), nullable=False)
    document_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    wad_file: Mapped[WadFile] = relationship("WadFile")
