from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.routers import admin_storage, analysis, reports, runs, wads, ws
from app.services.gemini_service import GeminiService
from app.services.mcp_client_service import probe_mcp_sse_url
from app.services.run_service import fail_orphaned_active_runs


settings = get_settings()


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
    async with SessionLocal() as db:
        await fail_orphaned_active_runs(db, reason="Orphaned by server restart")
        await db.commit()
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

app.include_router(wads.router)
app.include_router(analysis.router)
app.include_router(runs.router)
app.include_router(reports.router)
app.include_router(ws.router)
app.include_router(admin_storage.router)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/gemini", tags=["Health"])
async def gemini_health_check() -> dict[str, str]:
    try:
        result = await GeminiService().probe_model()
        return {"status": "ok", "model": result["model"], "response": result["response"][:200]}
    except Exception as exc:
        return {"status": "error", "model": settings.llm_model, "error": str(exc)}


@app.get("/health/mcp", tags=["Health"])
async def mcp_health_check() -> dict[str, object]:
    result = await probe_mcp_sse_url()
    return {"status": "ok" if result.get("reachable") else "error", **result}
