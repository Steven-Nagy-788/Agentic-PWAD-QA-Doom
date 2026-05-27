from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import Callable
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
    "select_weapon",
}
DIRECTOR_TOOLS = {"get_situation_report", "set_objective", "set_strategy"}

logger = logging.getLogger(__name__)
_gemini_sem = asyncio.Semaphore(max(1, get_settings().gemini_max_concurrency))
_api_call_timestamps: list[float] = []
class GeminiService:
    def __init__(
        self,
        *,
        llm_model: str | None = None,
        rate_limit_calls_per_minute: int | None = None,
    ) -> None:
        self.settings = get_settings()
        self.llm_model = llm_model or self.settings.llm_model
        self.rate_limit_calls_per_minute = (
            self.settings.gemini_rate_limit_calls_per_minute
            if rate_limit_calls_per_minute is None
            else rate_limit_calls_per_minute
        )

    async def detect_visual_defects(
        self,
        screenshots: list[tuple[str, bytes]],
    ) -> list[dict[str, object]]:
        if not screenshots:
            return []
        results: list[dict[str, object]] = []
        batch_size = 3
        for i in range(0, len(screenshots), batch_size):
            batch = screenshots[i : i + batch_size]
            batch_results = await self._analyze_screenshot_batch(batch)
            results.extend(batch_results)
        return results

    async def _analyze_screenshot_batch(
        self,
        batch: list[tuple[str, bytes]],
    ) -> list[dict[str, object]]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc

        vision_prompt = (
            "You are a Doom map QA visual inspector. Analyze each screenshot and report any "
            "visible defects. Look for:\n"
          - "HOM (Hall of Mirrors) effects — missing textures causing visual glitches\n"
          - "Medusa effects — distorted/stretched textures\n"
          - "Tutti-frutti effects — colored pixel rows on walls\n"
          - "Misaligned textures — offsets on doors/walls that look wrong\n"
          - "Visible stuck monsters — monsters clipping into walls or each other\n"
          - "Zero-height or invisible sectors causing floating objects\n"
          - "HUD readout issues — negative health/armor, wrong weapon shown\n"
          - "Overlapping or z-fighting geometry\n"
          - "Projected texture seams or skybox issues\n\n"
            "For each screenshot that contains a defect, return one JSON object:\n"
            "{\n"
            '  "screenshot_index": <0-based index in this batch>,\n'
            '  "defect_type": "visual_texture_misalignment | visual_hom | visual_stuck_monster | visual_hud_anomaly | visual_geometry_glitch",\n'
            '  "title": "<concise title>",\n'
            '  "description": "<specific description of what is visible>",\n'
            '  "severity": <1|2|3>,\n'
            '  "recommendation": "<what to fix>"\n'
            "}\n"
            "Return a JSON array of defects. If no defects visible, return [].\n"
            "Do not report normal gameplay elements (blood, gibs, weapon sprites, normal HUD)."
        )

        parts = [types.Part.from_text(text=vision_prompt)]
        for _, png_bytes in batch:
            parts.append(types.Part.from_bytes(data=png_bytes, mime_type="image/png"))

        await _throttle_local_rate(self.rate_limit_calls_per_minute)
        async with _gemini_sem:
            client = genai.Client(api_key=self.settings.gemini_api_key)
            async_client = getattr(client, "aio", None)
            if async_client is not None and hasattr(async_client, "models"):
                response = await async_client.models.generate_content(
                    model=self.llm_model,
                    contents=types.Content(parts=parts, role="user"),
                )
            else:
                response = await asyncio.to_thread(
                    lambda: client.models.generate_content(
                        model=self.llm_model,
                        contents=types.Content(parts=parts, role="user"),
                    )
                )
        _record_api_call()
        text = response.text or "[]"
        parsed = self._parse_vision_response(text)
        for item in parsed:
            idx = item.get("screenshot_index", 0)
            if 0 <= idx < len(batch):
                item["screenshot_path"] = batch[idx][0]
        return parsed

    def _parse_vision_response(self, text: str) -> list[dict[str, object]]:
        try:
            data = self._parse_json_response(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                inner = data.get("defects") or data.get("results")
                if isinstance(inner, list):
                    return inner
                return [data]
        except ValueError:
            pass
        return []

    async def probe_model(self) -> dict[str, str]:
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        response = await self._generate_content("Return ok.", {})
        return {"model": self.llm_model, "response": response.text or ""}

    async def decide(self, system_prompt: str, llm_input: dict[str, Any], screenshot_png: bytes | None = None) -> tuple[dict[str, Any], dict[str, int]]:
        if not self.settings.gemini_api_key:
            return self._fallback_decision(llm_input, "Gemini API key is not configured; using deterministic fallback."), {}
        return await self._call_with_retry(
            system_prompt,
            llm_input,
            self.parse_decision,
            lambda: (
                self._fallback_decision(
                    llm_input,
                    "Model response failed or was rate limited; using deterministic fallback.",
                ),
                {},
            ),
            screenshot_png=screenshot_png,
        )

    async def decide_director(self, system_prompt: str, llm_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
        if not self.settings.gemini_api_key:
            return self._fallback_director_decision(
                llm_input,
                "Gemini API key is not configured; using deterministic director fallback.",
            ), {}
        return await self._call_with_retry(
            system_prompt,
            llm_input,
            self.parse_director_decision,
            lambda: (
                self._fallback_director_decision(
                    llm_input,
                    "Model response failed or was rate limited; using deterministic director fallback.",
                ),
                {},
            ),
        )

    async def _call_with_retry(
        self,
        system_prompt: str,
        llm_input: dict[str, Any],
        parser: Callable[[str], dict[str, Any]],
        fallback: Callable[[], tuple[dict[str, Any], dict[str, int]]],
        screenshot_png: bytes | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        last_error = ""
        await _throttle_local_rate(self.rate_limit_calls_per_minute)
        for attempt in range(3):
            try:
                response, token_usage = await self._call_gemini(system_prompt, llm_input, screenshot_png=screenshot_png)
                _record_api_call()
                return parser(response), token_usage
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Gemini API call attempt %d/3 failed: %s", attempt + 1, last_error)
                if _is_rate_limit(exc) and attempt < 2:
                    wait = min(_retry_delay_seconds(exc), 60.0)
                    logger.info("Rate limited, retrying in %.1fs (attempt %d/3)", wait, attempt + 2)
                    await asyncio.sleep(wait)
                    continue
                if attempt < 2:
                    logger.info("Non-rate-limit error, retrying in 5s (attempt %d/3)", attempt + 2)
                    await asyncio.sleep(5.0)
                    continue
        logger.warning("All 3 Gemini API attempts failed, using deterministic fallback")
        fallback_result, fallback_tokens = fallback()
        fallback_result["reasoning_summary"] = (
            f"Gemini API failed after 3 attempts: {last_error}. "
            f"{fallback_result.get('reasoning_summary', 'Falling back to deterministic.')}"
        )
        return fallback_result, fallback_tokens

    async def _call_gemini(self, system_prompt: str, llm_input: dict, screenshot_png: bytes | None = None) -> tuple[str, dict[str, int]]:
        response = await self._generate_content(system_prompt, llm_input, screenshot_png=screenshot_png)
        token_usage: dict[str, int] = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_usage = {
                "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0) or 0,
                "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0) or 0,
            }
        return response.text or "", token_usage

    async def _generate_content(self, system_prompt: str, llm_input: dict, screenshot_png: bytes | None = None) -> Any:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc

        text_part = f"{system_prompt}\n\nCURRENT STATE JSON:\n{json.dumps(llm_input, default=str)}"

        async with _gemini_sem:
            client = genai.Client(api_key=self.settings.gemini_api_key)
            async_client = getattr(client, "aio", None)

            if screenshot_png is not None and async_client is not None and hasattr(async_client, "models"):
                parts = [
                    types.Part.from_text(text=text_part),
                    types.Part.from_bytes(data=screenshot_png, mime_type="image/png"),
                ]
                return await async_client.models.generate_content(
                    model=self.llm_model,
                    contents=types.Content(parts=parts, role="user"),
                )

            if async_client is not None and hasattr(async_client, "models"):
                return await async_client.models.generate_content(model=self.llm_model, contents=text_part)

            def generate() -> Any:
                if screenshot_png is not None:
                    parts = [
                        types.Part.from_text(text=text_part),
                        types.Part.from_bytes(data=screenshot_png, mime_type="image/png"),
                    ]
                    return client.models.generate_content(
                        model=self.llm_model,
                        contents=types.Content(parts=parts, role="user"),
                    )
                return client.models.generate_content(model=self.llm_model, contents=text_part)

            return await asyncio.to_thread(generate)

    @staticmethod
    def _extract_json_block(text: str) -> str | None:
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            return _extract_json(match.group(1))
        return None

    @staticmethod
    def _extract_json_braces(text: str) -> str | None:
        cleaned = text.strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end >= start:
            return cleaned[start : end + 1]
        return None

    @staticmethod
    def _extract_json_balanced(text: str) -> str | None:
        candidates: list[str] = []
        i = 0
        while True:
            start = text.find("{", i)
            if start == -1:
                break
            depth = 0
            pos = start
            while pos < len(text):
                ch = text[pos]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:pos+1])
                        i = pos + 1
                        break
                pos += 1
            else:
                break
        if not candidates:
            return None
        return max(candidates, key=len)

    @staticmethod
    def _decode_json(text: str) -> dict[str, Any] | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        strategies = [
            self._extract_json_block,
            self._extract_json_balanced,
            self._extract_json_braces,
        ]
        for strategy in strategies:
            extracted = strategy(text)
            if extracted is not None:
                data = self._decode_json(extracted)
                if data is not None:
                    return data
        raise ValueError("Could not parse LLM response as JSON")

    def parse_decision(self, text: str) -> dict[str, Any]:
        try:
            data = self._parse_json_response(text)
        except ValueError:
            data = {}
        tool = data.get("mcp_tool") or "explore"
        if tool not in ALLOWED_TOOLS:
            tool = "explore"
        params = data.get("mcp_params")
        if not isinstance(params, dict):
            params = {}
        reasoning = data.get("reasoning_summary")
        if not isinstance(reasoning, str):
            reasoning = "No reasoning summary returned."
        observed_issue = data.get("observed_issue")
        if observed_issue is not None and not isinstance(observed_issue, (str, dict)):
            observed_issue = None
        return {
            "reasoning_summary": reasoning,
            "mcp_tool": tool,
            "mcp_params": params,
            "hypotheses": _normalize_hypotheses(data.get("hypotheses")),
            "observed_issue": observed_issue,
        }

    def parse_director_decision(self, text: str) -> dict[str, Any]:
        try:
            data = self._parse_json_response(text)
        except ValueError:
            data = {}
        tool = data.get("mcp_tool") or "get_situation_report"
        if tool not in DIRECTOR_TOOLS:
            tool = "get_situation_report"
        params = data.get("mcp_params")
        if not isinstance(params, dict):
            params = {}
        reasoning = data.get("reasoning_summary")
        if not isinstance(reasoning, str):
            reasoning = "Director requested the current situation."
        observed_issue = data.get("observed_issue")
        if observed_issue is not None and not isinstance(observed_issue, (str, dict)):
            observed_issue = None
        return {
            "reasoning_summary": reasoning,
            "mcp_tool": tool,
            "mcp_params": params,
            "hypotheses": _normalize_hypotheses(data.get("hypotheses")),
            "observed_issue": observed_issue,
        }

    def _fallback_decision(self, llm_input: dict[str, Any], reason: str) -> dict[str, Any]:
        objects = [obj for obj in llm_input.get("objects", []) if isinstance(obj, dict)]
        lockstep_state = llm_input.get("lockstep_state") if isinstance(llm_input.get("lockstep_state"), dict) else {}
        navigation_info = llm_input.get("navigation_info") if isinstance(llm_input.get("navigation_info"), dict) else {}
        completed_object_ids = {str(key) for key in (lockstep_state.get("completed_object_ids") or {})}
        failed_object_ids = {
            str(key)
            for key, value in (lockstep_state.get("failed_object_ids") or {}).items()
            if _number(value, 0) >= 2
        }
        invisible_target_failures = {str(key) for key in (lockstep_state.get("invisible_target_failures") or {})}
        weapon_state = llm_input.get("weapon_state") if isinstance(llm_input.get("weapon_state"), dict) else {}
        best_weapon = weapon_state.get("best_viable_weapon")
        usable_attack_ammo = _number(weapon_state.get("usable_attack_ammo"), 0)
        selected_ammo = _number(weapon_state.get("selected_weapon_ammo"), 0)
        usable_weapons = weapon_state.get("usable_weapons") if isinstance(weapon_state.get("usable_weapons"), list) else []
        if selected_ammo <= 0 and usable_attack_ammo > 0 and best_weapon is not None:
            return {
                "reasoning_summary": f"{reason} The selected weapon is empty but weapon {best_weapon} is usable, so switching before combat.",
                "mcp_tool": "select_weapon",
                "mcp_params": {"weapon_slot": best_weapon, "max_tics": 12},
                "observed_issue": None,
            }
        visible_monsters = [
            obj
            for obj in objects
            if obj.get("type") == "monster" and obj.get("is_visible") and obj.get("id") is not None
            and str(obj.get("id")) not in invisible_target_failures
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
            and str(obj.get("id")) not in completed_object_ids
            and str(obj.get("id")) not in failed_object_ids
        ]
        if visible_pickups:
            target = min(visible_pickups, key=lambda obj: float(obj.get("distance") or 999999))
            return {
                "reasoning_summary": f"{reason} Visible {target.get('name', 'pickup')} selected for collection.",
                "mcp_tool": "move_to",
                "mcp_params": {"object_id": target["id"], "stop_on_enemy": True},
                "observed_issue": None,
            }

        if not usable_weapons:
            return {
                "reasoning_summary": f"{reason} No usable weapon is available, so looking for resources or space before reassessing.",
                "mcp_tool": "retreat",
                "mcp_params": {"tics": 28},
                "observed_issue": None,
            }

        if int(lockstep_state.get("low_value_explore_total") or 0) >= 2:
            return {
                "reasoning_summary": f"{reason} Recent exploration did not progress, so probing a nearby door/use interaction.",
                "mcp_tool": "take_action",
                "mcp_params": {"actions": {"USE": 1}, "tics": 3},
                "observed_issue": None,
            }

        unexplored_direction = navigation_info.get("unexplored_direction") if isinstance(navigation_info, dict) else None
        if unexplored_direction:
            return {
                "reasoning_summary": f"{reason} Navigation info indicates unexplored area to the {unexplored_direction}, exploring toward it.",
                "mcp_tool": "explore",
                "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": True},
                "observed_issue": None,
            }

        unvisited_quadrants = int(lockstep_state.get("unvisited_quadrants") or 0)
        if unvisited_quadrants > 0:
            return {
                "reasoning_summary": f"{reason} {unvisited_quadrants} quadrant(s) remain unexplored; turning to probe new directions.",
                "mcp_tool": "take_action",
                "mcp_params": {"actions": {"TURN_LEFT_RIGHT_DELTA": 90}, "tics": 3},
                "observed_issue": None,
            }

        return {
            "reasoning_summary": f"{reason} No targets or navigation cues available, retreating to reassess from a safer position.",
            "mcp_tool": "retreat",
            "mcp_params": {"tics": 35},
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


async def _throttle_local_rate(max_calls: int) -> None:
    global _api_call_timestamps
    if max_calls <= 0:
        return
    now = time.monotonic()
    window = 60.0
    _api_call_timestamps = [t for t in _api_call_timestamps if now - t < window]

    if len(_api_call_timestamps) >= max_calls:
        oldest = _api_call_timestamps[0]
        wait = window - (now - oldest) + 1.0
        logger.info("Local rate limiter: %d calls in last 60s, waiting %.1fs", len(_api_call_timestamps), wait)
        await asyncio.sleep(wait)


def _record_api_call() -> None:
    global _api_call_timestamps
    _api_call_timestamps.append(time.monotonic())
    _api_call_timestamps = [t for t in _api_call_timestamps if time.monotonic() - t < 60.0]


def estimate_llm_cost_usd(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    *,
    input_cost_per_million: float,
    output_cost_per_million: float,
) -> float:
    input_cost = max(0, int(prompt_tokens or 0)) * input_cost_per_million / 1_000_000
    output_cost = max(0, int(completion_tokens or 0)) * output_cost_per_million / 1_000_000
    return input_cost + output_cost


def _normalize_hypotheses(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = [item for item in value if isinstance(item, str)]
    else:
        return []
    hypotheses = []
    seen = set()
    for item in raw_items:
        text = " ".join(item.split())[:180]
        if not text or text.lower() in seen:
            continue
        hypotheses.append(text)
        seen.add(text.lower())
    return hypotheses[:8]


def _is_rate_limit(exc: Exception) -> bool:
    exc_str = str(exc)
    return "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str


def _retry_delay_seconds(exc: Exception) -> float:
    exc_str = str(exc)
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s", exc_str)
    base = float(match.group(1)) if match else 15.0
    return base + random.uniform(1, 10)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_json(text: str) -> str | None:
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        return cleaned[start : end + 1]
    return None
