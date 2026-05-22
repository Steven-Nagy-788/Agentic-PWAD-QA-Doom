from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentPositionTrail, Defect, GameEvent, TestRun
from app.repositories.run_repository import RunRepository


class RunCompareService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def compare(self, run_a_id: UUID, run_b_id: UUID) -> dict[str, Any]:
        repo = RunRepository(self.db)
        run_a = await repo.get_by_id(run_a_id)
        run_b = await repo.get_by_id(run_b_id)
        if run_a is None or run_b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "One or both runs were not found")
        same_map = run_a.wad_file_id == run_b.wad_file_id and run_a.map_name == run_b.map_name
        if not same_map:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Runs must reference the same WAD and map")

        defects_a = await self._defects(run_a_id)
        defects_b = await self._defects(run_b_id)
        keys_a = set(defects_a)
        keys_b = set(defects_b)
        events_a = await self._events(run_a_id)
        events_b = await self._events(run_b_id)
        coverage_a = await self._movement_coverage(run_a_id)
        coverage_b = await self._movement_coverage(run_b_id)
        return {
            "run_a": run_a_id,
            "run_b": run_b_id,
            "same_map": same_map,
            "outcome_change": {"from": run_a.outcome, "to": run_b.outcome},
            "defects": {
                "present_in_both": [defects_b[key] for key in sorted(keys_a & keys_b)],
                "resolved": [defects_a[key] for key in sorted(keys_a - keys_b)],
                "new": [defects_b[key] for key in sorted(keys_b - keys_a)],
            },
            "kill_coverage_delta": {
                "run_a_kills": run_a.total_kills,
                "run_b_kills": run_b.total_kills,
                "delta": _none_safe_delta(run_b.total_kills, run_a.total_kills),
            },
            "movement_coverage_delta": {
                "run_a_cells": coverage_a,
                "run_b_cells": coverage_b,
                "delta": coverage_b - coverage_a,
            },
            "resource_delta": {
                "final_hp_delta": _none_safe_delta(run_b.final_hp, run_a.final_hp),
                "final_ammo_delta": _none_safe_delta(_last_ammo(events_b), _last_ammo(events_a)),
            },
        }

    async def _defects(self, run_id: UUID) -> dict[str, dict[str, Any]]:
        result = await self.db.execute(select(Defect).where(Defect.run_id == run_id))
        defects = {}
        for defect in result.scalars().all():
            key = defect.fingerprint or f"{defect.defect_type}:{defect.title}:{defect.detected_at_tick}"
            defects[key] = {
                "defect_type": defect.defect_type,
                "title": defect.title,
                "severity": defect.severity,
                "detected_at_tick": defect.detected_at_tick,
                "fingerprint": defect.fingerprint,
            }
        return defects

    async def _events(self, run_id: UUID) -> list[GameEvent]:
        result = await self.db.execute(select(GameEvent).where(GameEvent.run_id == run_id).order_by(GameEvent.tick_number))
        return list(result.scalars().all())

    async def _movement_coverage(self, run_id: UUID) -> float:
        result = await self.db.execute(select(AgentPositionTrail).where(AgentPositionTrail.run_id == run_id))
        cells = {(round(position.x / 128), round(position.y / 128)) for position in result.scalars().all()}
        return float(len(cells))


def _last_ammo(events: list[GameEvent]) -> int | None:
    if not events:
        return None
    event = events[-1]
    return event.ammo_bullets + event.ammo_shells + event.ammo_rockets + event.ammo_cells


def _none_safe_delta(new_value: int | None, old_value: int | None) -> int | None:
    if new_value is None or old_value is None:
        return None
    return new_value - old_value
