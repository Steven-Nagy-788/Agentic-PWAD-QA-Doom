from __future__ import annotations

from collections import defaultdict
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Defect, GameEvent, StaticAnalysisResult, TestRun
from app.repositories.defect_repository import DefectRepository
from app.services.analysis_service import selected_skill_spawn_summary


class DefectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DefectRepository(db)

    async def detect_for_run(self, run: TestRun) -> None:
        await self._pwad_crash(run)
        analysis = await self.db.get(StaticAnalysisResult, run.static_analysis_id) if run.static_analysis_id else None
        await self._difficulty_spawn_mismatch(run, analysis)
        result = await self.db.execute(select(GameEvent).where(GameEvent.run_id == run.id).order_by(GameEvent.tick_number))
        events = list(result.scalars().all())
        if not events:
            return
        await self._repeated_deaths(run.id, events)
        await self._ammo_starvation(run.id, events)
        await self._health_deficit(run.id, events)
        await self._softlock(run, events)
        await self._unreachable_secrets(run, events, analysis)

    async def _pwad_crash(self, run: TestRun) -> None:
        if run.failure_category != "pwad_crash" and run.outcome != "pwad_crash":
            return
        await self.repo.create(
            Defect(
                run_id=run.id,
                severity=1,
                priority=1,
                defect_type="pwad_crash",
                title="PWAD crashed or failed to initialize",
                description=(
                    run.failure_summary
                    or "The PWAD could not be initialized by the configured ViZDoom/Freedoom test runtime."
                ),
                detected_at_tick=0,
                recommendation=(
                    "Open the WAD in a Doom editor/source port, verify map markers and required resources, "
                    "and compare with the raw runtime diagnostic stored on the run."
                ),
            )
        )

    async def _difficulty_spawn_mismatch(self, run: TestRun, analysis: StaticAnalysisResult | None) -> None:
        if analysis is None:
            return
        skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
        spawned_enemies = int(skill_summary.get("thing_count_enemies") or 0)
        spawned_items = int(skill_summary.get("thing_count_items") or 0)
        raw_enemies = int(analysis.thing_count_enemies or 0)
        raw_items = int(analysis.thing_count_items or 0)
        if spawned_enemies >= raw_enemies and spawned_items >= raw_items:
            return
        if raw_enemies == 0 and raw_items == 0:
            return
        hidden_parts = []
        if spawned_enemies < raw_enemies:
            hidden_parts.append(f"{raw_enemies - spawned_enemies} of {raw_enemies} enemies")
        if spawned_items < raw_items:
            hidden_parts.append(f"{raw_items - spawned_items} of {raw_items} items")
        severity = 2 if raw_enemies and spawned_enemies == 0 else 3
        await self.repo.create(
            Defect(
                run_id=run.id,
                severity=severity,
                priority=2,
                defect_type="difficulty_spawn_mismatch",
                title="Difficulty-specific thing flags hide map content",
                description=(
                    f"At difficulty {run.difficulty_level}, {' and '.join(hidden_parts)} from raw static analysis "
                    "do not spawn in single-player because of Doom skill or multiplayer flags."
                ),
                detected_at_tick=0,
                recommendation=(
                    "Review THINGS difficulty flags in the map editor, or run QA at a skill where the intended "
                    "combat and pickups are enabled."
                ),
            )
        )

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
                        description="The automated playthrough died more than once in the same 50-unit area.",
                        detected_at_tick=first.tick_number,
                        position_x=first.player_x,
                        position_y=first.player_y,
                    )
                )

    async def _ammo_starvation(self, run_id: UUID, events: list[GameEvent]) -> None:
        episodes = _streak_episodes(
            events,
            lambda event: event.ammo_bullets + event.ammo_shells + event.ammo_rockets + event.ammo_cells == 0,
            minimum_length=61,
        )
        for episode in episodes:
            first = episode[0]
            await self.repo.create(
                Defect(
                    run_id=run_id,
                    severity=2,
                    priority=2,
                    defect_type="ammo_starvation",
                    fingerprint=f"ammo_starvation:{first.tick_number}",
                    title="Ammo starvation",
                    description="The automated playthrough had no ammo for more than 60 consecutive ticks.",
                    detected_at_tick=first.tick_number,
                    position_x=first.player_x,
                    position_y=first.player_y,
                    first_seen_tick=first.tick_number,
                    last_seen_tick=episode[-1].tick_number,
                    occurrence_count=len(episode),
                )
            )

    async def _health_deficit(self, run_id: UUID, events: list[GameEvent]) -> None:
        episodes = _streak_episodes(events, lambda event: event.health < 10, minimum_length=31)
        for episode in episodes:
            first = episode[0]
            await self.repo.create(
                Defect(
                    run_id=run_id,
                    severity=3,
                    priority=3,
                    defect_type="health_deficit",
                    fingerprint=f"health_deficit:{first.tick_number}",
                    title="Sustained health deficit",
                    description="The automated playthrough remained below 10 HP for more than 30 ticks.",
                    detected_at_tick=first.tick_number,
                    position_x=first.player_x,
                    position_y=first.player_y,
                    first_seen_tick=first.tick_number,
                    last_seen_tick=episode[-1].tick_number,
                    occurrence_count=len(episode),
                )
            )

    async def _softlock(self, run: TestRun, events: list[GameEvent]) -> None:
        stuck_events = [event for event in events if event.event_type == "stuck"]
        if run.outcome in {"stuck", "timeout"} and len(stuck_events) >= 3:
            first = stuck_events[0]
            if run.outcome == "timeout":
                run.outcome = "stuck"
            await self.repo.create(
                Defect(
                    run_id=run.id,
                    severity=1,
                    priority=1,
                    defect_type="softlock_navigation",
                    title="Run stalled after repeated stuck decisions",
                    description=(
                        "The run produced repeated stuck events with no meaningful progress. "
                        "This usually indicates blocked navigation, unreachable objectives, or an automated control loop "
                        "that should be reviewed with the recording and action trace."
                    ),
                    detected_at_tick=first.tick_number,
                    position_x=first.player_x,
                    position_y=first.player_y,
                )
            )
            return

        if run.outcome != "timeout" or len(events) < 10:
            return
        tail = events[-min(30, len(events)):]
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
                    description="The run timed out with little movement in the final decision window.",
                    detected_at_tick=first.tick_number,
                    position_x=first.player_x,
                    position_y=first.player_y,
                )
            )

    async def _unreachable_secrets(
        self,
        run: TestRun,
        events: list[GameEvent],
        analysis: StaticAnalysisResult | None,
    ) -> None:
        if analysis and analysis.secret_sector_count > 0 and max(event.secret_count for event in events) == 0:
            await self.repo.create(
                Defect(
                    run_id=run.id,
                    severity=3,
                    priority=3,
                    defect_type="unreachable_secret",
                    title="Secrets not reached",
                    description="Static analysis found secret sectors, but the automated playthrough did not enter one.",
                    detected_at_tick=events[-1].tick_number,
                )
            )


def _streak_episodes(
    events: list[GameEvent],
    predicate: Callable[[GameEvent], bool],
    minimum_length: int,
) -> list[list[GameEvent]]:
    episodes: list[list[GameEvent]] = []
    streak: list[GameEvent] = []
    for event in events:
        if predicate(event):
            streak.append(event)
            continue
        if len(streak) >= minimum_length:
            episodes.append(streak)
        streak = []
    if len(streak) >= minimum_length:
        episodes.append(streak)
    return episodes
