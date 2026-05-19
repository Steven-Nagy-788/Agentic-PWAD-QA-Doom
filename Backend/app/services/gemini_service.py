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
DIRECTOR_TOOLS = {"get_situation_report", "set_objective", "set_strategy"}


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
            return self._fallback_decision(llm_input, "Gemini API key is not configured; using deterministic fallback.")
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
            return self._fallback_decision(llm_input, "Model response failed or was rate limited; using deterministic fallback.")

    async def decide_director(self, system_prompt: str, llm_input: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            return self._fallback_director_decision(
                llm_input,
                "Gemini API key is not configured; using deterministic director fallback.",
            )
        try:
            response = await self._call_gemini(system_prompt, llm_input)
            return self.parse_director_decision(response)
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
                    return self.parse_director_decision(response)
                except Exception:
                    pass
            return self._fallback_director_decision(
                llm_input,
                "Model response failed or was rate limited; using deterministic director fallback.",
            )

    async def _call_gemini(self, system_prompt: str, llm_input: dict) -> str:
        def generate() -> str:
            from google import genai

            client = genai.Client(api_key=self.settings.gemini_api_key)
            contents = f"{system_prompt}\n\nCURRENT STATE JSON:\n{json.dumps(llm_input, default=str)}"
            response = client.models.generate_content(model=self.settings.llm_model, contents=contents)
            return response.text or ""

        return await asyncio.to_thread(generate)

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

    def parse_director_decision(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end >= start:
            cleaned = cleaned[start : end + 1]
        data = json.loads(cleaned)
        tool = data.get("mcp_tool") or "get_situation_report"
        if tool not in DIRECTOR_TOOLS:
            tool = "get_situation_report"
        params = data.get("mcp_params")
        if not isinstance(params, dict):
            params = {}
        return {
            "reasoning_summary": str(data.get("reasoning_summary") or "Director requested the current situation."),
            "mcp_tool": tool,
            "mcp_params": params,
            "observed_issue": data.get("observed_issue"),
        }

    def _fallback_decision(self, llm_input: dict[str, Any], reason: str) -> dict[str, Any]:
        objects = [obj for obj in llm_input.get("objects", []) if isinstance(obj, dict)]
        visible_monsters = [
            obj
            for obj in objects
            if obj.get("type") == "monster" and obj.get("is_visible") and obj.get("id") is not None
        ]
        if visible_monsters:
            target = min(visible_monsters, key=lambda obj: float(obj.get("distance") or 999999))
            tool = "strafe_and_shoot" if target.get("attack_type") == "hitscan" or float(target.get("distance") or 0) < 350 else "aim_and_shoot"
            return {
                "reasoning_summary": f"{reason} Visible {target.get('name', 'monster')} selected for combat.",
                "mcp_tool": tool,
                "mcp_params": {"object_id": target["id"]},
                "observed_issue": None,
            }

        visible_pickups = [
            obj
            for obj in objects
            if obj.get("type") in {"item", "ammo", "weapon", "key"} and obj.get("is_visible") and obj.get("id") is not None
        ]
        if visible_pickups:
            target = min(visible_pickups, key=lambda obj: float(obj.get("distance") or 999999))
            return {
                "reasoning_summary": f"{reason} Visible {target.get('name', 'pickup')} selected for collection.",
                "mcp_tool": "move_to",
                "mcp_params": {"object_id": target["id"], "stop_on_enemy": True},
                "observed_issue": None,
            }

        return {
            "reasoning_summary": f"{reason} No visible combat or pickup target is available, so a short bounded exploration step starts.",
            "mcp_tool": "explore",
            "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": True},
            "observed_issue": None,
        }

    def _fallback_director_decision(self, llm_input: dict[str, Any], reason: str) -> dict[str, Any]:
        situation = llm_input.get("situation") if isinstance(llm_input.get("situation"), dict) else {}
        variables = situation.get("game_variables") if isinstance(situation.get("game_variables"), dict) else {}
        objects = [obj for obj in situation.get("objects", []) if isinstance(obj, dict)]
        objectives = situation.get("objectives") if isinstance(situation.get("objectives"), list) else []
        executor_state = str(situation.get("executor_state") or "unknown")
        health = _number(variables.get("HEALTH") or variables.get("health"), 100)
        selected_ammo = _number(variables.get("SELECTED_WEAPON_AMMO") or variables.get("selected_weapon_ammo"), 0)
        visible_pickups = [
            obj
            for obj in objects
            if obj.get("is_visible")
            and obj.get("id") is not None
            and obj.get("type") in {"item", "ammo", "weapon", "key"}
        ]
        visible_monsters = [
            obj
            for obj in objects
            if obj.get("is_visible") and obj.get("id") is not None and obj.get("type") == "monster"
        ]
        progress = situation.get("executor_progress") if isinstance(situation.get("executor_progress"), dict) else {}
        if int(progress.get("stuck_recovery_count") or 0) > int(llm_input.get("last_stuck_recovery_count") or 0):
            return {
                "reasoning_summary": f"{reason} Executor reported stuck recovery, so replacing the objective with exploration.",
                "mcp_tool": "set_objective",
                "mcp_params": {
                    "objective_type": "explore",
                    "priority": 80,
                    "timeout_tics": 280,
                    "replace": True,
                },
                "event_type_override": "stuck",
                "observed_issue": None,
            }
        if health <= 25:
            return {
                "reasoning_summary": f"{reason} Health is low, so directing a retreat before continuing coverage.",
                "mcp_tool": "set_objective",
                "mcp_params": {"objective_type": "retreat", "priority": 100, "timeout_tics": 140, "replace": True},
                "observed_issue": None,
            }
        if selected_ammo <= 2 and any(obj.get("type") in {"ammo", "weapon"} for obj in visible_pickups):
            return {
                "reasoning_summary": f"{reason} Ammo is low and a useful pickup is visible, so directing collection.",
                "mcp_tool": "set_objective",
                "mcp_params": {"objective_type": "collect", "priority": 95, "timeout_tics": 220, "replace": True},
                "observed_issue": None,
            }
        if visible_monsters:
            return {
                "reasoning_summary": f"{reason} Visible monsters are present; tuning aggression while executor handles combat.",
                "mcp_tool": "set_strategy",
                "mcp_params": {"aggression": 0.85, "engage_range": 1400, "prefer_cover": True},
                "observed_issue": None,
            }
        if not objectives or executor_state in {"idle", "unknown"}:
            return {
                "reasoning_summary": f"{reason} No active objective is driving coverage, so directing exploration.",
                "mcp_tool": "set_objective",
                "mcp_params": {"objective_type": "explore", "priority": 40, "timeout_tics": 350, "replace": False},
                "observed_issue": None,
            }
        return {
            "reasoning_summary": f"{reason} Existing objective is still active; continuing to monitor.",
            "mcp_tool": "get_situation_report",
            "mcp_params": {},
            "observed_issue": None,
        }


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
