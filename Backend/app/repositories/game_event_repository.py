from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentPositionTrail, GameEvent, NotableEventScreenshot


class GameEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_event(self, event: GameEvent) -> GameEvent:
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def create_position(self, position: AgentPositionTrail) -> AgentPositionTrail:
        self.db.add(position)
        await self.db.flush()
        return position

    async def create_screenshot(
        self, screenshot: NotableEventScreenshot
    ) -> NotableEventScreenshot:
        self.db.add(screenshot)
        await self.db.flush()
        return screenshot

    async def list_trace(
        self, run_id: UUID, page: int, page_size: int
    ) -> list[GameEvent]:
        result = await self.db.execute(
            select(GameEvent)
            .where(GameEvent.run_id == run_id)
            .order_by(GameEvent.tick_number, GameEvent.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all())

    async def list_events(
        self, run_id: UUID, event_types: list[str]
    ) -> list[GameEvent]:
        query = select(GameEvent).where(GameEvent.run_id == run_id)
        if event_types:
            query = query.where(GameEvent.event_type.in_(event_types))
        else:
            query = query.where(GameEvent.event_type != "normal")
        result = await self.db.execute(
            query.order_by(GameEvent.tick_number, GameEvent.id)
        )
        return list(result.scalars().all())

    async def list_position_trail(
        self, run_id: UUID, limit: int | None = None
    ) -> list[AgentPositionTrail]:
        query = (
            select(AgentPositionTrail)
            .where(AgentPositionTrail.run_id == run_id)
            .where(AgentPositionTrail.is_sentinel.is_(False))
        )
        if limit is not None:
            query = query.order_by(
                AgentPositionTrail.tick_number.desc(), AgentPositionTrail.id.desc()
            ).limit(limit)
            result = await self.db.execute(query)
            return list(reversed(result.scalars().all()))
        result = await self.db.execute(
            query.order_by(AgentPositionTrail.tick_number, AgentPositionTrail.id)
        )
        return list(result.scalars().all())
