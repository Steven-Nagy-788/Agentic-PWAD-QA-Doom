from __future__ import annotations

from collections import defaultdict
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Defect, GameEvent, NotableEventScreenshot, StaticAnalysisResult, TestRun
from app.repositories.defect_repository import DefectRepository
from app.services.analysis_service import selected_skill_spawn_summary


_RESOURCE_STOP_REASONS = {
    "out_of_ammo",
    "selected_weapon_empty",
    "no_usable_weapon",
    "no_usable_ranged_weapon",
    "melee_target_out_of_range",
    "weapon_switch_failed",
}


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
        await self._link_screenshots_to_defects(run.id)

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
        severity = 2 if raw_enemies and spawned_enemies < raw_enemies else 3
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
            lambda event: _event_usable_attack_ammo(event) == 0,
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
                    description=(
                        "The automated playthrough had no usable attack ammo or usable ranged weapon for more "
                        "than 60 consecutive ticks."
                    ),
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
            confirmed_stuck = [event for event in stuck_events if _is_confirmed_map_stuck_event(event)]
            if len(confirmed_stuck) >= 3:
                first = confirmed_stuck[0]
                if run.outcome == "timeout":
                    run.outcome = "stuck"
                await self.repo.create(
                    Defect(
                        run_id=run.id,
                        severity=1,
                        priority=1,
                        defect_type="softlock_navigation",
                        title="Run stalled after repeated confirmed navigation blocks",
                        description=(
                            "The run produced repeated movement/collision stuck evidence with no meaningful progress. "
                            "Review the recording and action trace for blocked navigation or unreachable objectives."
                        ),
                        detected_at_tick=first.tick_number,
                        position_x=first.player_x,
                        position_y=first.player_y,
                    )
                )
            else:
                first = stuck_events[0]
                run.outcome = "inconclusive_agent_stall"
                await self.repo.create(
                    Defect(
                        run_id=run.id,
                        severity=3,
                        priority=3,
                        defect_type="inconclusive_agent_stall",
                        title="Run stalled with inconclusive agent/tool evidence",
                        description=(
                            "The run produced repeated stuck-classified events, but the trace does not contain enough "
                            "collision or blocked-geometry evidence to call this a map softlock. Treat this as an "
                            "agent/tool limitation and review the action trace before filing a map defect."
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
            if _has_agent_or_resource_limitation(tail):
                run.outcome = "inconclusive_agent_stall"
                await self.repo.create(
                    Defect(
                        run_id=run.id,
                        severity=3,
                        priority=3,
                        defect_type="inconclusive_agent_stall",
                        title="Timeout with little movement and inconclusive agent/tool evidence",
                        description=(
                            "The run timed out with little final-window movement, but resource/tool recovery evidence "
                            "makes the map softlock conclusion inconclusive."
                        ),
                        detected_at_tick=first.tick_number,
                        position_x=first.player_x,
                        position_y=first.player_y,
                    )
                )
                return
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
        coverage_percent = _coverage_percent(run)
        if (
            analysis
            and analysis.secret_sector_count > 0
            and max(event.secret_count for event in events) == 0
            and coverage_percent >= 60.0
        ):
            await self.repo.create(
                Defect(
                    run_id=run.id,
                    severity=3,
                    priority=3,
                    defect_type="unreachable_secret",
                    title="Secrets not reached",
                    description=(
                        "Static analysis found secret sectors, but the automated playthrough did not enter one "
                        f"after reaching {coverage_percent:.1f}% coarse cell coverage."
                    ),
                    detected_at_tick=events[-1].tick_number,
                )
            )

    async def _link_screenshots_to_defects(self, run_id: UUID) -> None:
        screenshot_result = await self.db.execute(
            select(NotableEventScreenshot).where(NotableEventScreenshot.run_id == run_id)
        )
        screenshots: list[NotableEventScreenshot] = list(screenshot_result.scalars().all())
        if not screenshots:
            return
        event_to_screenshot = {s.game_event_id: s.id for s in screenshots}
        events_result = await self.db.execute(
            select(GameEvent.id, GameEvent.tick_number).where(GameEvent.run_id == run_id)
        )
        tick_to_event: dict[int, int] = {}
        for row in events_result:
            tick_to_event[row.tick_number] = row.id
        defects_result = await self.db.execute(
            select(Defect).where(
                Defect.run_id == run_id,
                Defect.screenshot_id.is_(None),
                Defect.detected_at_tick.isnot(None),
            )
        )
        for defect in defects_result.scalars().all():
            event_id = tick_to_event.get(defect.detected_at_tick)
            if event_id is not None and event_id in event_to_screenshot:
                defect.screenshot_id = event_to_screenshot[event_id]


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


def _event_usable_attack_ammo(event: GameEvent) -> int:
    action_taken = getattr(event, "action_taken", None)
    if isinstance(action_taken, dict):
        resource_state = action_taken.get("resource_state")
        if isinstance(resource_state, dict) and resource_state.get("usable_attack_ammo") is not None:
            return _safe_int(resource_state.get("usable_attack_ammo"))
        mcp_output = action_taken.get("mcp_output")
        if isinstance(mcp_output, dict):
            weapon_state = mcp_output.get("weapon_state")
            if isinstance(weapon_state, dict) and weapon_state.get("usable_attack_ammo") is not None:
                return _safe_int(weapon_state.get("usable_attack_ammo"))
    return int(event.ammo_bullets or 0) + int(event.ammo_shells or 0) + int(event.ammo_rockets or 0) + int(event.ammo_cells or 0)


def _is_confirmed_map_stuck_event(event: GameEvent) -> bool:
    action_taken = getattr(event, "action_taken", None)
    if not isinstance(action_taken, dict):
        return True
    summary = action_taken.get("mcp_action_summary")
    if not isinstance(summary, dict):
        output = action_taken.get("mcp_output")
        summary = output.get("action_summary") if isinstance(output, dict) else {}
    stop_reason = str(summary.get("stop_reason") or action_taken.get("mcp_stop_reason") or "")
    tool = str(action_taken.get("mcp_executed_tool") or action_taken.get("mcp_tool") or "")
    if stop_reason in {"stuck", "arrival_blocked"}:
        return True
    if stop_reason in _RESOURCE_STOP_REASONS or str(getattr(event, "event_type", "")) == "resource_recovery":
        return False
    if tool == "take_action" and stop_reason in {"tics_complete", ""}:
        return False
    return stop_reason == ""


def _has_agent_or_resource_limitation(events: list[GameEvent]) -> bool:
    return any(
        str(getattr(event, "event_type", "")) == "resource_recovery"
        or _event_stop_reason(event) in _RESOURCE_STOP_REASONS
        for event in events
    )


def _event_stop_reason(event: GameEvent) -> str:
    action_taken = getattr(event, "action_taken", None)
    if not isinstance(action_taken, dict):
        return ""
    if action_taken.get("mcp_stop_reason") is not None:
        return str(action_taken["mcp_stop_reason"])
    output = action_taken.get("mcp_output")
    summary = output.get("action_summary") if isinstance(output, dict) else None
    if isinstance(summary, dict) and summary.get("stop_reason") is not None:
        return str(summary["stop_reason"])
    return ""


def _safe_int(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _coverage_percent(run: TestRun) -> float:
    metrics = run.progress_metrics if isinstance(getattr(run, "progress_metrics", None), dict) else {}
    value = metrics.get("coverage_percent")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
