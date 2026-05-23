from functools import lru_cache
import os
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Doom Agentic Testing Backend"
    app_env: str = "development"
    debug: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "doom_agentic_qa"
    postgres_user: str = "doom_agentic"
    postgres_password: str = "doom_agentic_password"
    database_url: str | None = None

    storage_dir: Path = Field(default=Path("storage"), validation_alias=AliasChoices("STORAGE_BASE", "STORAGE_DIR"))
    wad_storage_dir: Path | None = None
    report_storage_dir: Path | None = None
    recording_storage_dir: Path | None = None
    screenshot_storage_dir: Path | None = None
    analysis_storage_dir: Path | None = None

    iwad_used: str = "freedoom2"
    llm_model: str = "gemini-2.5-flash-lite"
    gemini_api_key: str = ""
    llm_throttle_seconds: float = 12.0
    gemini_retry_max_delay_seconds: float = 20.0
    gemini_max_concurrency: int = 1
    mcp_doom_sse_url: str = "http://localhost:8001/sse"
    mcp_probe_timeout_seconds: float = 3.0
    mcp_tool_timeout_seconds: float = 30.0
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    max_run_ticks: int = 35000
    default_run_ticks: int = 3000
    live_frame_fps: float = 10.0
    recording_fps: float = 15.0
    recording_telemetry_stride: int = 2
    default_agent_behavior: str = "safety"
    cors_origins: list[str] | str = "http://localhost:3000"

    @field_validator("debug", mode="before")
    @classmethod
    def _parse_debug(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on", "debug", "development"}

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return []

    @field_validator("gemini_max_concurrency", "recording_telemetry_stride")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than 0")
        return value

    @field_validator(
        "llm_throttle_seconds",
        "gemini_retry_max_delay_seconds",
        "mcp_probe_timeout_seconds",
        "mcp_tool_timeout_seconds",
        mode="after",
    )
    @classmethod
    def _non_negative_float(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must be greater than or equal to 0")
        return value

    @field_validator("live_frame_fps", "recording_fps")
    @classmethod
    def _positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be greater than 0")
        return value

    @model_validator(mode="after")
    def _derive_and_validate(self) -> "Settings":
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        self.database_url = self.database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
        if not self.database_url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            raise ValueError("DATABASE_URL must be an async SQLAlchemy URL, for example postgresql+asyncpg://...")

        if self.max_run_ticks < self.default_run_ticks:
            raise ValueError("MAX_RUN_TICKS must be greater than or equal to DEFAULT_RUN_TICKS")

        if self.debug or self.app_env.lower() in {"dev", "development", "local"}:
            self.cors_origins = list(dict.fromkeys([*self.cors_origins, "http://localhost:3000", "http://127.0.0.1:3000"]))

        self.storage_dir = self._resolve_path(self.storage_dir)
        self.wad_storage_dir = self._resolve_path(self.wad_storage_dir or self.storage_dir / "wads")
        self.report_storage_dir = self._resolve_path(self.report_storage_dir or self.storage_dir / "reports")
        self.recording_storage_dir = self._resolve_path(
            self.recording_storage_dir or self.storage_dir / "recordings"
        )
        self.screenshot_storage_dir = self._resolve_path(
            self.screenshot_storage_dir or self.storage_dir / "screenshots"
        )
        self.analysis_storage_dir = self._resolve_path(self.analysis_storage_dir or self.storage_dir / "analysis")

        for path in (
            self.storage_dir,
            self.wad_storage_dir,
            self.report_storage_dir,
            self.recording_storage_dir,
            self.screenshot_storage_dir,
            self.analysis_storage_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
            if not os.access(path, os.W_OK):
                raise ValueError(f"Storage path is not writable: {path}")
        return self

    @staticmethod
    def _resolve_path(value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
