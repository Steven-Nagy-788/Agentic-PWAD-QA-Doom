from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings as _get_settings
from app.core.behavior_profiles import PROFILES
from app.core.database import get_db
from app.repositories.config_repository import ConfigRepository

router = APIRouter(tags=["Settings"])


class SettingsUpdatePayload(BaseModel):
    llm_model: Optional[str] = None
    llm_throttle_seconds: Optional[float] = None
    gemini_rate_limit_calls_per_minute: Optional[int] = None
    llm_input_cost_per_million: Optional[float] = None
    llm_output_cost_per_million: Optional[float] = None
    max_run_ticks: Optional[int] = None
    default_run_ticks: Optional[int] = None
    live_frame_fps: Optional[float] = None
    recording_fps: Optional[float] = None
    recording_telemetry_stride: Optional[int] = None
    default_agent_behavior: Optional[str] = None
    iwad_used: Optional[str] = None


def _merge_settings(env: Any, overrides: dict[str, Any]) -> dict[str, Any]:
    return {
        "app_name": env.app_name,
        "app_env": env.app_env,
        "llm_model": overrides.get("llm_model", env.llm_model),
        "llm_throttle_seconds": overrides.get("llm_throttle_seconds", env.llm_throttle_seconds),
        "gemini_rate_limit_calls_per_minute": overrides.get(
            "gemini_rate_limit_calls_per_minute",
            env.gemini_rate_limit_calls_per_minute,
        ),
        "llm_input_cost_per_million": overrides.get("llm_input_cost_per_million", env.llm_input_cost_per_million),
        "llm_output_cost_per_million": overrides.get("llm_output_cost_per_million", env.llm_output_cost_per_million),
        "max_run_ticks": overrides.get("max_run_ticks", env.max_run_ticks),
        "default_run_ticks": overrides.get("default_run_ticks", env.default_run_ticks),
        "live_frame_fps": overrides.get("live_frame_fps", env.live_frame_fps),
        "recording_fps": overrides.get("recording_fps", env.recording_fps),
        "recording_telemetry_stride": overrides.get("recording_telemetry_stride", env.recording_telemetry_stride),
        "default_agent_behavior": overrides.get("default_agent_behavior", env.default_agent_behavior),
        "iwad_used": overrides.get("iwad_used", env.iwad_used),
    }


@router.get("/settings")
async def settings_route(db: AsyncSession = Depends(get_db)) -> dict:
    env = _get_settings()
    overrides = await ConfigRepository(db).get_all()
    return _merge_settings(env, overrides)


@router.patch("/settings")
async def update_settings(
    payload: SettingsUpdatePayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    overrides = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if overrides:
        await ConfigRepository(db).set_many(overrides)
        await db.commit()
    env = _get_settings()
    all_overrides = await ConfigRepository(db).get_all()
    return _merge_settings(env, all_overrides)


@router.get("/settings/behavior-profiles")
def behavior_profiles_route() -> dict:
    return {
        name: {
            "name": p.name,
            "description": p.description,
            "default_stride": p.default_stride,
            "combat_stride": p.combat_stride,
            "stuck_stride": p.stuck_stride,
        }
        for name, p in PROFILES.items()
    }
