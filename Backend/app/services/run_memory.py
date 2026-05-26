from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentDecision,
    Defect,
    GameEvent,
    TestRun,
    WadHypothesis,
    WadKnowledgeBase,
    WadSpatialMemory,
)
from app.services.gemini_service import GeminiService


STUCK_OUTCOMES = {"stuck"}
FAILED_STOP_REASONS = {
    "arrival_blocked",
    "enemy_nearby",
    "max_tics",
    "no_target",
    "out_of_ammo",
    "pickup_not_collected",
    "stuck",
    "target_lost",
    "target_not_visible",
}
HYPOTHESIS_TAGS = {"BLOCKED_PATH", "KEY_LOCATION", "RESOURCE_CACHE", "VISUAL_GLITCH", "ENCOUNTER_HOTSPOT", "NAVIGATION_GAP"}


class RunMemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def recommend_behavior_profile(
        self,
        wad_file_id: UUID,
        map_name: str,
        requested_profile: str | None,
        default_profile: str,
    ) -> str:
        selected = requested_profile or default_profile
        if requested_profile is not None or selected != "thorough":
            return selected

        result = await self.db.execute(
            select(TestRun)
            .where(
                TestRun.wad_file_id == wad_file_id,
                TestRun.map_name == map_name.upper(),
                TestRun.behavior_profile == "thorough",
                TestRun.outcome.isnot(None),
            )
            .order_by(TestRun.created_at.desc())
            .limit(10)
        )
        recent_thorough = list(result.scalars().all())
        if len(recent_thorough) == 10 and all(run.outcome == "stuck" for run in recent_thorough):
            return "fast"
        return selected

    async def build_cross_run_memory(
        self,
        wad_file_id: UUID,
        map_name: str,
        current_run_id: UUID | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        runs = await self._recent_runs(wad_file_id, map_name, current_run_id, limit)
        if not runs:
            return {
                "prior_run_count": 0,
                "outcome_counts": {},
                "warnings": [],
                "prompt": "No prior runs exist for this WAD/map.",
            }

        run_ids = [run.id for run in runs]
        latest_events = await self._latest_events(run_ids)
        defects_by_run, defect_patterns = await self._defects(run_ids)
        recent_decisions = await self._recent_decisions(run_ids)
        outcome_counts = Counter(str(run.outcome or "unknown") for run in runs)
        warnings = self._warnings(runs, defects_by_run)
        last_run = runs[0]
        last_event = latest_events.get(last_run.id)
        last_attempts = [
            attempt
            for attempt in (
                _decision_attempt(decision)
                for decision in recent_decisions.get(last_run.id, [])
            )
            if attempt is not None
        ][:3]
        memory = {
            "prior_run_count": len(runs),
            "outcome_counts": dict(outcome_counts),
            "last_run": _last_run_summary(last_run, last_event, last_attempts),
            "same_outcome_previous_count": sum(
                1 for run in runs[1:] if run.outcome and run.outcome == last_run.outcome
            ),
            "defect_patterns": defect_patterns[:5],
            "warnings": warnings,
        }
        memory["prompt"] = format_cross_run_memory(memory)
        return memory

    async def build_spatial_memory_briefing(
        self, wad_file_id: UUID, map_name: str
    ) -> str:
        result = await self.db.execute(
            select(
                WadSpatialMemory.cell_x,
                WadSpatialMemory.cell_y,
                WadSpatialMemory.event_type,
                func.sum(WadSpatialMemory.occurrence_count).label("total_occurrences"),
            )
            .where(
                WadSpatialMemory.wad_file_id == wad_file_id,
                WadSpatialMemory.map_name == map_name.upper(),
            )
            .group_by(WadSpatialMemory.cell_x, WadSpatialMemory.cell_y, WadSpatialMemory.event_type)
            .order_by(func.sum(WadSpatialMemory.occurrence_count).desc())
        )
        rows = result.all()
        if not rows:
            return ""

        stuck_cells = []
        death_cells = []
        key_cells = []
        secret_cells = []
        starve_cells = []
        visited_count = 0
        for row in rows:
            total = int(row.total_occurrences or 0)
            cell = f"cell ({row.cell_x},{row.cell_y}) {total}x"
            if row.event_type == "stuck":
                stuck_cells.append(cell)
            elif row.event_type == "death":
                death_cells.append(cell)
            elif row.event_type == "key_found":
                key_cells.append(cell)
            elif row.event_type == "secret_found":
                secret_cells.append(cell)
            elif row.event_type in {"ammo_starvation", "health_deficit"}:
                starve_cells.append(cell)
            elif row.event_type == "visited":
                visited_count += 1

        parts = []
        if stuck_cells:
            parts.append(f"Stuck events recorded in {len(stuck_cells)} cell(s): {', '.join(stuck_cells[:6])}")
        if death_cells:
            parts.append(f"Deaths recorded in {len(death_cells)} cell(s): {', '.join(death_cells[:6])}")
        if key_cells:
            parts.append(f"Keys found in {len(key_cells)} cell(s): {', '.join(key_cells[:6])}")
        if secret_cells:
            parts.append(f"Secrets found in {len(secret_cells)} cell(s): {', '.join(secret_cells[:6])}")
        if starve_cells:
            parts.append(f"Resource starvation in {len(starve_cells)} cell(s): {', '.join(starve_cells[:6])}")
        if visited_count:
            parts.append(f"Prior runs recorded visited coverage in {visited_count} coarse cell(s).")
        if not parts:
            return ""
        return "Spatial memory from prior runs:\n" + "\n".join(parts)

    async def build_hypotheses_briefing(
        self, wad_file_id: UUID, map_name: str
    ) -> str:
        result = await self.db.execute(
            select(WadHypothesis)
            .where(
                WadHypothesis.wad_file_id == wad_file_id,
                WadHypothesis.map_name == map_name.upper(),
                WadHypothesis.refuted_at.is_(None),
            )
            .order_by(WadHypothesis.confidence.desc())
            .limit(10)
        )
        hypotheses = list(result.scalars().all())
        if not hypotheses:
            return ""
        lines = ["Persistent hypotheses about this map (accumulated across runs):"]
        for h in hypotheses:
            tag = h.tag
            confidence = f"{h.confidence:.0%}" if h.confidence <= 1 else f"{h.confidence:.0%}"
            lines.append(f"  [{tag}] (confidence {confidence}) {h.content}")
        return "\n".join(lines)

    async def build_knowledge_briefing(
        self, wad_file_id: UUID, map_name: str
    ) -> str:
        result = await self.db.execute(
            select(WadKnowledgeBase)
            .where(
                WadKnowledgeBase.wad_file_id == wad_file_id,
                WadKnowledgeBase.map_name == map_name.upper(),
            )
            .limit(1)
        )
        kb = result.scalar_one_or_none()
        if kb is None or not kb.document_text.strip():
            return ""
        return f"Accumulated knowledge about this map (v{kb.version}):\n{kb.document_text[:2000]}"

    async def persist_spatial_memory(
        self,
        run_id: UUID,
        wad_file_id: UUID,
        map_name: str,
        events: list[GameEvent],
        defects: list[Defect],
    ) -> None:
        CELL_SIZE = 128.0
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
            previous_secret_count = max(previous_secret_count, int(event.secret_count or 0))

        for defect in defects:
            if defect.position_x is not None and defect.position_y is not None:
                cx = round(defect.position_x / CELL_SIZE)
                cy = round(defect.position_y / CELL_SIZE)
                etype = defect.defect_type
                if etype not in {"stuck", "death", "ammo_starvation", "health_deficit", "softlock_navigation"}:
                    continue
                if etype == "softlock_navigation":
                    etype = "stuck"
                cell_events[(cx, cy, etype)] += 1

        now = datetime.now(UTC)
        for (cx, cy, etype), count in cell_events.items():
            stmt = (
                pg_insert(WadSpatialMemory)
                .values(
                    wad_file_id=wad_file_id,
                    map_name=map_name.upper(),
                    cell_x=cx,
                    cell_y=cy,
                    event_type=etype,
                    occurrence_count=count,
                    last_seen_run_id=run_id,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["wad_file_id", "map_name", "cell_x", "cell_y", "event_type"],
                    set_={
                        "occurrence_count": WadSpatialMemory.occurrence_count + count,
                        "last_seen_run_id": run_id,
                        "updated_at": now,
                    },
                )
            )
            await self.db.execute(stmt)

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
        matched_any = False
        for hyp_text in in_run_hypotheses:
            if not _is_persistable_hypothesis(hyp_text):
                continue
            text_lower = hyp_text.lower()
            match = None
            for existing_hyp in existing:
                if _similar_text(text_lower, existing_hyp.content.lower()):
                    match = existing_hyp
                    break
            if match:
                match.last_seen_run_id = run_id
                match.confidence = min(1.0, match.confidence + 0.15)
                match.updated_at = datetime.now(UTC)
                matched_any = True
            else:
                tag = _infer_tag(hyp_text)
                new_hyp = WadHypothesis(
                    wad_file_id=wad_file_id,
                    map_name=map_name.upper(),
                    tag=tag,
                    content=hyp_text[:500],
                    confidence=0.3,
                    confirmed_at=datetime.now(UTC),
                    last_seen_run_id=run_id,
                )
                self.db.add(new_hyp)

        if agent_quality_flags:
            for warning in agent_quality_flags.get("warnings") or []:
                if not _is_persistable_hypothesis(warning):
                    continue
                text_lower = warning.lower()
                tag = _infer_tag(warning)
                match = None
                for existing_hyp in existing:
                    if _similar_text(text_lower, existing_hyp.content.lower()):
                        match = existing_hyp
                        break
                if not match:
                    self.db.add(WadHypothesis(
                        wad_file_id=wad_file_id,
                        map_name=map_name.upper(),
                        tag=tag,
                        content=warning[:500],
                        confidence=0.6,
                        confirmed_at=datetime.now(UTC),
                        last_seen_run_id=run_id,
                    ))

    async def update_knowledge_document(
        self,
        run_id: UUID,
        wad_file_id: UUID,
        map_name: str,
        outcome: str | None,
        duration: int | None,
        defect_count: int,
        action_count: int,
        game_tick_count: int,
        defects: list[Defect],
    ) -> str:
        result = await self.db.execute(
            select(WadKnowledgeBase).where(
                WadKnowledgeBase.wad_file_id == wad_file_id,
                WadKnowledgeBase.map_name == map_name.upper(),
            ).limit(1)
        )
        kb = result.scalar_one_or_none()
        current_doc = kb.document_text if kb else ""
        version = (kb.version if kb else 0) + 1

        change_log = []
        if outcome:
            change_log.append(f"Outcome: {outcome}")
        if duration:
            change_log.append(f"Duration: {duration}s")
        change_log.append(f"Actions: {action_count}")
        change_log.append(f"Game ticks: {game_tick_count}")
        change_log.append(f"Defects found: {defect_count}")
        for defect in defects:
            change_log.append(f"  - {defect.defect_type}: {defect.title}")
            if defect.position_x is not None:
                change_log.append(f"    at ({round(defect.position_x, 1)}, {round(defect.position_y, 1)})")

        if current_doc:
            new_text = (
                f"=== Update from run completed at {datetime.now(UTC).isoformat()} ===\n"
                f"Run: {run_id}\n"
                + "\n".join(change_log)
                + "\n\n"
                + current_doc
            )
        else:
            new_text = (
                f"Knowledge document for {map_name} (v{version})\n"
                f"Created from run {run_id}\n"
                + "\n".join(change_log)
            )
        new_text = new_text[:10000]

        if kb:
            kb.document_text = new_text
            kb.version = version
            kb.updated_at = datetime.now(UTC)
        else:
            self.db.add(WadKnowledgeBase(
                wad_file_id=wad_file_id,
                map_name=map_name.upper(),
                document_text=new_text,
                version=version,
            ))
        return new_text

    async def _recent_runs(
        self,
        wad_file_id: UUID,
        map_name: str,
        current_run_id: UUID | None,
        limit: int,
    ) -> list[TestRun]:
        query = select(TestRun).where(
            TestRun.wad_file_id == wad_file_id,
            TestRun.map_name == map_name.upper(),
            TestRun.outcome.isnot(None),
        )
        if current_run_id is not None:
            query = query.where(TestRun.id != current_run_id)
        query = query.order_by(TestRun.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _latest_events(self, run_ids: list[UUID]) -> dict[UUID, GameEvent]:
        result = await self.db.execute(
            select(GameEvent)
            .where(GameEvent.run_id.in_(run_ids))
            .order_by(GameEvent.run_id, GameEvent.tick_number.desc())
        )
        latest: dict[UUID, GameEvent] = {}
        for event in result.scalars().all():
            latest.setdefault(event.run_id, event)
        return latest

    async def _defects(self, run_ids: list[UUID]) -> tuple[dict[UUID, list[Defect]], list[dict[str, Any]]]:
        result = await self.db.execute(
            select(Defect)
            .where(Defect.run_id.in_(run_ids))
            .order_by(Defect.defect_type, Defect.title, Defect.created_at.desc())
        )
        by_run: dict[UUID, list[Defect]] = defaultdict(list)
        by_fingerprint: dict[str, list[Defect]] = defaultdict(list)
        for defect in result.scalars().all():
            by_run[defect.run_id].append(defect)
            key = defect.fingerprint or f"{defect.defect_type}:{defect.title}"
            by_fingerprint[key].append(defect)
        patterns = []
        for key, group in by_fingerprint.items():
            if len(group) < 2:
                continue
            sample = group[0]
            patterns.append(
                {
                    "fingerprint": key,
                    "type": sample.defect_type,
                    "title": sample.title,
                    "count": len(group),
                    "affected_runs": len({defect.run_id for defect in group}),
                }
            )
        patterns.sort(key=lambda item: item["count"], reverse=True)
        return dict(by_run), patterns

    async def _recent_decisions(self, run_ids: list[UUID]) -> dict[UUID, list[AgentDecision]]:
        result = await self.db.execute(
            select(AgentDecision)
            .where(AgentDecision.run_id.in_(run_ids))
            .order_by(AgentDecision.run_id, AgentDecision.sequence_number.desc())
        )
        grouped: dict[UUID, list[AgentDecision]] = defaultdict(list)
        for decision in result.scalars().all():
            if len(grouped[decision.run_id]) < 8:
                grouped[decision.run_id].append(decision)
        return dict(grouped)

    @staticmethod
    def _warnings(runs: list[TestRun], defects_by_run: dict[UUID, list[Defect]]) -> list[str]:
        warnings: list[str] = []
        ammo_defects = [
            defect
            for defects in defects_by_run.values()
            for defect in defects
            if defect.defect_type == "ammo_starvation"
        ]
        if ammo_defects:
            warnings.append(
                f"{len(ammo_defects)} prior ammo starvation/resource defect(s); prioritize ammo and weapon pickups early."
            )
        thorough = [run for run in runs if run.behavior_profile == "thorough"]
        if len(thorough) >= 10 and all(run.outcome == "stuck" for run in thorough[:10]):
            warnings.append(
                "The 10 most recent thorough-profile runs all ended stuck; use wider coverage before deep rechecks."
            )
        return warnings[:5]


def format_cross_run_memory(memory: dict[str, Any]) -> str:
    if not memory.get("prior_run_count"):
        return str(memory.get("prompt") or "No prior runs exist for this WAD/map.")

    parts = [
        (
            f"Prior same-WAD/map runs considered: {memory['prior_run_count']}. "
            f"Outcomes: {_format_counts(memory.get('outcome_counts') or {})}."
        )
    ]
    last_run = memory.get("last_run") if isinstance(memory.get("last_run"), dict) else {}
    if last_run:
        parts.append(_format_last_run(last_run))
    same_count = int(memory.get("same_outcome_previous_count") or 0)
    outcome = last_run.get("outcome")
    if outcome and same_count:
        parts.append(f"{same_count} previous run(s) had the same final outcome: {outcome}.")
    patterns = memory.get("defect_patterns") if isinstance(memory.get("defect_patterns"), list) else []
    if patterns:
        pattern_text = "; ".join(
            f"{item.get('title')} ({item.get('count')}x)" for item in patterns[:3]
        )
        parts.append(f"Repeated prior defects: {pattern_text}.")
    for warning in memory.get("warnings") or []:
        parts.append(f"Warning: {warning}")
    return "\n".join(parts)[:2500]


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _format_last_run(last_run: dict[str, Any]) -> str:
    location = ""
    if last_run.get("tick") is not None:
        location = f" at tick {last_run['tick']}"
    if last_run.get("position"):
        pos = last_run["position"]
        location += f" near ({pos['x']}, {pos['y']})"
    text = f"Last run: {last_run.get('outcome') or 'unknown'}{location}."
    attempts = last_run.get("failed_attempts") or []
    if attempts:
        attempt = attempts[0]
        object_label = ""
        if attempt.get("object_id") is not None:
            object_label = f" object {attempt['object_id']}"
        if attempt.get("target_name"):
            object_label += f" ({attempt['target_name']})"
        text += f" Last failed action: {attempt.get('type')}{object_label} -> {attempt.get('result')}."
    return text


def _last_run_summary(
    run: TestRun,
    latest_event: GameEvent | None,
    failed_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": str(run.id),
        "outcome": run.outcome,
        "behavior_profile": run.behavior_profile,
        "failed_attempts": failed_attempts,
    }
    if latest_event is not None:
        summary["tick"] = latest_event.tick_number
        summary["position"] = {
            "x": round(float(latest_event.player_x), 1),
            "y": round(float(latest_event.player_y), 1),
        }
    return summary


def _decision_attempt(decision: AgentDecision) -> dict[str, Any] | None:
    stop_reason = decision.mcp_stop_reason
    output = decision.mcp_output if isinstance(decision.mcp_output, dict) else {}
    action_summary = output.get("action_summary") if isinstance(output.get("action_summary"), dict) else {}
    stop_reason = stop_reason or action_summary.get("stop_reason")
    if stop_reason not in FAILED_STOP_REASONS:
        return None
    mcp_input = decision.mcp_input if isinstance(decision.mcp_input, dict) else {}
    return {
        "type": decision.mcp_tool,
        "object_id": mcp_input.get("object_id"),
        "target_name": action_summary.get("target_name"),
        "stop_reason": stop_reason,
        "result": _interaction_result(str(stop_reason)),
    }


def _interaction_result(stop_reason: str) -> str:
    if stop_reason in {"arrival_blocked", "stuck"}:
        return "blocked_by_collision"
    if stop_reason in {"pickup_not_collected", "target_lost", "max_tics", "enemy_nearby"}:
        return "unreachable_or_interrupted"
    if stop_reason == "target_not_visible":
        return "target_not_visible"
    if stop_reason == "out_of_ammo":
        return "out_of_ammo"
    return stop_reason or "unknown"


def _similar_text(a: str, b: str) -> bool:
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return a == b
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b)) >= 0.4


