from functools import lru_cache
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


class Settings:
    def __init__(self) -> None:
        _load_dotenv(BASE_DIR / ".env")

        self.app_name = os.getenv("APP_NAME", "Doom Agentic Testing Backend")
        self.app_env = os.getenv("APP_ENV", "development")
        self.debug = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes", "on"}

        self.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.postgres_db = os.getenv("POSTGRES_DB", "doom_agentic_qa")
        self.postgres_user = os.getenv("POSTGRES_USER", "doom_agentic")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD", "doom_agentic_password")
        default_database_url = (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
        self.database_url = os.getenv(
            "DATABASE_URL",
            default_database_url,
        ).replace("postgresql+psycopg://", "postgresql+asyncpg://")

        self.storage_dir = self._resolve_path(os.getenv("STORAGE_BASE") or os.getenv("STORAGE_DIR", "storage"))
        self.wad_storage_dir = self._resolve_path(os.getenv("WAD_STORAGE_DIR", str(self.storage_dir / "wads")))
        self.report_storage_dir = self._resolve_path(os.getenv("REPORT_STORAGE_DIR", str(self.storage_dir / "reports")))
        self.recording_storage_dir = self._resolve_path(
            os.getenv("RECORDING_STORAGE_DIR", str(self.storage_dir / "recordings"))
        )
        self.screenshot_storage_dir = self._resolve_path(
            os.getenv("SCREENSHOT_STORAGE_DIR", str(self.storage_dir / "screenshots"))
        )
        self.analysis_storage_dir = self._resolve_path(
            os.getenv("ANALYSIS_STORAGE_DIR", str(self.storage_dir / "analysis"))
        )

        self.iwad_used = os.getenv("IWAD_USED", "freedoom2")
        self.llm_model = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.llm_throttle_seconds = float(os.getenv("LLM_THROTTLE_SECONDS", "12"))
        self.gemini_retry_max_delay_seconds = float(os.getenv("GEMINI_RETRY_MAX_DELAY_SECONDS", "20"))
        self.mcp_doom_sse_url = os.getenv("MCP_DOOM_SSE_URL", "http://localhost:8001/sse")
        self.max_run_ticks = int(os.getenv("MAX_RUN_TICKS", "35000"))
        self.default_run_ticks = int(os.getenv("DEFAULT_RUN_TICKS", "3000"))
        self.live_frame_fps = float(os.getenv("LIVE_FRAME_FPS", "2"))
        self.recording_telemetry_stride = int(os.getenv("RECORDING_TELEMETRY_STRIDE", "1"))
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]

    @staticmethod
    def _resolve_path(value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
