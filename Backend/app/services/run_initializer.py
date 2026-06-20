"""Initialization logic for the lockstep agent run loop.

Extracts Phase 1 (DB load + prompt build) and Phase 2 (MCP startup + env metadata)
into standalone helpers, keeping agent_run_task focused on the gameplay loop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.types import LockstepState
from app.models import StaticAnalysisResult, TestRun
from app.repositories.config_repository import ConfigRepository
from app.repositories.run_repository import RunRepository
from app.repositories.wad_repository import WadRepository
from app.services.gemini_service import GeminiService
from app.services.recording_service import RecordingService
from app.services.run_utils import (
    _bounded_float,
    _bounded_int,
    _estimate_total_map_cells,
    _initial_lockstep_state,
    _json_safe,
)
from app.services.environment_service import collect_environment_metadata
from app.services.prompt_service import render_agent_prompt
from app.services.run_utils import get_behavior_profile
import hashlib


logger = logging.getLogger(__name__)


async def _build_cross_run_memory_context(
    db: AsyncSession,
    wad_file_id: UUID,
    map_name: str,
) -> str:
    """Build cross-run memory context from hypotheses and spatial memory."""
    from app.models import WadHypothesis, WadSpatialMemory

    parts: list[str] = []

    # High-confidence hypotheses from previous runs
    hyp_result = await db.execute(
        select(WadHypothesis)
        .where(
            WadHypothesis.wad_file_id == wad_file_id,
            WadHypothesis.map_name == map_name.upper(),
            WadHypothesis.confidence >= 0.5,
            WadHypothesis.refuted_at.is_(None),
        )
        .order_by(WadHypothesis.confidence.desc())
        .limit(10)
    )
    hypotheses = list(hyp_result.scalars().all())
    if hypotheses:
        hyp_lines = []
        for h in hypotheses:
            hyp_lines.append(
                f"- [{h.tag}] {h.content} (confidence: {h.confidence:.1f})"
            )
        parts.append("CROSS-RUN HYPOTHESES:\n" + "\n".join(hyp_lines))

    # Spatial memory: high-death or high-stuck cells
    spatial_result = await db.execute(
        select(WadSpatialMemory)
        .where(
            WadSpatialMemory.wad_file_id == wad_file_id,
            WadSpatialMemory.map_name == map_name.upper(),
            WadSpatialMemory.event_type.in_(["death", "stuck"]),
            WadSpatialMemory.occurrence_count >= 3,
        )
        .order_by(WadSpatialMemory.occurrence_count.desc())
        .limit(10)
    )
    spatial = list(spatial_result.scalars().all())
    if spatial:
        spatial_lines = []
        for s in spatial:
            spatial_lines.append(
                f"- Cell ({s.cell_x},{s.cell_y}): {s.event_type} x{s.occurrence_count}"
            )
        parts.append("KNOWN DANGER ZONES:\n" + "\n".join(spatial_lines))

    if not parts:
        return ""
    return (
        "## CROSS-RUN MEMORY (from previous runs on this map)\n"
        + "\n\n".join(parts)
        + "\n\nUse this as context only. Do not blindly follow old hypotheses—verify through gameplay."
    )


async def _build_per_decision_cross_run_context(
    db: AsyncSession,
    wad_file_id: UUID,
    map_name: str,
    player_x: float,
    player_y: float,
    cell_size: int = 256,
) -> dict[str, Any]:
    """Build per-decision cross-run context with danger zones near player."""
    from app.models import WadHypothesis, WadSpatialMemory, TestRun

    cx = round(player_x / cell_size)
    cy = round(player_y / cell_size)

    # Danger zones within 5-cell radius
    spatial_result = await db.execute(
        select(WadSpatialMemory)
        .where(
            WadSpatialMemory.wad_file_id == wad_file_id,
            WadSpatialMemory.map_name == map_name.upper(),
            WadSpatialMemory.event_type.in_(["death", "stuck"]),
            WadSpatialMemory.occurrence_count >= 1,
            WadSpatialMemory.cell_x.between(cx - 5, cx + 5),
            WadSpatialMemory.cell_y.between(cy - 5, cy + 5),
        )
        .order_by(WadSpatialMemory.occurrence_count.desc())
        .limit(10)
    )
    danger_zones = [
        {
            "cell_x": s.cell_x,
            "cell_y": s.cell_y,
            "event": s.event_type,
            "count": s.occurrence_count,
            "distance_cells": max(abs(s.cell_x - cx), abs(s.cell_y - cy)),
        }
        for s in spatial_result.scalars().all()
    ]

    # High-confidence hypotheses
    hyp_result = await db.execute(
        select(WadHypothesis)
        .where(
            WadHypothesis.wad_file_id == wad_file_id,
            WadHypothesis.map_name == map_name.upper(),
            WadHypothesis.confidence >= 0.4,
            WadHypothesis.refuted_at.is_(None),
        )
        .order_by(WadHypothesis.confidence.desc())
        .limit(5)
    )
    hypotheses = [
        {"tag": h.tag, "content": h.content, "confidence": h.confidence}
        for h in hyp_result.scalars().all()
    ]

    # Last 3 run summaries for same map
    runs_result = await db.execute(
        select(TestRun)
        .where(
            TestRun.wad_file_id == wad_file_id,
            TestRun.map_name == map_name.upper(),
            TestRun.status == "completed",
        )
        .order_by(TestRun.created_at.desc())
        .limit(3)
    )
    run_summaries = []
    for run in runs_result.scalars().all():
        run_summaries.append(
            {
                "outcome": run.outcome,
                "total_kills": run.total_kills,
                "final_hp": run.final_hp,
                "duration_seconds": run.duration_seconds,
            }
        )

    return {
        "danger_zones": danger_zones,
        "hypotheses": hypotheses,
        "run_summaries": run_summaries,
    }


@dataclass
class RunInitContext:
    """All values extracted from DB + config during Phase 1 of run initialization.

    After the short-lived DB session closes, the run loop works only with
    these primitive values — no ORM objects leak into the long-lived scope.
    """

    run_id: UUID
    wad_file_id: UUID
    map_name: str
    max_ticks: int
    seed: int | None
    iwad_used: str
    difficulty_level: str
    llm_model: str
    prompt: str

    # Paths
    wad_stored_path: str
    map_overview_png_path: str | None = None
    map_bounds_for_layout: dict[str, float] | None = None

    # Recording
    recording_fps: float = 24.0
    live_frame_fps: float = 1.0
    recording_telemetry_stride: int = 3

    # LLM config
    gemini_rate_limit: int = 10
    llm_input_cost_per_million: float = 0.0
    llm_output_cost_per_million: float = 0.0
    llm_throttle_cap_seconds: float = 0.0

    # Computed
    total_map_cells_estimate: int | None = None


async def load_run_init_context(run_id: UUID) -> RunInitContext | None:
    """Phase 1: Load all run data from DB in a short-lived session.

    Returns RunInitContext with all primitive values extracted, or None
    if the run/WAD/analysis is missing (caller should abort).
    """
    async with SessionLocal() as db:
        run_orm = await db.get(TestRun, run_id)
        if run_orm is None:
            return None

        wad = await WadRepository(db).get_by_id(run_orm.wad_file_id)
        analysis = (
            await db.get(StaticAnalysisResult, run_orm.static_analysis_id)
            if run_orm.static_analysis_id
            else None
        )

        if wad is None or analysis is None:
            await RunRepository(db).update(
                run_orm,
                status="failed",
                outcome="error",
                error_message="Run is missing WAD or static analysis",
            )
            await db.commit()
            return None

        settings = get_settings()
        runtime_overrides = await ConfigRepository(db).get_all()

        def runtime_value(key: str, fallback: Any = None) -> Any:
            return runtime_overrides.get(key, getattr(settings, key, fallback))

        profile = get_behavior_profile(run_orm)
        total_map_cells_estimate = _estimate_total_map_cells(analysis)
        prompt = (
            render_agent_prompt(wad, analysis, run_orm)
            + "\n\n"
            + profile.system_prompt_addendum
        )

        # Conditionally inject cross-run memory
        cross_run_enabled = runtime_value(
            "cross_run_memory_enabled", settings.cross_run_memory_enabled
        )
        if cross_run_enabled:
            cross_run_context = await _build_cross_run_memory_context(
                db, run_orm.wad_file_id, run_orm.map_name
            )
            if cross_run_context:
                prompt += f"\n\n{cross_run_context}"

        # Extract primitive values before session closes
        map_bounds_raw = (
            (analysis.spawn_summary_by_skill or {})
            .get("_map_features", {})
            .get("bounds")
            if analysis
            else None
        )
        map_bounds_for_layout = None
        if isinstance(map_bounds_raw, dict):
            try:
                map_bounds_for_layout = {
                    "min_x": float(map_bounds_raw["min_x"]),
                    "max_x": float(map_bounds_raw["max_x"]),
                    "min_y": float(map_bounds_raw["min_y"]),
                    "max_y": float(map_bounds_raw["max_y"]),
                }
            except (KeyError, TypeError, ValueError):
                pass

        return RunInitContext(
            run_id=run_orm.id,
            wad_file_id=run_orm.wad_file_id,
            map_name=run_orm.map_name,
            max_ticks=run_orm.max_ticks,
            seed=run_orm.seed,
            iwad_used=run_orm.iwad_used,
            difficulty_level=run_orm.difficulty_level,
            llm_model=run_orm.llm_model,
            prompt=prompt,
            wad_stored_path=wad.stored_path,
            map_overview_png_path=getattr(analysis, "map_overview_png_path", None),
            map_bounds_for_layout=map_bounds_for_layout,
            recording_fps=max(
                15.0,
                _bounded_float(
                    runtime_value("recording_fps", settings.recording_fps),
                    settings.recording_fps,
                ),
            ),
            live_frame_fps=max(
                0.1,
                _bounded_float(
                    runtime_value("live_frame_fps", settings.live_frame_fps),
                    settings.live_frame_fps,
                ),
            ),
            recording_telemetry_stride=_bounded_int(
                runtime_value(
                    "recording_telemetry_stride", settings.recording_telemetry_stride
                ),
                settings.recording_telemetry_stride,
                lower=1,
                upper=10,
            ),
            gemini_rate_limit=_bounded_int(
                runtime_value(
                    "gemini_rate_limit_calls_per_minute",
                    settings.gemini_rate_limit_calls_per_minute,
                ),
                settings.gemini_rate_limit_calls_per_minute,
                lower=0,
            ),
            llm_input_cost_per_million=_bounded_float(
                runtime_value(
                    "llm_input_cost_per_million", settings.llm_input_cost_per_million
                ),
                settings.llm_input_cost_per_million,
            ),
            llm_output_cost_per_million=_bounded_float(
                runtime_value(
                    "llm_output_cost_per_million", settings.llm_output_cost_per_million
                ),
                settings.llm_output_cost_per_million,
            ),
            llm_throttle_cap_seconds=_bounded_float(
                runtime_value("llm_throttle_seconds", settings.llm_throttle_seconds),
                settings.llm_throttle_seconds,
            ),
            total_map_cells_estimate=total_map_cells_estimate,
        )


def init_lockstep_state(ctx: RunInitContext) -> LockstepState:
    """Create the initial lockstep state populated with map estimate."""
    state = _initial_lockstep_state()
    if ctx.total_map_cells_estimate is not None:
        state["total_map_cells_estimate"] = ctx.total_map_cells_estimate
    return state


def init_recorder(ctx: RunInitContext) -> RecordingService:
    """Create the recording service."""
    return RecordingService(str(ctx.run_id), fps=ctx.recording_fps)


def init_gemini(ctx: RunInitContext) -> GeminiService:
    """Create the Gemini service."""
    return GeminiService(
        llm_model=ctx.llm_model,
        rate_limit_calls_per_minute=ctx.gemini_rate_limit,
    )


async def start_game_and_mark_running(
    mcp: McpDoomClient,  # noqa: F821
    ctx: RunInitContext,
) -> dict[str, Any]:
    """Phase 2: Start MCP game, collect environment metadata, mark run as running.

    Returns environment_metadata dict for storage.
    """
    await mcp.start_game(
        wad=ctx.iwad_used,
        scenario_wad=ctx.wad_stored_path,
        map_name=ctx.map_name,
        difficulty=ctx.difficulty_level,
        episode_timeout=ctx.max_ticks,
        async_player=False,
        seed=ctx.seed,
    )

    try:
        mcp_metadata = await mcp.get_runtime_metadata()
    except Exception:
        mcp_metadata = {}

    environment_metadata = await collect_environment_metadata(
        mcp_metadata,
        model=ctx.llm_model,
        iwad=ctx.iwad_used,
        difficulty=ctx.difficulty_level,
        max_ticks=ctx.max_ticks,
        seed=ctx.seed,
    )

    # Mark run as running
    prompt_hash = hashlib.sha256(ctx.prompt.encode()).hexdigest()
    async with SessionLocal() as db:
        run_orm = await db.get(TestRun, ctx.run_id)
        if run_orm is not None:
            await RunRepository(db).update(
                run_orm,
                status="running",
                started_at=datetime.now(UTC),
                environment_metadata=_json_safe(environment_metadata),
                system_prompt_hash=prompt_hash,
                system_prompt_text=ctx.prompt,
            )
            await db.commit()

    return environment_metadata
