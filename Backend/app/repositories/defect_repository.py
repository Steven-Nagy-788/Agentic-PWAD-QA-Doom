from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Defect


class DefectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, defect: Defect) -> Defect:
        self._ensure_fingerprint(defect)
        if not defect.fingerprint:
            raise ValueError(f"Fingerprint is still None after _ensure_fingerprint for defect_type={defect.defect_type}")
        values = {
            column.name: getattr(defect, column.name)
            for column in Defect.__table__.columns
            if column.name != "id" and getattr(defect, column.name) is not None
        }
        tick = values.get("detected_at_tick")
        values.setdefault("first_seen_tick", tick)
        values.setdefault("last_seen_tick", tick)
        values.setdefault("occurrence_count", 1)
        statement = (
            insert(Defect)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["run_id", "fingerprint"],
                set_={
                    "last_seen_tick": values.get("last_seen_tick"),
                    "occurrence_count": Defect.occurrence_count + 1,
                },
            )
            .returning(Defect.id)
        )
        result = await self.db.execute(statement)
        defect_id = result.scalar_one_or_none()
        if defect_id is not None:
            created = await self.db.get(Defect, defect_id)
            assert created is not None
            return created

        existing = await self.db.execute(
            select(Defect).where(
                Defect.run_id == values["run_id"],
                Defect.fingerprint == values["fingerprint"],
            )
        )
        return existing.scalar_one()

    async def list_by_run(self, run_id: UUID) -> list[Defect]:
        result = await self.db.execute(
            select(Defect).where(Defect.run_id == run_id).order_by(Defect.severity, Defect.detected_at_tick)
        )
        return self.dedupe_defects(list(result.scalars().all()))

    async def exists_by_type_title(self, run_id: UUID, defect_type: str, title: str) -> bool:
        result = await self.db.execute(
            select(Defect.id)
            .where(
                Defect.run_id == run_id,
                Defect.defect_type == defect_type,
                Defect.title == title,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def dedupe_defects(defects: list[Defect]) -> list[Defect]:
        unique: list[Defect] = []
        seen: set[tuple[str, str | int | None]] = set()
        for defect in defects:
            signature = DefectRepository._dedupe_signature(defect)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(defect)
        return unique

    @staticmethod
    def _dedupe_signature(defect: Defect) -> tuple[str, str | int | None]:
        if defect.fingerprint:
            return ("fingerprint", defect.fingerprint)
        if defect.defect_type.startswith("agent_observed"):
            return ("agent_observed", defect.title)
        return (defect.defect_type, defect.detected_at_tick)

    @staticmethod
    def _ensure_fingerprint(defect: Defect) -> None:
        if defect.fingerprint:
            return
        title = defect.title or defect.defect_type
        title_slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:64] or "issue"
        if defect.defect_type.startswith("agent_observed"):
            defect.fingerprint = f"{defect.defect_type}:{title_slug}"[:128]
        elif defect.position_x is not None and defect.position_y is not None:
            bucket = f"{round(defect.position_x / 64)}_{round(defect.position_y / 64)}"
            defect.fingerprint = f"{defect.defect_type}:{title_slug}:{bucket}"[:128]
        else:
            defect.fingerprint = f"{defect.defect_type}:{title_slug}:{defect.detected_at_tick or 0}"[:128]
        if not defect.fingerprint:
            defect.fingerprint = f"{defect.defect_type}:{defect.detected_at_tick or 0}:{id(defect)}"[:128]
