from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.path_security import resolve_path_within
from app.repositories.defect_repository import DefectRepository
from app.repositories.agent_decision_repository import AgentDecisionRepository
from app.repositories.game_event_repository import GameEventRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.run_repository import RunRepository
from app.serializers.agent_decision_serializers import AgentDecisionOut
from app.serializers.defect_serializers import DefectOut
from app.serializers.game_event_serializers import PositionTrailOut, TraceEntryOut
from collections import Counter
from pydantic import BaseModel

from app.core.behavior_profiles import PROFILES, BehaviorProfileName
from app.serializers.run_serializers import RunCompareOut, RunCreate, RunListOut, RunOut
from app.services.analysis_constants import CELL_SIZE
from app.services.run_compare_service import RunCompareService
from app.services.run_service import RunService
from app.services.run_utils import (
    _build_same_run_memory,
    _initial_lockstep_state,
    _record_decision_in_history,
)


class BehaviorUpdatePayload(BaseModel):
    behavior_profile: BehaviorProfileName


router = APIRouter(prefix="/runs", tags=["Runs"])


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).create_run(payload)


@router.get("", response_model=RunListOut)
async def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    wad_file_id: UUID | None = None,
    map_name: str | None = None,
    outcome: str | None = None,
    status: str | None = None,
    difficulty_level: int | None = Query(default=None, ge=1, le=5),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> RunListOut:
    repo = RunRepository(db)
    filters = {
        "wad_file_id": wad_file_id,
        "map_name": map_name,
        "outcome": outcome,
        "status": status,
        "difficulty_level": difficulty_level,
        "created_after": created_after,
        "created_before": created_before,
    }
    total = await repo.count(**filters)
    items = await repo.list(limit=limit, offset=offset, **filters)
    for run in items:
        run.map_display_name = (
            run.static_analysis.map_display_name
            if run.static_analysis is not None
            else None
        )
    return RunListOut(total=total, items=items, offset=offset)


@router.get("/compare", response_model=RunCompareOut)
async def compare_runs(
    run_a: UUID, run_b: UUID, db: AsyncSession = Depends(get_db)
) -> RunCompareOut:
    return await RunCompareService(db).compare(run_a, run_b)