def _is_persistable_hypothesis(text: str) -> bool:
    lower = text.lower().strip()
    if len(lower) < 20:
        return False
    speculative_markers = (
        "appears",
        "maybe",
        "possibly",
        "likely",
        "seems",
        "unclear",
        "hypothesis",
        "switching",
        "clearing",
        "recent combat",
        "already returned",
        "red-textured",
        "red textured",
    )
    if any(marker in lower for marker in speculative_markers):
        return False
    confirmed_markers = (
        "confirmed",
        "observed issue",
        "defect",
        "blocked after",
        "unreachable after",
        "does not respond after use",
        "no usable attack ammo",
        "ammo starvation",
        "softlock",
    )
    return any(marker in lower for marker in confirmed_markers)


def _infer_tag(text: str) -> str:
    lower = text.lower()
    if "blocked" in lower or "collision" in lower or "unreachable" in lower:
        return "BLOCKED_PATH"
    if "key" in lower:
        return "KEY_LOCATION"
    if "ammo" in lower or "starvation" in lower or "resource" in lower:
        return "RESOURCE_CACHE"
    if (
        "visual" in lower
        or "glitch" in lower
        or "missing texture" in lower
        or "misaligned texture" in lower
        or "hall of mirrors" in lower
        or "hom effect" in lower
    ):
        return "VISUAL_GLITCH"
    if "encounter" in lower or "combat" in lower or "monster" in lower:
        return "ENCOUNTER_HOTSPOT"
    if "navigation" in lower or "path" in lower or "door" in lower:
        return "NAVIGATION_GAP"
    return "NAVIGATION_GAP"
