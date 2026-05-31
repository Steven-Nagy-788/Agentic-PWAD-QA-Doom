from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
import platform
import subprocess
import sys
from typing import Any

from app.core.config import get_settings


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not reported"


def _ffmpeg_version() -> str:
    settings = get_settings()
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(0.1, settings.ffmpeg_timeout_seconds),
        )
    except Exception:
        return "not reported"
    first_line = (result.stdout or result.stderr or "").splitlines()
    return first_line[0] if first_line else "not reported"


async def collect_environment_metadata(
    mcp_metadata: dict[str, Any] | None,
    *,
    model: str,
    iwad: str,
    difficulty: int,
    max_ticks: int,
) -> dict[str, Any]:
    mcp = mcp_metadata or {}
    return {
        "hardware": {
            "cpu": platform.processor() or "not reported",
            "ram_gb": "not reported",
            "os": platform.platform() or "not reported",
        },
        "software": {
            "backend_python": platform.python_version(),
            "fastapi": _package_version("fastapi"),
            "weasyprint": _package_version("weasyprint"),
            "ffmpeg": await asyncio.to_thread(_ffmpeg_version),
            "mcp_python": mcp.get("python", "not reported"),
            "fastmcp": mcp.get("fastmcp", "not reported"),
            "vizdoom": mcp.get("vizdoom", "not reported"),
            "doom_mcp": mcp.get("doom_mcp", "not reported"),
            "platform_python_implementation": sys.implementation.name,
        },
        "run": {
            "llm_model": model,
            "iwad": iwad,
            "difficulty": difficulty,
            "max_ticks": max_ticks,
        },
    }
