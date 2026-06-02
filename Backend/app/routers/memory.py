from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Defect, TestRun, WadHypothesis, WadSpatialMemory


router = APIRouter(prefix="/wads", tags=["Memory"])


@router.get("/{wad_id}/memory/{map_name}")
async def get_wad_map_memory(
    wad_id: UUID,
    map_name: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    map_name_upper = map_name.upper()

    spatial_result = await db.execute(
        select(
            WadSpatialMemory.cell_x,
            WadSpatialMemory.cell_y,
            WadSpatialMemory.event_type,
            func.sum(WadSpatialMemory.occurrence_count).label("total"),
        )
        .where(
            WadSpatialMemory.wad_file_id == wad_id,
            WadSpatialMemory.map_name == map_name_upper,
        )
        .group_by(
            WadSpatialMemory.cell_x,
            WadSpatialMemory.cell_y,
            WadSpatialMemory.event_type,
        )
    )
    spatial_cells = [
        {
            "cell_x": row.cell_x,
            "cell_y": row.cell_y,
            "event_type": row.event_type,
            "count": int(row.total or 0),
        }
        for row in spatial_result.all()
    ]

    hyp_result = await db.execute(
        select(WadHypothesis)
        .where(
            WadHypothesis.wad_file_id == wad_id,
            WadHypothesis.map_name == map_name_upper,
            WadHypothesis.refuted_at.is_(None),
        )
        .order_by(WadHypothesis.confidence.desc())
        .limit(20)
    )
    hypotheses_list = [
        {
            "tag": hyp.tag,
            "content": hyp.content,
            "confidence": round(float(hyp.confidence), 2),
            "evidence_status": "confirmed" if hyp.confirmed_at else "candidate",
        }
        for hyp in hyp_result.scalars().all()
    ]

    run_result = await db.execute(
        select(TestRun.id, TestRun.outcome).where(
            TestRun.wad_file_id == wad_id,
            TestRun.map_name == map_name_upper,
        )
    )
    run_rows = run_result.all()
    run_ids = [row.id for row in run_rows]
    outcome_counts: dict[str, int] = {}
    for row in run_rows:
        outcome = str(row.outcome or "unknown")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
    recurring = []
    if run_ids:
        distinct_run_count = func.count(func.distinct(Defect.run_id))
        defect_result = await db.execute(
            select(
                Defect.fingerprint,
                Defect.defect_type,
                Defect.title,
                func.count(Defect.id).label("occurrence_count"),
                distinct_run_count.label("run_count"),
            )
            .where(
                Defect.run_id.in_(run_ids),
                Defect.fingerprint.isnot(None),
                Defect.resolution_status != "candidate",
            )
            .group_by(Defect.fingerprint, Defect.defect_type, Defect.title)
            .having(distinct_run_count >= 2)
            .order_by(distinct_run_count.desc())
        )
        recurring = [
            {
                "fingerprint": row.fingerprint,
                "defect_type": row.defect_type,
                "title": row.title,
                "occurrences": int(row.occurrence_count or 0),
                "run_count": int(row.run_count or 0),
            }
            for row in defect_result.all()
        ]

    return {
        "wad_id": str(wad_id),
        "map_name": map_name_upper,
        "summary_counts": {
            "prior_run_count": len(run_ids),
            "outcome_counts": outcome_counts,
        },
        "spatial_cells": spatial_cells,
        "hypotheses": hypotheses_list,
        "recurring_defects": recurring,
    }
