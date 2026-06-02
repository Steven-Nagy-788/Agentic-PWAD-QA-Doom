from contextlib import asynccontextmanager
from datetime import UTC, datetime
import os
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.routers import admin_storage, analysis, memory, patterns, reports, runs, settings as settings_router, wads, ws
from app.services.gemini_service import GeminiService
import app.core.metrics
from app.services.mcp_client_service import probe_mcp_sse_url
from app.services.smoke_service import SmokeService
from app.services.run_service import fail_orphaned_active_runs
from app.services.run_constants import RUN_TASKS
from app.repositories.config_repository import ConfigRepository
from app.models.test_run import TestRun
from sqlalchemy import select, func, text


settings = get_settings()
_gemini_probe_cache: dict[str, Any] | None = None


async def _effective_llm_model() -> tuple[str, str]:
    async with SessionLocal() as db:
        override = await ConfigRepository(db).get("llm_model")
    return (
        (str(override), "database_override")
        if override
        else (get_settings().llm_model, "environment")
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    for path in [
        settings.storage_dir,
        settings.wad_storage_dir,
        settings.report_storage_dir,
        settings.recording_storage_dir,
        settings.screenshot_storage_dir,
        settings.analysis_storage_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    import app.models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await fail_orphaned_active_runs(db, reason="Orphaned by server restart")
        await db.commit()
    try:
        import sentry_sdk
        has_sentry = True
    except ImportError:
        has_sentry = False
    if has_sentry and settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment="production" if not settings.debug else "development",
        )
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    description="Backend API for autonomous Doom PWAD QA runs.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wads.router, prefix="/v1")
app.include_router(analysis.router, prefix="/v1")
app.include_router(runs.router, prefix="/v1")
app.include_router(reports.router, prefix="/v1")
app.include_router(ws.router, prefix="/v1")
app.include_router(patterns.router, prefix="/v1")
app.include_router(admin_storage.router, prefix="/v1")
app.include_router(settings_router.router, prefix="/v1")
app.include_router(memory.router, prefix="/v1")


@app.get("/metrics", tags=["Metrics"])
def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/gemini", tags=["Health"])
async def gemini_health_check() -> dict[str, Any]:
    model, source = await _effective_llm_model()
    if not settings.gemini_api_key:
        return {"status": "error", "configured": False, "model": model, "model_source": source}
    return {
        "status": _gemini_probe_cache.get("status", "configured") if _gemini_probe_cache else "configured",
        "configured": True,
        "model": model,
        "model_source": source,
        "environment_default": get_settings().llm_model,
        "last_probe": _gemini_probe_cache,
    }


@app.post("/health/gemini/probe", tags=["Health"])
async def probe_gemini_health() -> dict[str, Any]:
    global _gemini_probe_cache
    model, source = await _effective_llm_model()
    try:
        result = await GeminiService(llm_model=model).probe_model()
        _gemini_probe_cache = {
            "status": "ok",
            "model": result["model"],
            "model_source": source,
            "response": result["response"][:200],
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        _gemini_probe_cache = {
            "status": "error",
            "model": model,
            "model_source": source,
            "error": str(exc),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    return _gemini_probe_cache


@app.get("/health/mcp", tags=["Health"])
async def mcp_health_check() -> dict[str, object]:
    result = await probe_mcp_sse_url()
    return {"status": "ok" if result.get("reachable") else "error", **result}


@app.get("/health/smoke", tags=["Health"])
async def smoke_health_check():
    if RUN_TASKS:
        return JSONResponse(
            content={"overall": "skip", "stages": [], "reason": "Active run in progress — smoke check would conflict."},
            status_code=503,
        )
    model, source = await _effective_llm_model()
    result = await SmokeService(llm_model=model, model_source=source).run_smoke()
    status_code = 200 if result["overall"] == "pass" else 503
    return JSONResponse(content=result, status_code=status_code)


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check():
    deps: dict[str, object] = {}

    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        deps["postgres"] = {"status": "ok"}
    except Exception as exc:
        deps["postgres"] = {"status": "error", "error": str(exc)}

    try:
        mcp_result = await probe_mcp_sse_url()
        deps["mcp"] = {
            "status": "ok" if mcp_result.get("reachable") else "error",
            **mcp_result,
        }
    except Exception as exc:
        deps["mcp"] = {"status": "error", "error": str(exc)}

    deps["gemini"] = {"status": "ok" if settings.gemini_api_key else "error"}

    storage_statuses = {}
    for path in [
        settings.storage_dir,
        settings.wad_storage_dir,
        settings.report_storage_dir,
        settings.recording_storage_dir,
        settings.screenshot_storage_dir,
        settings.analysis_storage_dir,
    ]:
        storage_statuses[str(path.relative_to(settings.storage_dir.parent))] = (
            "ok" if path.is_dir() and os.access(path, os.W_OK) else "error"
        )
    deps["storage"] = {"status": "ok" if all(v == "ok" for v in storage_statuses.values()) else "error", "dirs": storage_statuses}

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(func.count()).where(TestRun.status.in_(("pending", "analyzing", "running")))
            )
            active_count = result.scalar()
        deps["run_status"] = {"status": "ok", "active_runs": active_count}
    except Exception as exc:
        deps["run_status"] = {"status": "error", "error": str(exc)}

    overall = "ok" if all(
        dep.get("status") == "ok" for dep in deps.values()
        if isinstance(dep, dict)
    ) else "degraded"
    return {"status": overall, "dependencies": deps}
