from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Defect, GameEvent, StaticAnalysisResult, TestRun
from app.repositories.defect_repository import DefectRepository


class DefectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DefectRepository(db)

    async def detect_for_run(self, run: TestRun) -> None:
        result = await self.db.execute(select(GameEvent).where(GameEvent.run_id == run.id).order_by(GameEvent.tick_number))
        events = list(result.scalars().all())
        if not events:
            return
        await self._repeated_deaths(run.id, events)
        await self._ammo_starvation(run.id, events)
        await self._health_deficit(run.id, events)
        await self._softlock(run, events)
        await self._unreachable_secrets(run, events)

    async def _repeated_deaths(self, run_id: UUID, events: list[GameEvent]) -> None:
        buckets: dict[tuple[int, int], list[GameEvent]] = defaultdict(list)
        for event in events:
            if event.event_type == "death":
                buckets[(round(event.player_x / 50), round(event.player_y / 50))].append(event)
        for group in buckets.values():
            if len(group) > 1:
                first = group[0]
                await self.repo.create(
                    Defect(
                        run_id=run_id,
                        severity=2,
                        priority=1,
                        defect_type="repeated_death_location",
                        title="Repeated death location",
                        description="The agent died more than once in the same 50-unit area.",
                        detected_at_tick=first.tick_number,
                        position_x=first.player_x,
                        position_y=first.player_y,
                    )
                )

    async def _ammo_starvation(self, run_id: UUID, events: list[GameEvent]) -> None:
        streak = []
        for event in events:
            if event.ammo_bullets + event.ammo_shells + event.ammo_rockets + event.ammo_cells == 0:
                streak.append(event)
            else:
                streak = []
            if len(streak) > 60:
                first = streak[0]
                await self.repo.create(
                    Defect(
                        run_id=run_id,
                        severity=2,
                        priority=2,
                        defect_type="ammo_starvation",
                        title="Ammo starvation",
                        description="The agent had no ammo for more than 60 consecutive ticks.",
                        detected_at_tick=first.tick_number,
                        position_x=first.player_x,
                        position_y=first.player_y,
                    )
                )
                return

    async def _health_deficit(self, run_id: UUID, events: list[GameEvent]) -> None:
        streak = []
        for event in events:
            if event.health < 10:
                streak.append(event)
            else:
                streak = []
            if len(streak) > 30:
                first = streak[0]
                await self.repo.create(
                    Defect(
                        run_id=run_id,
                        severity=3,
                        priority=3,
                        defect_type="health_deficit",
                        title="Sustained health deficit",
                        description="The agent remained below 10 HP for more than 30 ticks.",
                        detected_at_tick=first.tick_number,
                        position_x=first.player_x,
                        position_y=first.player_y,
                    )
                )
                return

    async def _softlock(self, run: TestRun, events: list[GameEvent]) -> None:
        if run.outcome != "timeout" or len(events) < 120:
            return
        tail = events[-120:]
        moved = max(event.player_x for event in tail) - min(event.player_x for event in tail)
        moved += max(event.player_y for event in tail) - min(event.player_y for event in tail)
        if moved < 20:
            first = tail[0]
            await self.repo.create(
                Defect(
                    run_id=run.id,
                    severity=1,
                    priority=1,
                    defect_type="softlock_navigation",
                    title="Potential navigation softlock",
                    description="The run timed out with little movement in the final 120 ticks.",
                    detected_at_tick=first.tick_number,
                    position_x=first.player_x,
                    position_y=first.player_y,
                )
            )

    async def _unreachable_secrets(self, run: TestRun, events: list[GameEvent]) -> None:
        if run.static_analysis_id is None:
            return
        analysis = await self.db.get(StaticAnalysisResult, run.static_analysis_id)
        if analysis and analysis.secret_sector_count > 0 and max(event.secret_count for event in events) == 0:
            await self.repo.create(
                    Defect(
                        run_id=run.id,
                        severity=3,
                        priority=3,
                        defect_type="unreachable_secret",
                        title="Secrets not reached",
                        description="Static analysis found secret sectors, but the agent never entered one.",
                        detected_at_tick=events[-1].tick_number,
                    )
                )
