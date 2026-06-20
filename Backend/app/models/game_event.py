from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    REAL,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.notable_event_screenshot import NotableEventScreenshot
    from app.models.test_run import TestRun


class GameEvent(Base):
    __tablename__ = "game_events"
    __table_args__ = (
        Index("idx_game_events_run_id", "run_id"),
        Index("idx_game_events_run_id_tick", "run_id", "tick_number"),
        Index(
            "idx_game_events_notable",
            "run_id",
            "event_type",
            postgresql_where=text("event_type != 'normal'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tick_number: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    player_x: Mapped[float] = mapped_column(REAL, nullable=False)
    player_y: Mapped[float] = mapped_column(REAL, nullable=False)
    player_angle: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    health: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    armor: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ammo_bullets: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ammo_shells: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ammo_rockets: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ammo_cells: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kill_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    item_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    secret_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    weapon_selected: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    action_taken: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_reasoning: Mapped[str | None] = mapped_column(Text)
    llm_input_summary: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'normal'")
    )
    killed_enemy_type: Mapped[str | None] = mapped_column(String(64))
    damage_received: Mapped[int | None] = mapped_column(SmallInteger)

    run: Mapped[TestRun] = relationship("TestRun", back_populates="game_events")
    screenshots: Mapped[list[NotableEventScreenshot]] = relationship(
        "NotableEventScreenshot",
        back_populates="game_event",
        cascade="all, delete-orphan",
    )
