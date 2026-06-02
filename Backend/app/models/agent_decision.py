from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, REAL, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.game_event import GameEvent
    from app.models.test_run import TestRun


class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_number", name="uq_agent_decisions_run_sequence"),
        Index("idx_agent_decisions_run_id", "run_id"),
        Index("idx_agent_decisions_run_id_sequence", "run_id", "sequence_number"),
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
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_before: Mapped[int | None] = mapped_column(Integer)
    tick_after: Mapped[int | None] = mapped_column(Integer)
    game_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("game_events.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'started'"))
    error_message: Mapped[str | None] = mapped_column(Text)
    llm_input_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_llm_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reasoning_summary: Mapped[str | None] = mapped_column(Text)
    mcp_tool: Mapped[str | None] = mapped_column(String(64))
    mcp_input: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mcp_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mcp_stop_reason: Mapped[str | None] = mapped_column(String(64))
    guard_modified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    guard_reason: Mapped[str | None] = mapped_column(Text)
    decision_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="gemini", server_default=text("'gemini'")
    )
    llm_duration_ms: Mapped[float | None] = mapped_column(REAL)
    mcp_duration_ms: Mapped[float | None] = mapped_column(REAL)
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_cost_estimate_usd: Mapped[float | None] = mapped_column(REAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[TestRun] = relationship("TestRun", back_populates="agent_decisions")
    game_event: Mapped[GameEvent | None] = relationship("GameEvent", foreign_keys=[game_event_id])

    @property
    def validation_rejection(self) -> str | None:
        output = self.mcp_output if isinstance(self.mcp_output, dict) else {}
        summary = output.get("action_summary") if isinstance(output.get("action_summary"), dict) else {}
        value = summary.get("validation_error")
        return str(value) if value else None
