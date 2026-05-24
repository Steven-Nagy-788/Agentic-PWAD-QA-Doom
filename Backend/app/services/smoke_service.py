from __future__ import annotations

import time
from typing import Any

from app.core.config import get_settings
from app.services.gemini_service import GeminiService
from app.services.mcp_client_service import McpDoomClient, probe_mcp_sse_url


class SmokeService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_smoke(self) -> dict[str, Any]:
        stages: list[dict[str, Any]] = []
        mcp_client: McpDoomClient | None = None

        try:
            mcp_stage = await self._stage_check_mcp()
            stages.append(mcp_stage)
            gemini_stage = await self._stage_check_gemini_key()
            stages.append(gemini_stage)

            if mcp_stage["pass"]:
                stage3 = await self._stage_start_game()
                stages.append(stage3)
                mcp_client = stage3.get("_mcp_client")
            else:
                stages.append(self._skip_stage("Start game (MCP via Doom)", "Skipped: MCP not reachable"))

            if mcp_client is not None:
                stages.append(await self._stage_get_state(mcp_client))
            else:
                stages.append(self._skip_stage("Get game state", "Skipped: game not started"))
            if gemini_stage["pass"]:
                stages.append(await self._stage_test_gemini())
            else:
                stages.append(self._skip_stage("Test Gemini API", "Skipped: GEMINI_API_KEY is not set"))
        finally:
            stages.append(await self._stage_cleanup(mcp_client))

        for s in stages:
            s.pop("_mcp_client", None)

        overall = "pass" if all(s["pass"] for s in stages) else "fail"
        return {"overall": overall, "stages": stages}

    async def _stage_check_mcp(self) -> dict[str, Any]:
        label = "MCP SSE connectivity"
        start = time.monotonic()
        try:
            result = await probe_mcp_sse_url()
            reachable = result.get("reachable", False)
            if not reachable:
                return _fail(label, start, f"MCP not reachable: {result.get('error', 'unknown error')}")
            return _pass(label, start, {"latency_ms": result.get("latency_ms"), "status_code": result.get("status_code")})
        except Exception as exc:
            return _fail(label, start, str(exc))

    async def _stage_check_gemini_key(self) -> dict[str, Any]:
        label = "Gemini API key configured"
        start = time.monotonic()
        if not self.settings.gemini_api_key:
            return _fail(label, start, "GEMINI_API_KEY is not set")
        return _pass(label, start, {"model": self.settings.llm_model})

    async def _stage_start_game(self) -> dict[str, Any]:
        label = "Start game (Freedoom MAP01 via MCP)"
        start = time.monotonic()
        client = McpDoomClient()
        try:
            await client.__aenter__()
            result = await client.start_game(
                wad=self.settings.iwad_used,
                scenario_wad=None,
                map_name="MAP01",
                difficulty=3,
                episode_timeout=100,
                async_player=False,
            )
            detail = {"game_started": True}
            if hasattr(result, "content"):
                detail["response"] = str(result.content)[:200]
            return {**_pass(label, start, detail), "_mcp_client": client}
        except Exception as exc:
            await client.__aexit__(type(exc), exc, exc.__traceback__)
            return {**_fail(label, start, str(exc)), "_mcp_client": None}

    async def _stage_get_state(self, client: McpDoomClient) -> dict[str, Any]:
        label = "Get game state via MCP"
        start = time.monotonic()
        try:
            state, screenshot = await client.get_state()
            has_screenshot = screenshot is not None
            player = state.get("player", {}) if isinstance(state, dict) else {}
            return _pass(label, start, {
                "has_screenshot": has_screenshot,
                "player_health": player.get("health"),
                "player_ammo": player.get("ammo"),
            })
        except Exception as exc:
            return _fail(label, start, str(exc))

    async def _stage_test_gemini(self) -> dict[str, Any]:
        label = "Gemini API minimal prompt"
        start = time.monotonic()
        try:
            service = GeminiService()
            result = await service.probe_model()
            return _pass(label, start, {"model": result.get("model"), "response_preview": result.get("response", "")[:100]})
        except Exception as exc:
            return _fail(label, start, str(exc))

    async def _stage_cleanup(self, client: McpDoomClient | None) -> dict[str, Any]:
        label = "Cleanup (stop game)"
        start = time.monotonic()
        if client is None:
            return _pass(label, start, {"note": "no game to stop"})
        try:
            await client.stop_game()
            await client.__aexit__(None, None, None)
            return _pass(label, start, {"game_stopped": True})
        except Exception as exc:
            return _fail(label, start, str(exc))

    @staticmethod
    def _skip_stage(label: str, reason: str) -> dict[str, Any]:
        return {
            "label": label,
            "pass": True,
            "duration_ms": 0,
            "detail": {"skipped": reason},
        }


def _pass(label: str, start: float, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "pass": True,
        "duration_ms": _elapsed_ms(start),
        "detail": detail or {},
    }


def _fail(label: str, start: float, error: str) -> dict[str, Any]:
    return {
        "label": label,
        "pass": False,
        "duration_ms": _elapsed_ms(start),
        "error": error,
    }


def _elapsed_ms(start: float) -> int:
    return int(round((time.monotonic() - start) * 1000))
