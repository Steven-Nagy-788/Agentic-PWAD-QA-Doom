from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from app.core.config import get_settings


LOW_VALUE_TEXTURE_DEFECT_TYPES = {"visual_texture_misalignment"}
LOW_VALUE_TEXTURE_TERMS = (
    "alignment",
    "misalign",
    "offset",
    "tiling",
    "discontinuity",
    "repeat",
    "cut-off",
    "cut off",
    "seam",
)
CRITICAL_TEXTURE_TERMS = (
    "hom",
    "hall of mirrors",
    "missing texture",
    "medusa",
    "z-fighting",
    "z fighting",
)

logger = logging.getLogger(__name__)
_gemini_sem: asyncio.Semaphore | None = None
_api_call_timestamps: list[float] = []


def _get_gemini_sem() -> asyncio.Semaphore:
    global _gemini_sem
    if _gemini_sem is None:
        _gemini_sem = asyncio.Semaphore(max(1, get_settings().gemini_max_concurrency))
    return _gemini_sem


def is_low_value_texture_defect(defect: Mapping[str, Any]) -> bool:
    defect_type = str(defect.get("defect_type") or "").strip().lower()
    title = str(defect.get("title") or "").lower()
    description = str(defect.get("description") or "").lower()
    text = f"{defect_type} {title} {description}"
    if any(term in text for term in CRITICAL_TEXTURE_TERMS):
        return False
    if defect_type in LOW_VALUE_TEXTURE_DEFECT_TYPES:
        return True
    return (
        "texture" in text or "floor" in text or "wall" in text or "pillar" in text
    ) and any(term in text for term in LOW_VALUE_TEXTURE_TERMS)


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
            "visible gameplay-affecting defects. Look for:\n"
            "- HOM (Hall of Mirrors), missing textures, Medusa, or tutti-frutti rendering failures\n"
            "- Visible stuck monsters clipping into walls or each other\n"
            "- Zero-height or invisible sectors causing floating objects or blocked movement\n"
            "- HUD readout issues such as negative health/armor or wrong weapon state\n"
            "- Overlapping or z-fighting geometry that hides gameplay-critical space\n\n"
            "Do not report cosmetic texture alignment, tiling, offset, pillar, floor, wall seam, or pattern-repeat issues.\n\n"
            "For each screenshot that contains a defect, return one JSON object:\n"
            "{\n"
            '  "screenshot_index": <0-based index in this batch>,\n'
            '  "defect_type": "visual_hom | visual_stuck_monster | visual_hud_anomaly | visual_geometry_glitch",\n'
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
        async with _get_gemini_sem():
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
        filtered: list[dict[str, object]] = []
        for item in parsed:
            if is_low_value_texture_defect(item):
                continue
            idx = item.get("screenshot_index", 0)
            if 0 <= idx < len(batch):
                item["screenshot_path"] = batch[idx][0]
            filtered.append(item)
        return filtered

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

    async def decide(
        self,
        system_prompt: str,
        llm_input: dict[str, Any],
        screenshot_png: bytes | None = None,
        map_layout_png: bytes | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        if not self.settings.gemini_api_key:
            return self._fallback_decision(
                llm_input,
                "Gemini API key is not configured; using deterministic fallback.",
            ), {}
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
            map_layout_png=map_layout_png,
        )

    async def detect_visual_defect_from_screenshot(
        self, screenshot_png: bytes | None, tick: int, x: float, y: float
    ) -> dict | None:
        if screenshot_png is None or not self.settings.gemini_api_key:
            return None
        vision_prompt = (
            f"You are a Doom map QA visual inspector. Analyze this screenshot taken at tick {tick}, "
            f"position ({x:.1f}, {y:.1f}). Return JSON with defect info if you see a gameplay-affecting visible defect, "
            "or null if no defect is visible."
            "\n\nLook for:\n"
            "- HOM (Hall of Mirrors), missing textures, Medusa, or tutti-frutti rendering failures\n"
            "- Visible stuck monsters clipping into walls or each other\n"
            "- Zero-height or invisible sectors that affect navigation or visibility\n"
            "- HUD readout issues — negative health/armor\n"
            "- Overlapping or z-fighting geometry that hides gameplay-critical space\n\n"
            "Do not report cosmetic texture alignment, tiling, offset, pillar, floor, wall seam, or pattern-repeat issues.\n\n"
            "Respond with EXACTLY this JSON (no markdown, no extra text):\n"
            '{"defect_type": "visual_hom|visual_stuck_monster|visual_hud_anomaly|visual_geometry_glitch", '
            '"title": "concise title", '
            '"description": "specific description of what is visible", '
            '"severity": 1|2|3}'
            "\nIf no defect is visible, respond with: null"
        )
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.settings.gemini_api_key)
            async_client = getattr(client, "aio", None)
            parts = [
                types.Part.from_text(text=vision_prompt),
                types.Part.from_bytes(data=screenshot_png, mime_type="image/png"),
            ]
            await _throttle_local_rate(self.rate_limit_calls_per_minute)
            async with _get_gemini_sem():
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
            text = response.text or ""
            if not text or text.strip().lower() == "null":
                return None
            try:
                data = json.loads(text)
                if (
                    isinstance(data, dict)
                    and "defect_type" in data
                    and not is_low_value_texture_defect(data)
                ):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
            extracted = self._extract_json_balanced(text)
            if extracted:
                try:
                    data = json.loads(extracted)
                    if (
                        isinstance(data, dict)
                        and "defect_type" in data
                        and not is_low_value_texture_defect(data)
                    ):
                        return data
                except (json.JSONDecodeError, ValueError):
                    pass
            return None
        except Exception:
            return None

    async def _call_with_retry(
        self,
        system_prompt: str,
        llm_input: dict[str, Any],
        parser: Callable[[str], dict[str, Any]],
        fallback: Callable[[], tuple[dict[str, Any], dict[str, int]]],
        screenshot_png: bytes | None = None,
        map_layout_png: bytes | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        last_error = ""
        await _throttle_local_rate(self.rate_limit_calls_per_minute)
        for attempt in range(3):
            try:
                response, token_usage = await self._call_gemini(
                    system_prompt,
                    llm_input,
                    screenshot_png=screenshot_png,
                    map_layout_png=map_layout_png,
                )
                _record_api_call()
                return parser(response), token_usage
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Gemini API call attempt %d/3 failed: %s", attempt + 1, last_error
                )
                if _is_rate_limit(exc) and attempt < 2:
                    wait = min(_retry_delay_seconds(exc), 60.0)
                    logger.info(
                        "Rate limited, retrying in %.1fs (attempt %d/3)",
                        wait,
                        attempt + 2,
                    )
                    await asyncio.sleep(wait)
                    continue
                if attempt < 2:
                    logger.info(
                        "Non-rate-limit error, retrying in 5s (attempt %d/3)",
                        attempt + 2,
                    )
                    await asyncio.sleep(5.0)
                    continue
        logger.warning("All 3 Gemini API attempts failed, using deterministic fallback")
        fallback_result, fallback_tokens = fallback()
        fallback_result["reasoning_summary"] = (
            f"Gemini API failed after 3 attempts: {last_error}. "
            f"{fallback_result.get('reasoning_summary', 'Falling back to deterministic.')}"
        )
        return fallback_result, fallback_tokens

    async def _call_gemini(
        self,
        system_prompt: str,
        llm_input: dict,
        screenshot_png: bytes | None = None,
        map_layout_png: bytes | None = None,
    ) -> tuple[str, dict[str, int]]:
        response = await self._generate_content(
            system_prompt,
            llm_input,
            screenshot_png=screenshot_png,
            map_layout_png=map_layout_png,
        )
        token_usage: dict[str, int] = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_usage = {
                "prompt_tokens": getattr(
                    response.usage_metadata, "prompt_token_count", 0
                )
                or 0,
                "completion_tokens": getattr(
                    response.usage_metadata, "candidates_token_count", 0
                )
                or 0,
            }
        return response.text or "", token_usage

    async def _generate_content(
        self,
        system_prompt: str,
        llm_input: dict,
        screenshot_png: bytes | None = None,
        map_layout_png: bytes | None = None,
    ) -> Any:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc

        config_cls = getattr(types, "GenerateContentConfig", None)
        config = (
            config_cls(system_instruction=system_prompt)
            if config_cls is not None
            else None
        )
        user_content = f"CURRENT STATE JSON:\n{json.dumps(llm_input, default=str)}"
        if config is None:
            user_content = f"{system_prompt}\n\n{user_content}"

        # Build parts list: text + optional screenshots
        has_images = screenshot_png is not None or map_layout_png is not None
        async with _get_gemini_sem():
            client = genai.Client(api_key=self.settings.gemini_api_key)
            async_client = getattr(client, "aio", None)

            if async_client is not None and hasattr(async_client, "models"):
                if has_images:
                    parts = [types.Part.from_text(text=user_content)]
                    if map_layout_png is not None:
                        parts.append(
                            types.Part.from_bytes(
                                data=map_layout_png, mime_type="image/png"
                            )
                        )
                    if screenshot_png is not None:
                        parts.append(
                            types.Part.from_bytes(
                                data=screenshot_png, mime_type="image/png"
                            )
                        )
                    kwargs = {
                        "model": self.llm_model,
                        "contents": types.Content(parts=parts, role="user"),
                    }
                else:
                    kwargs = {"model": self.llm_model, "contents": user_content}
                if config is not None:
                    kwargs["config"] = config
                return await async_client.models.generate_content(**kwargs)

            def generate() -> Any:
                if has_images:
                    parts = [types.Part.from_text(text=user_content)]
                    if map_layout_png is not None:
                        parts.append(
                            types.Part.from_bytes(
                                data=map_layout_png, mime_type="image/png"
                            )
                        )
                    if screenshot_png is not None:
                        parts.append(
                            types.Part.from_bytes(
                                data=screenshot_png, mime_type="image/png"
                            )
                        )
                    kwargs = {
                        "model": self.llm_model,
                        "contents": types.Content(parts=parts, role="user"),
                    }
                else:
                    kwargs = {"model": self.llm_model, "contents": user_content}
                if config is not None:
                    kwargs["config"] = config
                return client.models.generate_content(**kwargs)

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
                        candidates.append(text[start : pos + 1])
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
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str):
            raise ValueError("Could not parse LLM response as JSON")
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
        data = self._parse_json_response(text)
        tool = data.get("mcp_tool")
        if not isinstance(tool, str) or not tool:
            raise ValueError("LLM response omitted mcp_tool")
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
            "_decision_source": "gemini",
        }

    def _fallback_decision(
        self, llm_input: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        objects = [
            obj for obj in llm_input.get("scene_objects", []) if isinstance(obj, dict)
        ]
        same_run = (
            llm_input.get("same_run_memory")
            if isinstance(llm_input.get("same_run_memory"), dict)
            else {}
        )
        milestones = (
            same_run.get("older_milestones")
            if isinstance(same_run.get("older_milestones"), dict)
            else {}
        )
        navigation_info = (
            llm_input.get("navigation")
            if isinstance(llm_input.get("navigation"), dict)
            else {}
        )
        completed_object_ids = {
            str(key) for key in (milestones.get("completed_targets") or {})
        }
        failed_object_ids = {
            str(key) for key in (milestones.get("failed_targets") or {})
        }
        weapon_state = (
            llm_input.get("weapon_state")
            if isinstance(llm_input.get("weapon_state"), dict)
            else {}
        )
        best_weapon = weapon_state.get("best_viable_weapon")
        usable_attack_ammo = _number(weapon_state.get("usable_attack_ammo"), 0)
        selected_ammo = _number(weapon_state.get("selected_weapon_ammo"), 0)
        usable_weapons = (
            weapon_state.get("usable_weapons")
            if isinstance(weapon_state.get("usable_weapons"), list)
            else []
        )
        if selected_ammo <= 0 and usable_attack_ammo > 0 and best_weapon is not None:
            return {
                "reasoning_summary": f"{reason} The selected weapon is empty but weapon {best_weapon} is usable, so switching before combat.",
                "mcp_tool": "select_weapon",
                "mcp_params": {"weapon_slot": best_weapon, "max_tics": 20},
                "observed_issue": None,
                "_decision_source": "deterministic_fallback",
            }
        visible_monsters = [
            obj
            for obj in objects
            if obj.get("type") == "monster"
            and obj.get("is_visible")
            and obj.get("id") is not None
        ]
        if visible_monsters:
            target = min(
                visible_monsters, key=lambda obj: float(obj.get("distance") or 999999)
            )
            tool = (
                "strafe_and_shoot"
                if target.get("attack_type") == "hitscan"
                or float(target.get("distance") or 0) < 350
                else "aim_and_shoot"
            )
            return {
                "reasoning_summary": f"{reason} Visible {target.get('name', 'monster')} selected for combat.",
                "mcp_tool": tool,
                "mcp_params": {"object_id": target["id"]},
                "observed_issue": None,
                "_decision_source": "deterministic_fallback",
            }

        visible_pickups = [
            obj
            for obj in objects
            if obj.get("type") in {"item", "ammo", "weapon", "key"}
            and obj.get("is_visible")
            and obj.get("id") is not None
            and str(obj.get("id")) not in completed_object_ids
            and str(obj.get("id")) not in failed_object_ids
        ]
        if visible_pickups:
            target = min(
                visible_pickups, key=lambda obj: float(obj.get("distance") or 999999)
            )
            return {
                "reasoning_summary": f"{reason} Visible {target.get('name', 'pickup')} selected for collection.",
                "mcp_tool": "move_to",
                "mcp_params": {"object_id": target["id"], "stop_on_enemy": True},
                "observed_issue": None,
                "_decision_source": "deterministic_fallback",
            }

        if not usable_weapons:
            return {
                "reasoning_summary": f"{reason} No usable weapon is available, so looking for resources or space before reassessing.",
                "mcp_tool": "retreat",
                "mcp_params": {"tics": 28},
                "observed_issue": None,
                "_decision_source": "deterministic_fallback",
            }

        unexplored_direction = (
            navigation_info.get("unexplored_direction")
            if isinstance(navigation_info, dict)
            else None
        )
        if unexplored_direction:
            return {
                "reasoning_summary": f"{reason} Navigation info indicates unexplored area to the {unexplored_direction}, exploring toward it.",
                "mcp_tool": "explore",
                "mcp_params": {
                    "max_tics": 80,
                    "stop_on_enemy": True,
                    "stop_on_item": True,
                },
                "observed_issue": None,
                "_decision_source": "deterministic_fallback",
            }

        return {
            "reasoning_summary": f"{reason} No actionable target is visible, so exploring for new evidence.",
            "mcp_tool": "explore",
            "mcp_params": {"max_tics": 80, "stop_on_enemy": True, "stop_on_item": True},
            "observed_issue": None,
            "_decision_source": "deterministic_fallback",
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
        logger.info(
            "Local rate limiter: %d calls in last 60s, waiting %.1fs",
            len(_api_call_timestamps),
            wait,
        )
        await asyncio.sleep(wait)


def _record_api_call() -> None:
    global _api_call_timestamps
    _api_call_timestamps.append(time.monotonic())
    _api_call_timestamps = [
        t for t in _api_call_timestamps if time.monotonic() - t < 60.0
    ]


def estimate_llm_cost_usd(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    *,
    input_cost_per_million: float,
    output_cost_per_million: float,
) -> float:
    input_cost = max(0, int(prompt_tokens or 0)) * input_cost_per_million / 1_000_000
    output_cost = (
        max(0, int(completion_tokens or 0)) * output_cost_per_million / 1_000_000
    )
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
