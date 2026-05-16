from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.game_event import GameEvent
    from app.models.test_run import TestRun


class NotableEventScreenshot(Base):
    __tablename__ = "notable_event_screenshots"
    __table_args__ = (Index("idx_screenshots_run_id", "run_id"),)

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
    game_event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("game_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    screenshot_path: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[TestRun] = relationship("TestRun", back_populates="screenshots")
    game_event: Mapped[GameEvent] = relationship("GameEvent", back_populates="screenshots")
