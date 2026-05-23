from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentPositionTrail, Defect, GameEvent, NotableEventScreenshot
from app.repositories.defect_repository import DefectRepository
from app.repositories.game_event_repository import GameEventRepository


STUCK_DECISION_THRESHOLD = 5


class CollectorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = GameEventRepository(db)
        self._previous: dict[str, Any] | None = None
        self._stuck_count = 0

    async def collect(
        self,
        run_id: UUID,
        tick: int,
        state: dict[str, Any],
        llm_input: dict[str, Any],
        decision: dict[str, Any],
        mcp_call: dict[str, Any],
        agent_decision_id: UUID | None = None,
    ) -> GameEvent:
        variables = normalize_variables(state)
        detected_event_type = self.detect_event(variables)
        event_type = detected_event_type
        if detected_event_type == "normal" and decision.get("event_type_override"):
            event_type = str(decision["event_type_override"])
        mcp_output = mcp_call.get("output")
        action_summary = mcp_output.get("action_summary") if isinstance(mcp_output, dict) else None
        action_taken = {
            "mcp_tool": decision.get("mcp_tool"),
            "mcp_executed_tool": mcp_call.get("tool") or decision.get("mcp_tool"),
            "mcp_params": decision.get("mcp_params") or {},
            "mcp_service": mcp_call.get("service", "mcp-doom"),
            "mcp_input": mcp_call.get("input"),
            "mcp_output": mcp_output,
        }
        if isinstance(action_summary, dict):
            action_taken["mcp_action_summary"] = action_summary
            if action_summary.get("stop_reason") is not None:
                action_taken["mcp_stop_reason"] = str(action_summary["stop_reason"])
        if decision.get("recording_fidelity_warning"):
            action_taken["recording_fidelity_warning"] = decision["recording_fidelity_warning"]
        if decision.get("tool_param_warning"):
            action_taken["tool_param_warning"] = decision["tool_param_warning"]
        event = GameEvent(
            run_id=run_id,
            tick_number=tick,
            player_x=float(variables["x"]),
            player_y=float(variables["y"]),
            player_angle=int(variables["angle"]),
            health=int(variables["health"]),
            armor=int(variables["armor"]),
            ammo_bullets=int(variables["ammo_bullets"]),
            ammo_shells=int(variables["ammo_shells"]),
            ammo_rockets=int(variables["ammo_rockets"]),
            ammo_cells=int(variables["ammo_cells"]),
            kill_count=int(variables["kill_count"]),
            item_count=int(variables["item_count"]),
            secret_count=int(variables["secret_count"]),
            weapon_selected=int(variables["weapon_selected"]),
            agent_decision_id=agent_decision_id,
            event_type=event_type,
            damage_received=variables.get("damage_received"),
            llm_input_summary=_compact_llm_event_summary(tick, event_type, variables),
            llm_reasoning=decision.get("reasoning_summary"),
            action_taken=action_taken,
        )
        event = await self.repo.create_event(event)
        await self.repo.create_position(
            AgentPositionTrail(
                run_id=run_id,
                tick_number=tick * 1000 + 999,
                x=event.player_x,
                y=event.player_y,
                health=event.health,
            )
        )
        issue = decision.get("observed_issue")
        if issue:
            defect_repo = DefectRepository(self.db)
            defect_type, title = normalize_observed_issue(issue)
            if not await defect_repo.exists_by_type_title(run_id, defect_type, title):
                existing = await defect_repo.list_by_run(run_id)
                is_duplicate = False
                for defect in existing:
                    if defect.defect_type != defect_type:
                        continue
                    if defect.detected_at_tick is not None and abs(defect.detected_at_tick - tick) < 500:
                        if defect.position_x is not None and defect.position_y is not None:
                            dist = ((defect.position_x - event.player_x) ** 2 + (defect.position_y - event.player_y) ** 2) ** 0.5
                            if dist < 100:
                                is_duplicate = True
                                break
                if not is_duplicate:
                    issue_description = (
                        issue.get("description") if isinstance(issue, dict) else str(issue)
                    )
                    await defect_repo.create(
                        Defect(
                            run_id=run_id,
                            severity=2,
                            priority=2,
                            defect_type=defect_type,
                            title=title,
                            description=issue_description,
                            detected_at_tick=tick,
                            position_x=event.player_x,
                            position_y=event.player_y,
                        )
                    )
        self._previous = variables
        return event

    async def collect_position(self, run_id: UUID, tick_number: int, state: dict[str, Any]) -> None:
        variables = normalize_variables(state)
        await self.repo.create_position(
            AgentPositionTrail(
                run_id=run_id,
                tick_number=tick_number,
                x=float(variables["x"]),
                y=float(variables["y"]),
                health=int(variables["health"]),
            )
        )

    async def attach_screenshot(self, run_id: UUID, event: GameEvent, screenshot_path: str) -> None:
        await self.repo.create_screenshot(
            NotableEventScreenshot(run_id=run_id, game_event_id=event.id, screenshot_path=screenshot_path)
        )

    def detect_event(self, current: dict[str, Any]) -> str:
        if current.get("level_completed") or current.get("map_exit"):
            return "map_exit"
        previous = self._previous
        if current["health"] <= 0:
            return "death"
        if previous is None:
            return "normal"
        if current["kill_count"] > previous["kill_count"]:
            return "kill"
        if current["secret_count"] > previous["secret_count"]:
            return "secret_found"
        if current["item_count"] > previous["item_count"]:
            return "item_pickup"
        if current["health"] < previous["health"]:
            current["damage_received"] = previous["health"] - current["health"]
            return "damage_taken"
        if _changed_resources_or_score(current, previous):
            self._stuck_count = 0
            return "normal"
        if abs(current["x"] - previous["x"]) < 1 and abs(current["y"] - previous["y"]) < 1:
            self._stuck_count += 1
            if self._stuck_count >= STUCK_DECISION_THRESHOLD:
                return "stuck"
        else:
            self._stuck_count = 0
        return "normal"


