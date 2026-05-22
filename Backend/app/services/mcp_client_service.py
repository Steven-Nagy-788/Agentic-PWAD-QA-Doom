from __future__ import annotations

import base64
import asyncio
import contextlib
import json
import time
import warnings
from typing import Any

import httpx

from app.core.config import get_settings


MCP_STARTUP_RETRY_DELAYS = (1.0, 2.0, 4.0)


def _suppress_fastmcp_authlib_warning() -> None:
    try:
        from authlib.deprecate import AuthlibDeprecationWarning
    except ImportError:
        warning_category = Warning
    else:
        warning_category = AuthlibDeprecationWarning
    warnings.filterwarnings("ignore", category=warning_category)


class McpDoomClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any = None

    async def __aenter__(self) -> "McpDoomClient":
        try:
            _suppress_fastmcp_authlib_warning()
            from fastmcp import Client
        except ImportError as exc:
            raise RuntimeError("fastmcp is not installed in the backend environment") from exc
        last_error: Exception | None = None
        for attempt in range(len(MCP_STARTUP_RETRY_DELAYS) + 1):
            self._client = Client(self.settings.mcp_doom_sse_url)
            try:
                await self._client.__aenter__()
                return self
            except Exception as exc:
                last_error = exc
                with contextlib.suppress(Exception):
                    await self._client.__aexit__(type(exc), exc, exc.__traceback__)
                self._client = None
                if attempt < len(MCP_STARTUP_RETRY_DELAYS):
                    await asyncio.sleep(MCP_STARTUP_RETRY_DELAYS[attempt])
        raise McpStartupError("MCP SSE connection failed after startup retries") from last_error

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)

    async def call_tool(self, name: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            raise RuntimeError("MCP client is not connected")
        timeout = max(0.1, self.settings.mcp_tool_timeout_seconds)
        try:
            return await asyncio.wait_for(self._client.call_tool(name, params or {}), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise McpToolTimeoutError(f"MCP tool {name} timed out after {timeout:g}s") from exc

    async def start_game(
        self,
        wad: str,
        scenario_wad: str,
        map_name: str,
        difficulty: int,
        episode_timeout: int,
        async_player: bool = False,
        ticrate: int | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "wad": wad,
            "scenario_wad": scenario_wad,
            "map_name": map_name,
            "difficulty": difficulty,
            "episode_timeout": episode_timeout,
            "screen_resolution": "RES_640X480",
            "render_hud": False,
            "window_visible": False,
            "async_player": async_player,
        }
        if ticrate is not None:
            params["ticrate"] = ticrate
        last_error: Exception | None = None
        for attempt in range(len(MCP_STARTUP_RETRY_DELAYS) + 1):
            try:
                return await self.call_tool("start_game", params)
            except Exception as exc:
                last_error = exc
                if attempt < len(MCP_STARTUP_RETRY_DELAYS):
                    await asyncio.sleep(MCP_STARTUP_RETRY_DELAYS[attempt])
        raise McpStartupError("MCP start_game failed after startup retries") from last_error

    async def get_state(self) -> tuple[dict[str, Any], bytes | None]:
        result = await self.call_tool("get_state", {"include_sectors": False, "include_depth": True})
        return normalize_mcp_state(result)

    async def get_situation_report(self) -> tuple[dict[str, Any], bytes | None]:
        result = await self.call_tool("get_situation_report", {})
        return normalize_mcp_state(result)

    async def set_objective(
        self,
        objective_type: str,
        params: dict[str, Any] | None = None,
        priority: int = 0,
        timeout_tics: int = 0,
        replace: bool = False,
    ) -> Any:
        return await self.call_tool(
            "set_objective",
            {
                "objective_type": objective_type,
                "params": params or {},
                "priority": priority,
                "timeout_tics": timeout_tics,
                "replace": replace,
            },
        )

    async def set_strategy(self, **kwargs: Any) -> Any:
        return await self.call_tool("set_strategy", {key: value for key, value in kwargs.items() if value is not None})

    async def stop_game(self) -> None:
        with contextlib.suppress(Exception):
            await self.call_tool("stop_game", {})


class McpToolTimeoutError(RuntimeError):
    pass


class McpStartupError(RuntimeError):
    pass


async def probe_mcp_sse_url(url: str | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
    settings = get_settings()
    target_url = url or settings.mcp_doom_sse_url
    timeout = timeout_seconds if timeout_seconds is not None else settings.mcp_probe_timeout_seconds
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=max(0.1, timeout), follow_redirects=True) as client:
            async with client.stream("GET", target_url, headers={"Accept": "text/event-stream"}) as response:
                status_code = response.status_code
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "reachable": 200 <= status_code < 400,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "url": target_url,
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "reachable": False,
            "latency_ms": latency_ms,
            "url": target_url,
            "error": str(exc),
        }


def normalize_mcp_state(result: Any) -> tuple[dict[str, Any], bytes | None]:
    screenshot: bytes | None = None
    state: dict[str, Any] = {}
    items = result if isinstance(result, list) else [result]
    for item in items:
        content = getattr(item, "content", None)
        if content:
            nested_state, nested_screenshot = normalize_mcp_state(content)
            state = nested_state or state
            screenshot = nested_screenshot or screenshot
            continue
        data = getattr(item, "data", None)
        mime_type = getattr(item, "mime_type", "") or getattr(item, "mimeType", "") or getattr(item, "format", "")
        if data is not None and ("image" in mime_type or mime_type in {"png", "jpeg", "jpg"}):
            if isinstance(data, bytes):
                screenshot = data
            elif isinstance(data, str):
                screenshot = base64.b64decode(data)
        elif isinstance(item, dict):
            state = item
        elif hasattr(item, "structured_content") and isinstance(item.structured_content, dict):
            state = item.structured_content
        elif hasattr(item, "text"):
            text = item.text
            try:
                parsed = json.loads(text)
                nested_state, nested_screenshot = normalize_mcp_state(parsed)
                state = nested_state or state
                screenshot = nested_screenshot or screenshot
            except Exception:
                pass
    return state, screenshot
