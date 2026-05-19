from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.test_run import TestRun
    from app.models.wad_file import WadFile


class StaticAnalysisResult(Base):
    __tablename__ = "static_analysis_results"
    __table_args__ = (UniqueConstraint("wad_file_id", "map_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    wad_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wad_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    map_name: Mapped[str] = mapped_column(String(16), nullable=False)

    thing_count_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    thing_count_enemies: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    thing_count_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    thing_count_keys: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    thing_count_weapons: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    linedef_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sector_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    secret_sector_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    vertex_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    map_width_units: Mapped[int | None] = mapped_column(Integer)
    map_height_units: Mapped[int | None] = mapped_column(Integer)

    total_monster_hp: Mapped[int | None] = mapped_column(Integer)
    total_health_pickup_pts: Mapped[int | None] = mapped_column(Integer)
    total_armor_pickup_pts: Mapped[int | None] = mapped_column(Integer)
    hitscanner_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    health_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    ammo_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    estimated_difficulty: Mapped[str | None] = mapped_column(String(16))

    enemy_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    item_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    map_title: Mapped[str | None] = mapped_column(Text)
    map_display_name: Mapped[str | None] = mapped_column(Text)
    map_title_source: Mapped[str | None] = mapped_column(String(32))
    spawn_summary_by_skill: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    map_overview_png_path: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    wad_file: Mapped[WadFile] = relationship("WadFile", back_populates="static_analysis_results")
    test_runs: Mapped[list[TestRun]] = relationship(
        "TestRun",
        back_populates="static_analysis",
        foreign_keys="TestRun.static_analysis_id",
    )
