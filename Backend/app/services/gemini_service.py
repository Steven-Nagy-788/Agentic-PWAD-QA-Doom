from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from app.core.config import get_settings


ALLOWED_TOOLS = {
    "get_state",
    "explore",
    "aim_and_shoot",
    "move_to",
    "strafe_and_shoot",
    "retreat",
    "get_threat_assessment",
    "get_navigation_info",
    "take_action",
}


class GeminiService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def probe_model(self) -> dict[str, str]:
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc
        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(model=self.settings.llm_model, contents="Return ok.")
        return {"model": self.settings.llm_model, "response": response.text or ""}

    async def decide(self, system_prompt: str, llm_input: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            return {
                "reasoning_summary": "Gemini API key is not configured; using fallback exploration action.",
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 35, "stop_on_enemy": False},
                "observed_issue": None,
            }
        try:
            response = await self._call_gemini(system_prompt, llm_input)
            return self.parse_decision(response)
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                match = re.search(r"retryDelay['\"]:\s*['\"](\d+)s", exc_str)
                wait = int(match.group(1)) if match else 15
                wait += random.uniform(1, 3)
                wait = min(wait, self.settings.gemini_retry_max_delay_seconds)
                await asyncio.sleep(wait)
                try:
                    response = await self._call_gemini(system_prompt, llm_input)
                    return self.parse_decision(response)
                except Exception:
                    pass
            return {
                "reasoning_summary": "Rate limited — fallback explore used.",
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 35, "stop_on_enemy": False},
                "observed_issue": None,
            }

    async def _call_gemini(self, system_prompt: str, llm_input: dict) -> str:
        from google import genai

        client = genai.Client(api_key=self.settings.gemini_api_key)
        contents = f"{system_prompt}\n\nCURRENT STATE JSON:\n{json.dumps(llm_input, default=str)}"
        response = client.models.generate_content(model=self.settings.llm_model, contents=contents)
        return response.text or ""

    def parse_decision(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end >= start:
            cleaned = cleaned[start : end + 1]
        data = json.loads(cleaned)
        tool = data.get("mcp_tool") or "explore"
        if tool not in ALLOWED_TOOLS:
            tool = "explore"
        params = data.get("mcp_params")
        if not isinstance(params, dict):
            params = {}
        return {
            "reasoning_summary": str(data.get("reasoning_summary") or "No reasoning summary returned."),
            "mcp_tool": tool,
            "mcp_params": params,
            "observed_issue": data.get("observed_issue"),
        }
