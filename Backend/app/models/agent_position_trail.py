from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, REAL, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.test_run import TestRun


class AgentPositionTrail(Base):
    __tablename__ = "agent_position_trail"
    __table_args__ = (Index("idx_position_trail_run_id", "run_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tick_number: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[float] = mapped_column(REAL, nullable=False)
    y: Mapped[float] = mapped_column(REAL, nullable=False)
    angle: Mapped[float] = mapped_column(REAL, nullable=False, default=0)
    health: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_sentinel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    run: Mapped[TestRun] = relationship("TestRun", back_populates="position_trail")
