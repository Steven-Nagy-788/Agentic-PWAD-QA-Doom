from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
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
    same_run_ledger_max_chars: Optional[int] = None
    same_run_ledger_recent_actions: Optional[int] = None
    no_progress_decision_abort_threshold: Optional[int] = None
    default_agent_behavior: Optional[str] = None
    iwad_used: Optional[str] = None
    cross_run_memory_enabled: Optional[bool] = None
    guard_enabled: Optional[bool] = None
    clear_overrides: list[str] = Field(default_factory=list)

    @field_validator("clear_overrides")
    @classmethod
    def validate_clear_overrides(cls, values: list[str]) -> list[str]:
        unknown = sorted(set(values) - OVERRIDABLE_KEYS)
        if unknown:
            raise ValueError(f"Unknown setting override(s): {', '.join(unknown)}")
        return values


OVERRIDABLE_KEYS = set(SettingsUpdatePayload.model_fields) - {"clear_overrides"}


def _merge_settings(env: Any, overrides: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "app_name": env.app_name,
        "app_env": env.app_env,
        "llm_model": overrides.get("llm_model", env.llm_model),
        "llm_throttle_seconds": overrides.get(
            "llm_throttle_seconds", env.llm_throttle_seconds
        ),
        "gemini_rate_limit_calls_per_minute": overrides.get(
            "gemini_rate_limit_calls_per_minute",
            env.gemini_rate_limit_calls_per_minute,
        ),
        "llm_input_cost_per_million": overrides.get(
            "llm_input_cost_per_million", env.llm_input_cost_per_million
        ),
        "llm_output_cost_per_million": overrides.get(
            "llm_output_cost_per_million", env.llm_output_cost_per_million
        ),
        "max_run_ticks": overrides.get("max_run_ticks", env.max_run_ticks),
        "default_run_ticks": overrides.get("default_run_ticks", env.default_run_ticks),
        "live_frame_fps": overrides.get("live_frame_fps", env.live_frame_fps),
        "recording_fps": overrides.get("recording_fps", env.recording_fps),
        "recording_telemetry_stride": overrides.get(
            "recording_telemetry_stride", env.recording_telemetry_stride
        ),
        "same_run_ledger_max_chars": overrides.get(
            "same_run_ledger_max_chars", env.same_run_ledger_max_chars
        ),
        "same_run_ledger_recent_actions": overrides.get(
            "same_run_ledger_recent_actions",
            env.same_run_ledger_recent_actions,
        ),
        "no_progress_decision_abort_threshold": overrides.get(
            "no_progress_decision_abort_threshold",
            env.no_progress_decision_abort_threshold,
        ),
        "default_agent_behavior": overrides.get(
            "default_agent_behavior", env.default_agent_behavior
        ),
        "iwad_used": overrides.get("iwad_used", env.iwad_used),
        "cross_run_memory_enabled": overrides.get(
            "cross_run_memory_enabled", env.cross_run_memory_enabled
        ),
        "guard_enabled": overrides.get("guard_enabled", env.guard_enabled),
    }
    env_defaults = {key: getattr(env, key) for key in OVERRIDABLE_KEYS}
    merged["sources"] = {
        key: "database_override" if key in overrides else "environment"
        for key in OVERRIDABLE_KEYS
    }
    merged["env_defaults"] = env_defaults
    return merged


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
    clear_overrides = payload.clear_overrides
    overrides = {
        k: v
        for k, v in payload.model_dump(
            exclude_none=True, exclude={"clear_overrides"}
        ).items()
    }
    for key in clear_overrides:
        await ConfigRepository(db).delete(key)
    if overrides:
        await ConfigRepository(db).set_many(overrides)
    if overrides or clear_overrides:
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
        }
        for name, p in PROFILES.items()
    }


class AblationApplyPayload(BaseModel):
    config_name: str


@router.get("/settings/ablation/configs")
async def list_ablation_configs() -> dict:
    from app.services.ablation_study import list_ablation_configs, get_ablation_config

    names = list_ablation_configs()
    configs = {}
    for name in names:
        cfg = get_ablation_config(name)
        if cfg:
            configs[name] = {
                "name": cfg.name,
                "description": cfg.description,
                "disabled_components": list(cfg.disabled_components),
            }
    return {"configs": configs}


@router.post("/settings/ablation/apply")
async def apply_ablation_config(
    payload: AblationApplyPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.ablation_study import get_ablation_config, get_runtime_overrides

    config = get_ablation_config(payload.config_name)
    if config is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Config '{payload.config_name}' not found")

    overrides = get_runtime_overrides(config)
    await ConfigRepository(db).set_many(overrides)
    await db.commit()
    return {"status": "applied", "config": payload.config_name, "overrides": overrides}


@router.post("/settings/ablation/reset")
async def reset_ablation_config(
    db: AsyncSession = Depends(get_db),
) -> dict:
    keys = [
        "guard_enabled",
        "cross_run_memory_enabled",
        "deterministic_fallback_enabled",
        "execution_time_monitor_enabled",
    ]
    for key in keys:
        await ConfigRepository(db).delete(key)
    await db.commit()
    return {"status": "reset", "cleared": keys}