@router.get("/batch-trails")
async def batch_trails(
    ids: str = Query(..., description="Comma-separated run IDs"),
    limit: int = Query(default=80, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    run_ids = [UUID(rid.strip()) for rid in ids.split(",") if rid.strip()]
    if len(run_ids) > 50:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Maximum 50 run IDs per request"
        )
    event_repo = GameEventRepository(db)
    result: dict[str, list[dict[str, Any]]] = {}
    for run_id in run_ids:
        trail = await event_repo.list_position_trail(run_id, limit=limit)
        result[str(run_id)] = [
            {"tick_number": t.tick_number, "health": t.health, "x": t.x, "y": t.y}
            for t in trail
        ]
    return result


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    run.map_display_name = (
        run.static_analysis.map_display_name
        if run.static_analysis is not None
        else None
    )
    return run


@router.get("/{run_id}/live-snapshot", tags=["Trace"])
async def get_live_snapshot(
    run_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")

    decision_repo = AgentDecisionRepository(db)
    event_repo = GameEventRepository(db)
    defect_repo = DefectRepository(db)
    decisions = await decision_repo.list_by_run(run_id, 1, 200)
    trace = await event_repo.list_trace(run_id, 1, 200)
    events = await event_repo.list_events(
        run_id,
        [
            "kill",
            "death",
            "item_pickup",
            "secret_found",
            "stuck",
            "damage_taken",
            "map_exit",
        ],
    )
    trail = await event_repo.list_position_trail(run_id, limit=500)
    defects = await defect_repo.list_by_run(run_id)
    report_status = await _report_status_payload(run_id, run, db)
    usage = _usage_payload(run, decisions)
    latest_state = _latest_state_payload(run, trace[-1] if trace else None)

    return jsonable_encoder(
        {
            "run": RunOut.model_validate(run).model_dump(mode="json"),
            "state": latest_state,
            "decisions": [
                AgentDecisionOut.model_validate(item).model_dump(mode="json")
                for item in decisions
            ],
            "trace": [
                TraceEntryOut.model_validate(item).model_dump(mode="json")
                for item in trace
            ],
            "events": [
                TraceEntryOut.model_validate(item).model_dump(mode="json")
                for item in events
            ],
            "position_trail": [
                PositionTrailOut.model_validate(item).model_dump(mode="json")
                for item in trail
            ],
            "defects": [
                DefectOut.model_validate(item).model_dump(mode="json")
                for item in defects
            ],
            "usage": usage,
            "progress_metrics": run.progress_metrics or {},
            "agent_quality_flags": run.agent_quality_flags or {},
            "report_status": report_status,
            "same_run_memory": _persisted_same_run_memory(
                run, decisions, trace, defects
            ),
            "visited_cells": _visited_cells_from_trail(trail),
            "visited_cell_size": CELL_SIZE,
        }
    )


async def _report_status_payload(
    run_id: UUID, run: Any, db: AsyncSession
) -> dict[str, Any]:
    report = await ReportRepository(db).get_by_run(run_id)
    if report is None:
        terminal = run.status in {"completed", "cancelled", "failed"}
        if run.error_message and "Report generation failed:" in run.error_message:
            return {
                "status": "error",
                "report_id": None,
                "pdf_available": False,
                "pdf_url": None,
                "generation_error": run.error_message,
            }
        return {
            "status": "missing" if terminal else "pending",
            "report_id": None,
            "pdf_available": False,
            "pdf_url": None,
            "generation_error": None,
        }
    pdf_available = bool(
        report.pdf_path
        and Path(get_settings().report_storage_dir.parent, report.pdf_path).exists()
    )
    status_value = report.generation_status
    if status_value == "complete" and not pdf_available:
        status_value = "missing"
    if (
        status_value == "generating"
        and not pdf_available
        and run.status in {"completed", "cancelled", "failed"}
    ):
        status_value = "missing"
    return {
        "status": status_value,
        "report_id": str(report.id),
        "pdf_available": pdf_available,
        "pdf_url": f"/runs/{run_id}/report/pdf" if pdf_available else None,
        "generation_error": report.generation_error,
    }


def _usage_payload(run: Any, decisions: list[Any]) -> dict[str, Any]:
    total_prompt = sum(item.llm_input_tokens or 0 for item in decisions)
    total_completion = sum(item.llm_output_tokens or 0 for item in decisions)
    total_cost = sum(item.llm_cost_estimate_usd or 0 for item in decisions)
    return {
        "run_id": str(run.id),
        "model": run.llm_model,
        "total_llm_calls": len(decisions),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "estimated_cost_usd": round(total_cost, 6),
        "per_decision_avg_cost_usd": round(total_cost / max(len(decisions), 1), 8),
    }


def _latest_state_payload(run: Any, event: Any | None) -> dict[str, Any] | None:
    if event is None:
        return {"type": "state", "status": run.status, "tick": 0}
    return {
        "type": "state",
        "tick": event.tick_number,
        "status": run.status,
        "health": event.health,
        "armor": event.armor,
        "kills": event.kill_count,
        "secrets": event.secret_count,
        "ammo": {
            "bullets": event.ammo_bullets,
            "shells": event.ammo_shells,
            "rockets": event.ammo_rockets,
            "cells": event.ammo_cells,
        },
        "position": {
            "x": event.player_x,
            "y": event.player_y,
            "angle": event.player_angle,
        },
        "event_type": event.event_type,
        "llm_reasoning": event.llm_reasoning,
        "action": event.action_taken or {},
    }


def _visited_cells_from_trail(trail: list[Any]) -> dict[str, int]:
    cells: Counter[str] = Counter()
    for sample in trail:
        cells[f"{round(sample.x / CELL_SIZE)},{round(sample.y / CELL_SIZE)}"] += 1
    return dict(cells)


def _persisted_same_run_memory(
    run: Any,
    decisions: list[Any],
    trace: list[Any],
    defects: list[Any],
) -> dict[str, Any]:
    state = _initial_lockstep_state()
    state["defects_found"] = [
        {
            "defect_type": item.defect_type,
            "title": item.title,
            "severity": item.severity,
        }
        for item in defects
    ]
    state["checkpoints"] = [
        {
            "tick": event.tick_number,
            "event": event.event_type,
            "pos": {"x": round(event.player_x, 1), "y": round(event.player_y, 1)},
        }
        for event in trace
        if event.event_type != "normal"
    ][-15:]
    for item in decisions:
        output = item.mcp_output if isinstance(item.mcp_output, dict) else {}
        summary = (
            output.get("action_summary")
            if isinstance(output.get("action_summary"), dict)
            else {}
        )
        _record_decision_in_history(
            state,
            seq=item.sequence_number,
            tick_before=item.tick_before or 0,
            tick_after=item.tick_after or item.tick_before or 0,
            tool=item.mcp_tool or "pending",
            stop_reason=item.mcp_stop_reason,
            params=item.mcp_input or {},
            reasoning=item.reasoning_summary,
            guard_modified=False,
            llm_duration_ms=float(item.llm_duration_ms or 0),
            mcp_duration_ms=float(item.mcp_duration_ms or 0),
            total_budget=int(run.max_ticks or 0),
            action_summary=summary,
            state_after=output,
            decision_source=item.decision_source,
            observed_issue=(item.llm_decision or {}).get("observed_issue"),
        )
    return _build_same_run_memory(state)


@router.patch("/{run_id}/behavior", response_model=RunOut)
async def update_run_behavior(
    run_id: UUID,
    payload: BehaviorUpdatePayload,
    db: AsyncSession = Depends(get_db),
) -> RunOut:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if payload.behavior_profile not in PROFILES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown behavior profile '{payload.behavior_profile}'. "
            f"Valid options: {', '.join(PROFILES)}",
        )
    await RunRepository(db).update(run, behavior_profile=payload.behavior_profile)
    await db.commit()
    await db.refresh(run)
    return run


@router.delete("/{run_id}", response_model=RunOut)
async def cancel_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.post("/{run_id}/force-stop", response_model=RunOut)
async def force_stop_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await RunService(db).cancel(run_id)


@router.get(
    "/{run_id}/trace",
    response_model=list[TraceEntryOut],
    tags=["Trace"],
    summary="Full ordered action trace",
)
async def get_trace(
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TraceEntryOut]:
    return await GameEventRepository(db).list_trace(run_id, page, page_size)


@router.get(
    "/{run_id}/events",
    response_model=list[TraceEntryOut],
    tags=["Trace"],
    summary="Notable or filtered run events",
)
async def get_events(
    run_id: UUID,
    type: Optional[str] = Query(
        default=None,
        description=(
            "Comma-separated list of event types to filter. "
            "When omitted, this endpoint returns only notable events where event_type != normal. "
            "Use /trace for the full ordered action history. "
            "Valid values: normal, kill, death, damage_taken, item_pickup, "
            "secret_found, map_exit, stuck. "
            "Example: ?type=kill,death,damage_taken"
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[TraceEntryOut]:
    event_types = [value.strip() for value in (type or "").split(",") if value.strip()]
    return await GameEventRepository(db).list_events(run_id, event_types)


@router.get(
    "/{run_id}/decisions",
    response_model=list[AgentDecisionOut],
    tags=["Trace"],
    summary="Full ordered LLM/MCP decision trace",
)
async def get_decisions(
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[AgentDecisionOut]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return await AgentDecisionRepository(db).list_by_run(run_id, page, page_size)


@router.get("/{run_id}/defects", response_model=list[DefectOut], tags=["Reports"])
async def get_defects(
    run_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[DefectOut]:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return await DefectRepository(db).list_by_run(run_id)


@router.get(
    "/{run_id}/position-trail", response_model=list[PositionTrailOut], tags=["Trace"]
)
async def get_position_trail(
    run_id: UUID,
    limit: int | None = Query(default=None, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> list[PositionTrailOut]:
    return await GameEventRepository(db).list_position_trail(run_id, limit=limit)


@router.get(
    "/{run_id}/recording",
    responses={200: {"content": {"video/mp4": {}}, "description": "MP4 recording"}},
    response_class=FileResponse,
)
async def get_recording(
    run_id: UUID, db: AsyncSession = Depends(get_db)
) -> FileResponse:
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if not run.recording_mp4_path:
        if run.failure_category == "pwad_crash" or run.outcome == "pwad_crash":
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                {
                    "error": "recording_not_available",
                    "reason": "No recording exists because the PWAD crashed or failed before gameplay initialized.",
                    "failure_category": run.failure_category or "pwad_crash",
                    "failure_stage": run.failure_stage,
                },
            )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    try:
        resolved = resolve_path_within(
            run.recording_mp4_path, get_settings().recording_storage_dir
        )
    except ValueError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    if not resolved.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording file is missing")
    return FileResponse(resolved, media_type="video/mp4")


@router.get("/{run_id}/usage", tags=["Runs"])
async def get_run_usage(
    run_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Return aggregated token usage and cost for a run."""
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    decisions = await AgentDecisionRepository(db).list_by_run(run_id, 1, 500)
    decisions_list = (
        list(decisions)
        if isinstance(decisions, list)
        else list(decisions.scalars().all())
        if hasattr(decisions, "scalars")
        else []
    )
    total_prompt = sum(d.llm_input_tokens or 0 for d in decisions_list)
    total_completion = sum(d.llm_output_tokens or 0 for d in decisions_list)
    total_cost = sum(d.llm_cost_estimate_usd or 0 for d in decisions_list)
    return {
        "run_id": str(run_id),
        "model": run.llm_model,
        "total_llm_calls": len(decisions_list),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "estimated_cost_usd": round(total_cost, 6),
        "per_decision_avg_cost_usd": round(total_cost / max(len(decisions_list), 1), 8),
    }


@router.get("/{run_id}/benchmark", tags=["Runs"])
async def get_run_benchmark(
    run_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Return performance timing breakdown for a run."""
    decisions = await AgentDecisionRepository(db).list_by_run(run_id, 1, 500)
    decisions_list = (
        list(decisions)
        if isinstance(decisions, list)
        else list(decisions.scalars().all())
        if hasattr(decisions, "scalars")
        else []
    )
    llm_times = [
        d.llm_duration_ms for d in decisions_list if d.llm_duration_ms is not None
    ]
    mcp_times = [
        d.mcp_duration_ms for d in decisions_list if d.mcp_duration_ms is not None
    ]

    def _stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"avg": 0, "p50": 0, "p95": 0, "max": 0, "min": 0, "count": 0}
        sorted_v = sorted(values)
        n = len(sorted_v)
        return {
            "avg": round(sum(values) / n, 1),
            "p50": round(sorted_v[n // 2], 1),
            "p95": round(sorted_v[int(n * 0.95)], 1),
            "max": round(max(values), 1),
            "min": round(min(values), 1),
            "count": n,
        }

    return {
        "run_id": str(run_id),
        "total_decisions": len(decisions_list),
        "llm_latency_ms": _stats(llm_times),
        "mcp_latency_ms": _stats(mcp_times),
        "tools_used": dict(Counter(d.mcp_tool or "unknown" for d in decisions_list)),
    }
