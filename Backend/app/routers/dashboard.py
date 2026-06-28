from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import (
    Defect,
    WadFile,
    TestRun,
    AgentDecision,
)
from app.serializers.dashboard_serializers import (
    DashboardStats,
    DashboardRecentRun,
    DashboardDefectSummary,
    DefectTypeBreakdown,
    DefectSeverityBreakdown,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    wad_count = (await db.execute(select(func.count(WadFile.id)))).scalar() or 0
    run_count = (await db.execute(select(func.count(TestRun.id)))).scalar() or 0
    defect_count = (await db.execute(select(func.count(Defect.id)))).scalar() or 0

    avg_coverage = (
        await db.execute(
            select(
                func.avg(
                    cast(TestRun.progress_metrics["coverage_pct"].astext, Float)
                )
            )
        )
    ).scalar()

    avg_kill_rate = (
        await db.execute(
            select(
                func.avg(
                    cast(
                        TestRun.progress_metrics["kill_rate_pct"].astext, Float
                    )
                )
            )
        )
    ).scalar()

    total_cost = (
        await db.execute(
            select(func.coalesce(func.sum(AgentDecision.llm_cost_estimate_usd), 0.0))
        )
    ).scalar() or 0.0

    status_rows = (
        await db.execute(
            select(TestRun.status, func.count(TestRun.id)).group_by(TestRun.status)
        )
    ).all()
    runs_by_status = {row[0]: row[1] for row in status_rows}

    outcome_rows = (
        await db.execute(
            select(
                func.coalesce(TestRun.outcome, "unknown"),
                func.count(TestRun.id),
            ).group_by(TestRun.outcome)
        )
    ).all()
    runs_by_outcome = {row[0]: row[1] for row in outcome_rows}

    return DashboardStats(
        total_wads=wad_count,
        total_runs=run_count,
        total_defects=defect_count,
        avg_coverage_pct=round(avg_coverage, 1) if avg_coverage is not None else None,
        avg_kill_rate_pct=round(avg_kill_rate, 1) if avg_kill_rate is not None else None,
        total_llm_cost_usd=round(total_cost, 4),
        runs_by_status=runs_by_status,
        runs_by_outcome=runs_by_outcome,
    )


@router.get("/recent-runs", response_model=list[DashboardRecentRun])
async def dashboard_recent_runs(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[DashboardRecentRun]:
    stmt = (
        select(
            TestRun.id,
            TestRun.map_name,
            TestRun.outcome,
            TestRun.difficulty_level,
            TestRun.progress_metrics,
            TestRun.total_kills,
            TestRun.duration_seconds,
            TestRun.created_at,
            TestRun.llm_model,
            WadFile.original_filename.label("wad_filename"),
        )
        .join(WadFile, TestRun.wad_file_id == WadFile.id)
        .order_by(TestRun.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    run_ids = [row[0] for row in rows]
    defect_counts: dict[UUID, int] = {}
    if run_ids:
        count_rows = (
            await db.execute(
                select(Defect.run_id, func.count(Defect.id))
                .where(Defect.run_id.in_(run_ids))
                .group_by(Defect.run_id)
            )
        ).all()
        defect_counts = {row[0]: row[1] for row in count_rows}

    cost_rows: dict[UUID, float] = {}
    if run_ids:
        costs = (
            await db.execute(
                select(
                    AgentDecision.run_id,
                    func.coalesce(func.sum(AgentDecision.llm_cost_estimate_usd), 0.0),
                )
                .where(AgentDecision.run_id.in_(run_ids))
                .group_by(AgentDecision.run_id)
            )
        ).all()
        cost_rows = {row[0]: float(row[1]) for row in costs}

    result = []
    for row in rows:
        run_id = row[0]
        pm = row[4] or {}
        spawned = pm.get("spawned_enemy_count")
        kills = row[5]
        coverage_pct = pm.get("coverage_pct")

        result.append(
            DashboardRecentRun(
                id=str(run_id),
                map_name=row[1],
                wad_filename=row[8] or "unknown",
                outcome=row[2],
                difficulty_level=row[3],
                coverage_pct=coverage_pct,
                total_kills=kills,
                spawned_enemies=spawned,
                defect_count=defect_counts.get(run_id, 0),
                duration_seconds=row[6],
                created_at=row[7].isoformat() if row[7] else "",
                llm_cost_usd=round(cost_rows.get(run_id, 0.0), 4),
            )
        )
    return result


@router.get("/defect-summary", response_model=DashboardDefectSummary)
async def dashboard_defect_summary(
    db: AsyncSession = Depends(get_db),
) -> DashboardDefectSummary:
    total = (await db.execute(select(func.count(Defect.id)))).scalar() or 0

    type_rows = (
        await db.execute(
            select(
                Defect.defect_type,
                func.count(Defect.id),
                func.avg(Defect.severity),
            ).group_by(Defect.defect_type)
        )
    ).all()
    by_type = [
        DefectTypeBreakdown(
            defect_type=r[0],
            count=r[1],
            avg_severity=round(r[2], 1) if r[2] else 0.0,
        )
        for r in type_rows
    ]

    severity_rows = (
        await db.execute(
            select(Defect.severity, func.count(Defect.id)).group_by(Defect.severity)
        )
    ).all()
    by_severity = [DefectSeverityBreakdown(severity=r[0], count=r[1]) for r in severity_rows]

    return DashboardDefectSummary(
        by_type=by_type,
        by_severity=by_severity,
        total_defects=total,
    )
