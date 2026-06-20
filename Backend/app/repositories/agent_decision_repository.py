from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentDecision


class AgentDecisionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, decision: AgentDecision) -> AgentDecision:
        self.db.add(decision)
        await self.db.flush()
        await self.db.refresh(decision)
        return decision

    async def update(self, decision: AgentDecision, **fields: object) -> AgentDecision:
        for key, value in fields.items():
            setattr(decision, key, value)
        await self.db.flush()
        await self.db.refresh(decision)
        return decision

    async def list_by_run(
        self, run_id: UUID, page: int, page_size: int
    ) -> list[AgentDecision]:
        result = await self.db.execute(
            select(AgentDecision)
            .where(AgentDecision.run_id == run_id)
            .order_by(AgentDecision.sequence_number)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all())
