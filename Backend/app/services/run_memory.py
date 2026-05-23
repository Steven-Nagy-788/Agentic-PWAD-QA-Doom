from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentDecision, Defect, GameEvent, TestRun


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
            or "ammo" in (defect.title or "").lower()
            or "ammo" in (defect.description or "").lower()
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
