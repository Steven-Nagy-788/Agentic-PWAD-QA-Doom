from __future__ import annotations

import base64
import contextlib
import json
from typing import Any

from app.core.config import get_settings


class McpDoomClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any = None

    async def __aenter__(self) -> "McpDoomClient":
        try:
            from fastmcp import Client
        except ImportError as exc:
            raise RuntimeError("fastmcp is not installed in the backend environment") from exc
        self._client = Client(self.settings.mcp_doom_sse_url)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)

    async def call_tool(self, name: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            raise RuntimeError("MCP client is not connected")
        return await self._client.call_tool(name, params or {})

    async def start_game(
        self,
        wad: str,
        scenario_wad: str,
        map_name: str,
        difficulty: int,
        episode_timeout: int,
    ) -> Any:
        return await self.call_tool(
            "start_game",
            {
                "wad": wad,
                "scenario_wad": scenario_wad,
                "map_name": map_name,
                "difficulty": difficulty,
                "episode_timeout": episode_timeout,
                "screen_resolution": "RES_320X240",
                "render_hud": False,
                "window_visible": False,
            },
        )

    async def get_state(self) -> tuple[dict[str, Any], bytes | None]:
        result = await self.call_tool("get_state", {"include_sectors": False, "include_depth": True})
        return normalize_mcp_state(result)

    async def stop_game(self) -> None:
        with contextlib.suppress(Exception):
            await self.call_tool("stop_game", {})


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
        elif hasattr(item, "text"):
            text = item.text
            try:
                parsed = json.loads(text)
                nested_state, nested_screenshot = normalize_mcp_state(parsed)
                state = nested_state or state
                screenshot = nested_screenshot or screenshot
            except Exception:
                pass
        elif hasattr(item, "structured_content") and isinstance(item.structured_content, dict):
            state = item.structured_content
    return state, screenshot
