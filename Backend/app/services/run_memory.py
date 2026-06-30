from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentDecision, Defect, GameEvent, WadHypothesis, WadSpatialMemory
from app.services.analysis_constants import CELL_SIZE


class RunMemoryService:
    """Persist reviewer-facing cross-run analytics without influencing gameplay."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def persist_spatial_memory(
        self,
        run_id: UUID,
        wad_file_id: UUID,
        map_name: str,
        events: list[GameEvent],
        defects: list[Defect],
    ) -> None:
        cell_events: dict[tuple[int, int, str], int] = defaultdict(int)
        previous_secret_count = 0
        for event in events:
            cx = round(event.player_x / CELL_SIZE)
            cy = round(event.player_y / CELL_SIZE)
            cell_events[(cx, cy, "visited")] += 1
            if event.event_type in {"stuck", "death", "kill", "secret_found"}:
                cell_events[(cx, cy, event.event_type)] += 1
            if int(event.secret_count or 0) > previous_secret_count:
                cell_events[(cx, cy, "secret_found")] += 1
            previous_secret_count = max(
                previous_secret_count, int(event.secret_count or 0)
            )

        for defect in defects:
            if defect.position_x is None or defect.position_y is None:
                continue
            cx = round(defect.position_x / CELL_SIZE)
            cy = round(defect.position_y / CELL_SIZE)
            event_type = defect.defect_type
            if event_type not in {
                "stuck",
                "death",
                "ammo_starvation",
                "health_deficit",
                "softlock_navigation",
            }:
                continue
            cell_events[
                (cx, cy, "stuck" if event_type == "softlock_navigation" else event_type)
            ] += 1

        now = datetime.now(UTC)
        for (cell_x, cell_y, event_type), count in cell_events.items():
            stmt = (
                pg_insert(WadSpatialMemory)
                .values(
                    wad_file_id=wad_file_id,
                    map_name=map_name.upper(),
                    cell_x=cell_x,
                    cell_y=cell_y,
                    event_type=event_type,
                    occurrence_count=count,
                    last_seen_run_id=run_id,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[
                        "wad_file_id",
                        "map_name",
                        "cell_x",
                        "cell_y",
                        "event_type",
                    ],
                    set_={
                        "occurrence_count": WadSpatialMemory.occurrence_count + count,
                        "last_seen_run_id": run_id,
                        "updated_at": now,
                    },
                )
            )
            await self.db.execute(stmt)

    async def persist_state_action_transitions(
        self,
        run_id: UUID,
        wad_file_id: UUID,
        map_name: str,
        decisions: list[AgentDecision],
    ) -> None:
        """Track state-action transitions across runs for coverage-guided exploration.

        Inspired by TITAN's Execution Coverage Memory (Section 3.4).
        Maintains a persistent memory of abstract states and actions explored,
        tagging transitions with outcomes (success, failure, stuck, etc.).
        """
        transitions: dict[tuple[str, str, str], int] = defaultdict(int)
        outcomes: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
            lambda: {"success": 0, "failure": 0, "stuck": 0}
        )

        for i, decision in enumerate(decisions):
            if decision.mcp_tool is None:
                continue

            state_before = decision.llm_input_summary or {}
            state_snapshot = self._abstract_state(state_before)
            action = decision.mcp_tool
            stop_reason = decision.mcp_stop_reason or "unknown"

            transition_key = (state_snapshot, action, stop_reason)
            transitions[transition_key] += 1

            if stop_reason in {"target_killed", "item_found", "key_found", "map_exit"}:
                outcomes[transition_key]["success"] += 1
            elif stop_reason in {
                "target_lost",
                "target_not_visible",
                "out_of_ammo",
                "no_usable_weapon",
                "invalid_params",
            }:
                outcomes[transition_key]["failure"] += 1
            elif stop_reason in {"stuck", "arrival_blocked"}:
                outcomes[transition_key]["stuck"] += 1

        now = datetime.now(UTC)
        for (state_snapshot, action, stop_reason), count in transitions.items():
            outcome_counts = outcomes[(state_snapshot, action, stop_reason)]
            stmt = (
                pg_insert(WadSpatialMemory)
                .values(
                    wad_file_id=wad_file_id,
                    map_name=map_name.upper(),
                    cell_x=hash(state_snapshot) % 10000,
                    cell_y=hash(action) % 10000,
                    event_type=f"transition:{stop_reason}",
                    occurrence_count=count,
                    last_seen_run_id=run_id,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[
                        "wad_file_id",
                        "map_name",
                        "cell_x",
                        "cell_y",
                        "event_type",
                    ],
                    set_={
                        "occurrence_count": WadSpatialMemory.occurrence_count + count,
                        "last_seen_run_id": run_id,
                        "updated_at": now,
                    },
                )
            )
            await self.db.execute(stmt)

    def _abstract_state(self, state: dict[str, Any]) -> str:
        """Abstract raw game state into a compact representation.

        Following TITAN's Perception Abstraction Module (Section 3.2):
        - Discretize continuous values (health, ammo, position)
        - Filter irrelevant data
        - Encode into concise textual format
        """
        game_vars = state.get("game_variables", {})

        health = int(game_vars.get("HEALTH", 100) or 100)
        if health <= 0:
            health_bucket = "dead"
        elif health < 20:
            health_bucket = "critical"
        elif health < 50:
            health_bucket = "low"
        elif health < 80:
            health_bucket = "medium"
        else:
            health_bucket = "high"

        ammo = (
            int(game_vars.get("AMMO", 0) or 0)
            + int(game_vars.get("SHELLS", 0) or 0)
            + int(game_vars.get("ROCKETS", 0) or 0)
            + int(game_vars.get("CELLS", 0) or 0)
        )
        if ammo == 0:
            ammo_bucket = "empty"
        elif ammo < 20:
            ammo_bucket = "low"
        elif ammo < 50:
            ammo_bucket = "medium"
        else:
            ammo_bucket = "high"

        kills = int(game_vars.get("KILLCOUNT", 0) or 0)
        secrets = int(game_vars.get("SECRETCOUNT", 0) or 0)

        return f"hp:{health_bucket}|ammo:{ammo_bucket}|kills:{kills}|secrets:{secrets}"

    async def persist_hypotheses(
        self,
        run_id: UUID,
        wad_file_id: UUID,
        map_name: str,
        in_run_hypotheses: list[str],
        agent_quality_flags: dict[str, Any] | None,
    ) -> None:
        existing_result = await self.db.execute(
            select(WadHypothesis).where(
                WadHypothesis.wad_file_id == wad_file_id,
                WadHypothesis.map_name == map_name.upper(),
                WadHypothesis.refuted_at.is_(None),
            )
        )
        existing = list(existing_result.scalars().all())
        candidates = list(in_run_hypotheses)
        if agent_quality_flags:
            candidates.extend(
                str(warning) for warning in agent_quality_flags.get("warnings") or []
            )

        for hypothesis in candidates:
            if not _is_persistable_hypothesis(hypothesis):
                continue
            match = next(
                (
                    item
                    for item in existing
                    if _similar_text(hypothesis.lower(), item.content.lower())
                ),
                None,
            )
            if match is not None:
                match.last_seen_run_id = run_id
                match.confidence = min(1.0, match.confidence + 0.15)
                match.updated_at = datetime.now(UTC)
                continue
            new_hypothesis = WadHypothesis(
                wad_file_id=wad_file_id,
                map_name=map_name.upper(),
                tag=_infer_tag(hypothesis),
                content=hypothesis[:500],
                confidence=0.3,
                last_seen_run_id=run_id,
            )
            self.db.add(new_hypothesis)
            existing.append(new_hypothesis)


def _similar_text(a: str, b: str) -> bool:
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return a == b
    return len(words_a & words_b) / max(len(words_a), len(words_b)) >= 0.4


def _is_persistable_hypothesis(text: str) -> bool:
    import re

    lower = text.lower().strip()
    if len(lower) < 20:
        return False
    noise_markers = (
        "suspected false positive",
        "switching",
        "clearing",
        "recent combat",
        "already returned",
        "red-textured",
        "red textured",
    )
    if any(marker in lower for marker in noise_markers):
        return False
    only_speculation = ("maybe", "possibly", "unclear", "hypothesis")
    has_only_speculation = any(marker in lower for marker in only_speculation)
    has_evidence_anchor = bool(
        re.search(r"tick \d+|position \(|cell \(|at \(-?\d|\(\s*-?\d", lower)
    )
    has_conclusion = any(
        marker in lower
        for marker in (
            "confirmed",
            "observed issue",
            "defect",
            "softlock",
            "no exit",
            "no usable",
            "unreachable",
            "blocked after",
            "does not respond",
            "ammo starvation",
            "no reachable",
            "progression defect",
            "sealed",
            "no interactable",
            "exhausted",
        )
    )
    if has_only_speculation and not has_evidence_anchor and not has_conclusion:
        return False
    return has_evidence_anchor or has_conclusion


def _infer_tag(text: str) -> str:
    lower = text.lower()
    if "blocked" in lower or "collision" in lower or "unreachable" in lower:
        return "BLOCKED_PATH"
    if "key" in lower:
        return "KEY_LOCATION"
    if "ammo" in lower or "starvation" in lower or "resource" in lower:
        return "RESOURCE_CACHE"
    if any(
        term in lower
        for term in (
            "visual",
            "glitch",
            "missing texture",
            "hall of mirrors",
            "hom effect",
        )
    ):
        return "VISUAL_GLITCH"
    if "encounter" in lower or "combat" in lower or "monster" in lower:
        return "ENCOUNTER_HOTSPOT"
    return "NAVIGATION_GAP"
