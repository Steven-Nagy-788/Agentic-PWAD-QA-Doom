from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import analysis, reports, runs, wads, ws
from app.services.gemini_service import GeminiService


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    description="Backend API for autonomous Doom PWAD QA runs.",
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


@app.on_event("startup")
async def ensure_storage_dirs() -> None:
    for path in [
        settings.storage_dir,
        settings.wad_storage_dir,
        settings.report_storage_dir,
        settings.recording_storage_dir,
        settings.screenshot_storage_dir,
        settings.analysis_storage_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


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
