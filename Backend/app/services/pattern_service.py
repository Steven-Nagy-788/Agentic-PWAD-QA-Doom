from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Defect, TestRun
from app.services.analysis_constants import CELL_SIZE


class PatternService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_patterns(self, wad_id: UUID) -> dict[str, Any]:
        runs_result = await self.db.execute(
            select(TestRun).where(TestRun.wad_file_id == wad_id)
        )
        runs = list(runs_result.scalars().all())
        run_ids = [r.id for r in runs]

        if not run_ids:
            return {
                "wad_id": str(wad_id),
                "total_runs": 0,
                "defect_patterns": [],
                "difficulty_coverage": {},
            }

        defects_result = await self.db.execute(
            select(Defect).where(Defect.run_id.in_(run_ids))
        )
        defects = list(defects_result.scalars().all())

        by_fingerprint = defaultdict(list)
        for d in defects:
            key = d.fingerprint or f"{d.defect_type}:{d.title}"
            by_fingerprint[key].append(d)

        by_cell = defaultdict(list)
        for d in defects:
            if d.position_x is not None and d.position_y is not None:
                cell = (
                    round(d.position_x / CELL_SIZE),
                    round(d.position_y / CELL_SIZE),
                )
                by_cell[cell].append(d)

        by_difficulty = defaultdict(
            lambda: {"runs": 0, "completed": 0, "failed": 0, "defects": 0}
        )
        for r in runs:
            diff = r.difficulty_level or "unknown"
            by_difficulty[diff]["runs"] += 1
            if r.outcome == "map_completed":
                by_difficulty[diff]["completed"] += 1
            elif r.outcome in ("stuck", "error", "pwad_crash"):
                by_difficulty[diff]["failed"] += 1
        for d in defects:
            diff = str(d.run.difficulty_level) if d.run else "unknown"
            by_difficulty[diff]["defects"] += 1

        defect_patterns = []
        for fingerprint, group in by_fingerprint.items():
            if len(group) >= 2:
                cells = set()
                for d in group:
                    if d.position_x is not None and d.position_y is not None:
                        cells.add(
                            (
                                round(d.position_x / CELL_SIZE),
                                round(d.position_y / CELL_SIZE),
                            )
                        )
                defect_patterns.append(
                    {
                        "fingerprint": fingerprint,
                        "defect_type": group[0].defect_type,
                        "title": group[0].title,
                        "occurrence_count": len(group),
                        "affected_runs": len(set(d.run_id for d in group)),
                        "avg_severity": round(
                            sum(d.severity for d in group) / len(group), 1
                        ),
                        "grid_clusters": [{"x": c[0], "y": c[1]} for c in cells],
                    }
                )

        defect_patterns.sort(key=lambda p: p["occurrence_count"], reverse=True)

        return {
            "wad_id": str(wad_id),
            "total_runs": len(runs),
            "total_defects": len(defects),
            "defect_patterns": defect_patterns[:20],
            "defect_clusters": [
                {"cell": {"x": c[0], "y": c[1]}, "count": len(g)}
                for c, g in sorted(by_cell.items(), key=lambda x: -len(x[1]))[:10]
            ],
            "difficulty_coverage": dict(by_difficulty),
        }