def normalize_variables(state: dict[str, Any]) -> dict[str, Any]:
    variables = state.get("game_variables") or state.get("variables") or state

    def num(*keys: str, default: float = 0) -> float:
        for key in keys:
            if key in variables and variables[key] is not None:
                return variables[key]
        return default

    normalized = {
        "x": num("POSITION_X", "position_x", "x"),
        "y": num("POSITION_Y", "position_y", "y"),
        "angle": num("ANGLE", "angle", "player_angle"),
        "health": num("HEALTH", "health"),
        "armor": num("ARMOR", "armor"),
        "ammo_bullets": num("AMMO0", "ammo_bullets", "bullets"),
        "ammo_shells": num("AMMO1", "ammo_shells", "shells"),
        "ammo_rockets": num("AMMO2", "ammo_rockets", "rockets"),
        "ammo_cells": num("AMMO3", "ammo_cells", "cells"),
        "kill_count": num("KILLCOUNT", "kill_count", "kills"),
        "item_count": num("ITEMCOUNT", "item_count", "items"),
        "secret_count": num("SECRETCOUNT", "secret_count", "secrets"),
        "weapon_selected": num("SELECTED_WEAPON", "weapon_selected"),
    }
    normalized["level_completed"] = bool(state.get("level_completed") or state.get("next_map"))
    normalized["map_exit"] = bool(state.get("map_exit"))
    normalized["ammo_total"] = (
        normalized["ammo_bullets"]
        + normalized["ammo_shells"]
        + normalized["ammo_rockets"]
        + normalized["ammo_cells"]
    )
    return normalized


def _changed_resources_or_score(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    watched_keys = (
        "ammo_total",
        "armor",
        "weapon_selected",
        "kill_count",
        "item_count",
        "secret_count",
    )
    return any(current.get(key) != previous.get(key) for key in watched_keys)


_KNOWN_DEFECT_CATEGORIES = {"geometry", "resource_balance", "progression", "encounter_design", "pwad_crash"}


def normalize_observed_issue(issue: Any) -> tuple[str, str]:
    if isinstance(issue, dict):
        raw = str(issue.get("category") or "agent_observed").strip().lower()
        description = issue.get("description") or ""
    else:
        text = str(issue)
        match = re.match(r"\s*\[([^\]]+)\]", text)
        raw = (match.group(1) if match else "agent observed").strip().lower()
        description = text

    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_") or "issue"
    normalized_category = slug if slug in _KNOWN_DEFECT_CATEGORIES else "agent_observed"
    defect_type = f"agent_observed_{normalized_category}"[:64]
    title = f"Automated playthrough observed {normalized_category.replace('_', ' ')} issue"
    return defect_type, title[:255]


def _compact_llm_event_summary(tick: int, event_type: str, variables: dict[str, Any]) -> str:
    summary = {
        "tick": tick,
        "event_type": event_type,
        "hp": variables.get("health"),
        "armor": variables.get("armor"),
        "kills": variables.get("kill_count"),
        "items": variables.get("item_count"),
        "secrets": variables.get("secret_count"),
        "ammo_total": variables.get("ammo_total"),
    }
    return json.dumps(summary, separators=(",", ":"), default=str)[:200]
