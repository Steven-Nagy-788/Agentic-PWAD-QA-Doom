"""Tests for app.core.config Settings validators and derived fields."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings, get_settings


def _make_settings(**env_overrides) -> Settings:
    """Create a Settings instance with clean env, avoiding lru_cache issues."""
    clean_env = {
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
        "STORAGE_DIR": str(Path(os.environ.get("TMPDIR", "/tmp")) / "doom_qa_test_storage"),
    }
    clean_env.update(env_overrides)
    with patch.dict(os.environ, clean_env, clear=True):
        get_settings.cache_clear()
        return Settings()


def test_settings_defaults():
    s = _make_settings()
    assert s.app_name == "Doom Agentic Testing Backend"
    assert s.postgres_host in ("127.0.0.1", "localhost")
    assert s.postgres_port == 5432
    assert s.guard_enabled is True
    assert s.guard_consecutive_get_state_threshold == 2
    assert s.guard_position_stuck_threshold == 2
    assert s.guard_diversity_threshold == 3


def test_debug_parser_accepts_true_string():
    assert Settings._parse_debug("true") is True
    assert Settings._parse_debug("1") is True
    assert Settings._parse_debug("yes") is True
    assert Settings._parse_debug("on") is True


def test_debug_parser_rejects_false_string():
    assert Settings._parse_debug("false") is False
    assert Settings._parse_debug("0") is False
    assert Settings._parse_debug("no") is False


def test_debug_parser_handles_none():
    assert Settings._parse_debug(None) is False


def test_debug_parser_handles_bool_passthrough():
    assert Settings._parse_debug(True) is True
    assert Settings._parse_debug(False) is False


def test_cors_origins_comma_separated_string():
    s = _make_settings(CORS_ORIGINS="http://a.com, http://b.com")
    assert "http://a.com" in s.cors_origins
    assert "http://b.com" in s.cors_origins


def test_cors_origins_empty_string_returns_empty_list():
    s = _make_settings(CORS_ORIGINS="", APP_ENV="production", DEBUG="false")
    assert s.cors_origins == []


def test_cors_origins_list_passthrough():
    s = _make_settings(APP_ENV="production", DEBUG="false")
    s2 = Settings(cors_origins=["http://x.com"], database_url=s.database_url, app_env="production", debug=False)
    assert s2.cors_origins == ["http://x.com"]


def test_positive_int_validator_rejects_zero():
    with pytest.raises(ValueError, match="greater than 0"):
        _make_settings(MAX_WAD_UPLOAD_BYTES="0")


def test_positive_int_validator_rejects_negative():
    with pytest.raises(ValueError, match="greater than 0"):
        _make_settings(NO_PROGRESS_DECISION_ABORT_THRESHOLD="-5")


def test_non_negative_int_validator_allows_zero():
    s = _make_settings(GEMINI_RATE_LIMIT_CALLS_PER_MINUTE="0")
    assert s.gemini_rate_limit_calls_per_minute == 0


def test_non_negative_int_validator_rejects_negative():
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        _make_settings(GEMINI_RATE_LIMIT_CALLS_PER_MINUTE="-1")


def test_non_negative_float_validator_rejects_negative():
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        _make_settings(LLM_THROTTLE_SECONDS="-1.5")


def test_positive_float_validator_rejects_zero():
    with pytest.raises(ValueError, match="greater than 0"):
        _make_settings(LIVE_FRAME_FPS="0")


def test_model_validator_derives_database_url():
    s = _make_settings(
        POSTGRES_HOST="db.example.com",
        POSTGRES_PORT="5433",
        POSTGRES_DB="mydb",
        POSTGRES_USER="myuser",
        POSTGRES_PASSWORD="mypass",
        DATABASE_URL="",
    )
    assert "db.example.com" in s.database_url
    assert "5433" in s.database_url
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_model_validator_rejects_non_async_database_url():
    with pytest.raises(ValueError, match="async SQLAlchemy URL"):
        _make_settings(DATABASE_URL="mysql://localhost/mydb")


def test_model_validator_rejects_max_lt_default_ticks():
    with pytest.raises(ValueError, match="MAX_RUN_TICKS must be greater"):
        _make_settings(MAX_RUN_TICKS="100", DEFAULT_RUN_TICKS="500")


def test_storage_dirs_created(tmp_path):
    storage = tmp_path / "storage"
    s = _make_settings(STORAGE_DIR=str(storage))
    assert s.storage_dir.is_dir()
    assert s.wad_storage_dir.is_dir()
    assert s.report_storage_dir.is_dir()
    assert s.recording_storage_dir.is_dir()
    assert s.screenshot_storage_dir.is_dir()
    assert s.analysis_storage_dir.is_dir()


def test_resolve_path_absolute():
    result = Settings._resolve_path("/absolute/path")
    assert result == Path("/absolute/path")


def test_resolve_path_relative_resolves_against_base():
    from app.core.config import BASE_DIR
    result = Settings._resolve_path("relative/path")
    assert result == BASE_DIR / "relative/path"
