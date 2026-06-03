from __future__ import annotations

import base64
import contextlib
import json
import logging
import math
import re
import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.core.database import engine
from app.models import AgentDecision, AgentPositionTrail, Defect, GameEvent, StaticAnalysisResult, TestReport, TestRun, WadFile
from app.repositories.defect_repository import DefectRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.run_repository import RunRepository
from app.services.analysis_service import map_bounds_for_wad, selected_skill_spawn_summary
from app.services.analysis_constants import CELL_SIZE


logger = logging.getLogger(__name__)


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = ReportRepository(db)

    async def generate(self, run_id: UUID) -> TestReport:
        lock_key = f"report:{run_id}"
        async with engine.connect() as raw_lock_connection:
            lock_connection = await raw_lock_connection.execution_options(isolation_level="AUTOCOMMIT")
            acquired = await lock_connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                {"key": lock_key},
            )
            if not acquired:
                existing = await self.repo.get_by_run(run_id)
                if existing is not None and existing.pdf_path:
                    return existing
                raise RuntimeError("Report generation is already in progress by another request")
            try:
                return await self._generate_locked(run_id)
            except Exception as exc:
                logger.warning("Report generation failed for run %s: %s", run_id, exc)
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                    await self.mark_error(run_id, str(exc))
                    await self.db.commit()
                raise
            finally:
                with contextlib.suppress(Exception):
                    await lock_connection.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:key))"),
                        {"key": lock_key},
                    )

    async def _generate_locked(self, run_id: UUID) -> TestReport:
        existing = await self.repo.get_by_run(run_id)
        if existing is not None and existing.generation_status == "complete" and existing.pdf_path:
            if Path(self.settings.report_storage_dir.parent, existing.pdf_path).exists():
                return existing
        if existing is not None:
            await self.repo.update(existing, generation_status="generating", generation_error=None)
        else:
            existing = await self.repo.create(TestReport(run_id=run_id, generation_status="generating"))
        run = await self.db.get(TestRun, run_id)
        if run is None:
            raise ValueError("Run not found")
        analysis = await self.db.get(StaticAnalysisResult, run.static_analysis_id) if run.static_analysis_id else None
        map_bounds = await self._map_bounds_for_report(run, analysis)
        defects = await DefectRepository(self.db).list_by_run(run_id)
        events = list(
            (
                await self.db.execute(
                    select(GameEvent).where(GameEvent.run_id == run_id).order_by(GameEvent.tick_number, GameEvent.id)
                )
            )
            .scalars()
            .all()
        )
        positions = list(
            (
                await self.db.execute(
                    select(AgentPositionTrail)
                    .where(AgentPositionTrail.run_id == run_id)
                    .where(AgentPositionTrail.is_sentinel.is_(False))
                    .order_by(AgentPositionTrail.tick_number, AgentPositionTrail.id)
                )
            )
            .scalars()
            .all()
        )
        decisions = list(
            (
                await self.db.execute(
                    select(AgentDecision)
                    .where(AgentDecision.run_id == run_id)
                    .order_by(AgentDecision.sequence_number)
                )
            )
            .scalars()
            .all()
        )
        notable = [event for event in events if event.event_type != "normal"][:20]
        payload = {
            "run": run,
            "analysis": analysis,
            "defects": defects,
            "events": events,
            "decisions": decisions,
            "notable_events": notable,
            "first_ticks": list(events[:5]),
            "last_ticks": list(events[-5:]),
            "position_trail": positions,
            "map_bounds": map_bounds,
            "metrics": self._build_metrics(run, analysis, events, positions, decisions),
        }
        await self.db.commit()
        report_json = await self._call_gemini_or_fallback(payload)
        render_report = self._sanitize_report_voice(self._normalize_report_sections(report_json))
        pdf_path = await self._render_pdf_with_timeout(run_id, render_report, payload)
        fields = self._report_fields(run, render_report, pdf_path)
        created = await self.repo.update(existing, **fields)
        await RunRepository(self.db).update(run, report_pdf_path=str(pdf_path))
        await self.db.commit()
        return created

    async def _render_pdf_with_timeout(
        self,
        run_id: UUID,
        report: dict[str, Any],
        payload: dict[str, Any],
    ) -> Path:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._render_pdf, run_id, report, payload),
                timeout=max(0.1, self.settings.report_pdf_timeout_seconds),
            )
        except asyncio.TimeoutError:
            logger.warning("PDF rendering timed out for run %s", run_id)
            raise RuntimeError("PDF rendering timed out") from None
        except Exception as exc:
            logger.warning("PDF rendering failed for run %s: %s", run_id, exc)
            raise

    async def mark_error(self, run_id: UUID, error: str) -> TestReport:
        existing = await self.repo.get_by_run(run_id)
        fields = {
            "generation_status": "error",
            "generation_error": error,
            "pdf_path": None,
        }
        if existing is not None:
            return await self.repo.update(existing, **fields)
        return await self.repo.create(TestReport(run_id=run_id, **fields))

    async def _map_bounds_for_report(
        self,
        run: TestRun,
        analysis: StaticAnalysisResult | None,
    ) -> dict[str, int] | None:
        bounds = self._analysis_map_bounds(analysis)
        if bounds:
            return bounds
        wad = await self.db.get(WadFile, run.wad_file_id)
        if wad is None:
            return None
        try:
            return await asyncio.to_thread(map_bounds_for_wad, wad.stored_path, run.map_name)
        except Exception:
            return None

    @staticmethod
    def _report_fields(run: TestRun, report_json: dict, pdf_path: Path) -> dict:
        def text_value(key: str) -> str | None:
            return ReportService._coerce_text(report_json.get(key))

        def json_value(key: str) -> Any:
            return report_json.get(key)

        pdf_path_str = str(pdf_path.relative_to(get_settings().report_storage_dir.parent)) if pdf_path.is_absolute() else str(pdf_path)

        return {
            "generation_status": "complete",
            "generation_error": None,
            "report_purpose": text_value("report_purpose"),
            "intended_audience": text_value("intended_audience") or "Game developers and QA engineers",
            "problem_and_escalation": text_value("problem_and_escalation"),
            "test_items_summary": text_value("test_items_summary"),
            "test_environment_summary": text_value("test_environment_summary"),
            "hardware_spec": ReportService._coerce_json_object(json_value("hardware_spec")),
            "software_spec": ReportService._coerce_json_object(json_value("software_spec")),
            "variances_from_plan": text_value("variances_from_plan"),
            "test_procedure_variances": text_value("test_procedure_variances"),
            "test_case_variances": text_value("test_case_variances"),
            "test_coverage_evaluation": text_value("test_coverage_evaluation"),
            "objectives_planned": ReportService._normalize_objective_list(
                json_value("objectives_planned"), default_detail_key="status"
            ),
            "objectives_covered": ReportService._normalize_objective_list(
                json_value("objectives_covered"), default_detail_key="evidence"
            ),
            "objectives_omitted": ReportService._normalize_objective_list(
                json_value("objectives_omitted"), default_detail_key="reason"
            ),
            "uncovered_attributes": text_value("uncovered_attributes"),
            "test_process_changes": text_value("test_process_changes"),
            "defect_summary_narrative": text_value("defect_summary_narrative"),
            "defect_patterns": text_value("defect_patterns"),
            "test_item_limitations": text_value("test_item_limitations"),
            "dropped_features": text_value("dropped_features"),
            "pass_fail_summary": ReportService._coerce_json_object(json_value("pass_fail_summary")),
            "risk_areas": ReportService._normalize_named_list(json_value("risk_areas"), "area", "risk"),
            "good_quality_areas": ReportService._normalize_named_list(
                json_value("good_quality_areas"), "area", "evidence"
            ),
            "major_activities_summary": text_value("major_activities_summary"),
            "activity_variances": text_value("activity_variances"),
            "elapsed_time_seconds": report_json.get("elapsed_time_seconds") or run.duration_seconds,
            "total_actions_taken": report_json.get("total_actions_taken") or run.total_actions_taken,
            "report_model": ReportService._coerce_text(report_json.get("_report_model")),
            "pdf_path": pdf_path_str,
        }

    @staticmethod
    def _normalize_report_sections(report_json: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(report_json)
        normalized["objectives_planned"] = ReportService._normalize_objective_list(
            normalized.get("objectives_planned"), default_detail_key="status"
        )
        normalized["objectives_covered"] = ReportService._normalize_objective_list(
            normalized.get("objectives_covered"), default_detail_key="evidence"
        )
        normalized["objectives_omitted"] = ReportService._normalize_objective_list(
            normalized.get("objectives_omitted"), default_detail_key="reason"
        )
        normalized["risk_areas"] = ReportService._normalize_named_list(normalized.get("risk_areas"), "area", "risk")
        normalized["good_quality_areas"] = ReportService._normalize_named_list(
            normalized.get("good_quality_areas"), "area", "evidence"
        )
        return normalized

    @staticmethod
    def _sanitize_report_voice(value: Any) -> Any:
        long_first_replacements = [
            (r"\b[Tt]he automated playthrough was unable to\b", "the automated playthrough did not"),
            (r"\b[Aa]utomated playthrough was unable to\b", "automated playthrough did not"),
            (r"\b[Tt]he agent was unable to\b", "the automated playthrough did not"),
            (r"\b[Aa]gent was unable to\b", "automated playthrough did not"),
            (r"\b[Tt]he agent failed to\b", "the automated playthrough did not"),
            (r"\b[Aa]gent failed to\b", "automated playthrough did not"),
            (r"\b[Tt]he agent could not\b", "the automated playthrough did not"),
            (r"\b[Aa]gent could not\b", "automated playthrough did not"),
            (r"\b[Tt]he agent did not\b", "the automated playthrough did not"),
            (r"\b[Aa]gent did not\b", "automated playthrough did not"),
        ]
        catch_all_replacements = [
            (r"\bAgent\b", "Automated playthrough"),
            (r"\bagent\b", "automated playthrough"),
        ]
        if isinstance(value, str):
            result = value
            for source, target in long_first_replacements:
                result = re.sub(source, target, result)
            doubled = False
            if "automated automated" in result.lower():
                doubled = True
                result = re.sub(r"\b[Aa]utomated\s+[Aa]utomated playthrough\b", "Automated playthrough", result)
            for source, target in catch_all_replacements:
                result = re.sub(source, target, result)
            if doubled:
                result = re.sub(r"\b[Aa]utomated\s+[Aa]utomated playthrough\b", "Automated playthrough", result)
            if result.startswith("the automated"):
                result = "T" + result[1:]
            return result
        if isinstance(value, list):
            return [ReportService._sanitize_report_voice(item) for item in value]
        if isinstance(value, dict):
            return {key: ReportService._sanitize_report_voice(item) for key, item in value.items()}
        return value

    @staticmethod
    def _coerce_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(
                f"- {ReportService._coerce_text(item) or ''}".strip()
                for item in value
                if item not in (None, "")
            )
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        return str(value)

    @staticmethod
    def _coerce_json_object(value: Any) -> dict[str, Any] | None:
        if value in (None, ""):
            return None
        if isinstance(value, dict):
            return value
        return {"value": value}

    @staticmethod
    def _coerce_json_value(value: Any) -> list[Any] | dict[str, Any] | None:
        if value in (None, ""):
            return None
        if isinstance(value, (list, dict)):
            return value
        return [{"value": value}]

    @staticmethod
    def _normalize_objective_list(value: Any, default_detail_key: str) -> list[dict[str, Any]] | None:
        raw = ReportService._coerce_json_value(value)
        if raw in (None, {}, []):
            return None
        items = raw if isinstance(raw, list) else [raw]
        normalized: list[dict[str, Any]] = []
        for item in items:
            if item in (None, "", {}, []):
                continue
            if isinstance(item, str):
                objective, detail = ReportService._split_label_detail(item)
                entry: dict[str, Any] = {"objective": objective}
                if detail:
                    entry[default_detail_key] = detail
                normalized.append(entry)
                continue
            if isinstance(item, dict):
                objective = (
                    item.get("objective")
                    or item.get("name")
                    or item.get("item")
                    or item.get("value")
                    or item.get("title")
                )
                if not objective:
                    continue
                entry = dict(item)
                entry["objective"] = str(objective)
                normalized.append(entry)
        return normalized or None

    @staticmethod
    def _normalize_named_list(value: Any, label_key: str, default_detail_key: str) -> list[dict[str, Any]] | None:
        raw = ReportService._coerce_json_value(value)
        if raw in (None, {}, []):
            return None
        items = raw if isinstance(raw, list) else [raw]
        normalized: list[dict[str, Any]] = []
        for item in items:
            if item in (None, "", {}, []):
                continue
            if isinstance(item, str):
                label, detail = ReportService._split_label_detail(item)
                entry: dict[str, Any] = {label_key: label}
                if detail:
                    entry[default_detail_key] = detail
                normalized.append(entry)
                continue
            if isinstance(item, dict):
                label = item.get(label_key) or item.get("area") or item.get("name") or item.get("value")
                if not label:
                    continue
                entry = dict(item)
                entry[label_key] = str(label)
                normalized.append(entry)
        return normalized or None

    @staticmethod
    def _split_label_detail(value: str) -> tuple[str, str | None]:
        for delimiter in (" \u2014 ", " - ", ": "):
            if delimiter in value:
                left, right = value.split(delimiter, 1)
                return left.strip(), right.strip() or None
        return value.strip(), None

    @staticmethod
    def _build_metrics(
        run: TestRun,
        analysis: StaticAnalysisResult | None,
        events: list[GameEvent],
        positions: list[AgentPositionTrail],
        decisions: list[AgentDecision] | None = None,
    ) -> dict[str, Any]:
        event_type_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        decision_source_counts: dict[str, int] = {}
        for event in events:
            event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1
            action = event.action_taken or {}
            tool = action.get("mcp_tool") or "unknown"
            action_counts[tool] = action_counts.get(tool, 0) + 1

        movement_distance = 0.0
        clusters: set[tuple[int, int]] = set()
        previous: AgentPositionTrail | None = None
        for position in positions:
            clusters.add((round(position.x / CELL_SIZE), round(position.y / CELL_SIZE)))
            if previous is not None:
                movement_distance += math.hypot(position.x - previous.x, position.y - previous.y)
            previous = position

        first_position = positions[0] if positions else None
        last_position = positions[-1] if positions else None
        skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
        progress_metrics = run.progress_metrics or {}
        raw_enemy_count = int(analysis.thing_count_enemies or 0) if analysis else 0
        spawned_enemy_count = int(skill_summary.get("thing_count_enemies") or 0)
        raw_item_count = int(analysis.thing_count_items or 0) if analysis else 0
        spawned_item_count = int(skill_summary.get("thing_count_items") or 0)
        for decision in decisions or []:
            source = str(decision.decision_source or "gemini")
            decision_source_counts[source] = decision_source_counts.get(source, 0) + 1
        return {
            "event_count": len(events),
            "decision_count": len(decisions or []),
            "position_sample_count": len(positions),
            "position_cluster_count": len(clusters),
            "movement_distance_units": round(movement_distance, 1),
            "event_type_counts": event_type_counts,
            "action_counts": action_counts,
            "decision_source_counts": decision_source_counts,
            "fallback_action_count": decision_source_counts.get("deterministic_fallback", 0),
            "validation_rejection_count": sum(
                1 for decision in decisions or [] if decision.mcp_stop_reason == "invalid_params"
            ),
            "difficulty_level": run.difficulty_level,
            "raw_enemy_count": raw_enemy_count,
            "spawned_enemy_count": spawned_enemy_count,
            "hidden_enemy_count": max(raw_enemy_count - spawned_enemy_count, 0),
            "raw_item_count": raw_item_count,
            "spawned_item_count": spawned_item_count,
            "hidden_item_count": max(raw_item_count - spawned_item_count, 0),
            "selected_skill_summary": skill_summary,
            "notable_event_count": sum(1 for event in events if event.event_type != "normal"),
            "tick_start": events[0].tick_number if events else None,
            "tick_end": events[-1].tick_number if events else None,
            "position_tick_start": first_position.tick_number if first_position else None,
            "position_tick_end": last_position.tick_number if last_position else None,
            "first_position": ReportService._position_snapshot(first_position),
            "last_position": ReportService._position_snapshot(last_position),
            "min_health": min((event.health for event in events), default=run.final_hp),
            "max_kills": max((event.kill_count for event in events), default=run.total_kills),
            "max_items": max((event.item_count for event in events), default=run.total_items_collected),
            "max_secrets": max((event.secret_count for event in events), default=run.secrets_found),
            "secret_sector_count": analysis.secret_sector_count if analysis else None,
            "recording_mp4_url": f"/runs/{run.id}/recording" if (run.recording_mp4_path or (run.recording_metadata or {}).get("quality_status") == "ok") else None,
            "report_pdf_url": f"/runs/{run.id}/report/pdf" if run.report_pdf_path else None,
            "recording_metadata": run.recording_metadata or {},
            "progress_metrics": progress_metrics,
            "coverage_percent": progress_metrics.get("coverage_percent"),
            "agent_quality_flags": run.agent_quality_flags or {},
            "recording_file_size_bytes": ReportService._safe_file_size(run.recording_mp4_path) or ReportService._safe_file_size((run.recording_metadata or {}).get("path")),
        }

    @staticmethod
    def _safe_file_size(path_str: str | None) -> int | None:
        if not path_str:
            return None
        try:
            return Path(path_str).stat().st_size
        except OSError:
            return None

    async def _call_gemini_or_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback_report(payload)
        fallback["_report_model"] = "deterministic-grounded-template"
        return fallback

    @staticmethod
    def _merge_report_defaults(defaults: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
        # Model prose is not evidence. Keep deterministic fields authoritative
        # until a claim-level grounding validator exists.
        return dict(defaults)

    @staticmethod
    def _fallback_report(payload: dict[str, Any]) -> dict[str, Any]:
        run: TestRun = payload["run"]
        analysis: StaticAnalysisResult | None = payload["analysis"]
        all_defects: list[Defect] = payload["defects"]
        defects = [defect for defect in all_defects if defect.resolution_status != "candidate"]
        candidate_count = len(all_defects) - len(defects)
        metrics: dict[str, Any] = payload["metrics"]
        if ReportService._is_pwad_crash(run):
            return ReportService._pwad_crash_report(payload)
        outcome = ReportService._display_outcome(run, defects)
        passed = run.status == "completed" and run.outcome == "map_completed"
        outcome_sentence = "The map was completed." if passed else f"The run ended with outcome '{outcome}'."
        defect_phrase = "No confirmed defects were detected." if not defects else f"{len(defects)} confirmed defect(s) were detected."
        if candidate_count:
            defect_phrase += f" {candidate_count} candidate signal(s) require review."
        coverage_phrase = (
            f"The automated playthrough recorded {metrics['event_count']} gameplay event(s), "
            f"{metrics.get('decision_count', 0)} lockstep LLM/MCP decision(s), "
            f"{metrics['position_sample_count']} movement samples, "
            f"{metrics['position_cluster_count']} position cluster(s), and "
            f"{metrics['movement_distance_units']} map units of movement."
        )
        analysis_phrase = ReportService._analysis_phrase(analysis)
        skill_summary = metrics.get("selected_skill_summary") or {}
        spawned_enemies = int(metrics.get("spawned_enemy_count") or 0)
        raw_enemies = int(metrics.get("raw_enemy_count") or 0)
        hidden_enemies = int(metrics.get("hidden_enemy_count") or 0)
        health_ratio = float(skill_summary.get("health_ratio") or 0)
        ammo_ratio = float(skill_summary.get("ammo_ratio") or 0)
        kill_ratio = (run.total_kills or 0) / spawned_enemies if spawned_enemies else 1.0
        map_navigation_pass = passed
        combat_pass = spawned_enemies == 0 or ((run.total_kills or 0) > 0 and kill_ratio >= 0.5)
        resource_pass = spawned_enemies == 0 or (health_ratio >= 0.15 and ammo_ratio >= 0.8 and not any(
            defect.defect_type in {"ammo_starvation", "health_deficit"} for defect in defects
        ))
        coverage_percent = float(metrics.get("coverage_percent") or 0)
        if analysis and analysis.secret_sector_count == 0:
            secret_status = "PASS"
        elif (run.secrets_found or 0) > 0:
            secret_status = "PASS"
        elif coverage_percent >= 60:
            secret_status = "FAIL"
        else:
            secret_status = "LIMITED"
        secret_pass = secret_status == "PASS"
        overall_verdict = (
            "PASS"
            if all([map_navigation_pass, combat_pass, resource_pass, secret_pass])
            else "PARTIAL"
            if map_navigation_pass
            else "FAIL"
        )
        major_risk = ReportService._major_risk(run, defects, metrics)
        spawn_note = (
            f" Raw static analysis found {raw_enemies} enemies, but {hidden_enemies} are disabled at "
            f"difficulty {run.difficulty_level} by skill flags."
            if hidden_enemies
            else ""
        )
        recording_meta = metrics.get("recording_metadata") or {}
        progress_metrics = metrics.get("progress_metrics") or {}
        quality_flags = metrics.get("agent_quality_flags") or {}
        environment = ReportService._factual_environment_fields(run)
        recording_note = (
            f" Recording quality status: {recording_meta.get('quality_status', 'unknown')}; "
            f"{recording_meta.get('frame_count', 0)} frames, "
            f"{recording_meta.get('unique_frame_count', 0)} unique frames, "
            f"{recording_meta.get('duration_seconds', 0)} recording seconds at {recording_meta.get('fps', 'unknown')} FPS. "
            f"Wall-clock run duration was {run.duration_seconds or 0} seconds; "
            f"gameplay advanced {recording_meta.get('advanced_game_ticks', 'unknown')} tics."
        )
        progress_note = (
            f" Agent progress score: {progress_metrics.get('progress_score', 0)} with "
            f"{progress_metrics.get('meaningful_progress_events', 0)} meaningful progress event(s). "
            f"Quality flags: {quality_flags.get('quality_status', 'unknown')}."
        )
        runtime_warnings = [str(item) for item in quality_flags.get("warnings", [])]
        variance_summary = (
            "The run finished inside the requested tick budget."
            if run.status == "completed"
            else f"The run did not complete normally: {run.error_message or outcome}."
        )
        if runtime_warnings:
            variance_summary += " Runtime warnings: " + "; ".join(runtime_warnings)
        variance_summary += (
            f" Deterministic fallback actions: {metrics.get('fallback_action_count', 0)}."
            f" Validation rejections: {metrics.get('validation_rejection_count', 0)}."
        )

        return {
            "report_purpose": (
                "Document the automated PWAD QA run, combine static map analysis with live play telemetry, "
                "and give map authors concrete evidence about completion, traversal, combat, and defects. "
                f"The selected-difficulty gameplay evidence uses {spawned_enemies} spawned enemy/enemies.{spawn_note}"
            ),
            "intended_audience": "Doom PWAD authors, level designers, QA engineers, and release owners.",
            "problem_and_escalation": ReportService._problem_statement(run, defects, metrics),
            "test_items_summary": (
                f"Test item: {run.map_name} from WAD {run.wad_file_id}. "
                f"Static analysis context: {analysis_phrase} At difficulty {run.difficulty_level}, "
                f"{spawned_enemies} of {raw_enemies} raw enemies spawn."
            ),
            "test_environment_summary": environment["summary"],
            "hardware_spec": environment["hardware"],
            "software_spec": environment["software"],
            "variances_from_plan": variance_summary,
            "test_procedure_variances": (
                "No manual gameplay intervention was used. The report reflects lockstep LLM tool decisions and MCP telemetry."
            ),
            "test_case_variances": (
                "Coverage depth depends on available run time, lockstep tool decisions, and whether the map exposes progression cues."
            ),
            "test_coverage_evaluation": (
                f"{coverage_phrase} {outcome_sentence} Combat coverage is evaluated against {spawned_enemies} "
                f"enemy/enemies that spawn at difficulty {run.difficulty_level}, not against hidden raw THINGS."
                f"{recording_note} {progress_note}"
            ),
            "objectives_planned": [
                {"objective": "Validate the map starts correctly in single-player QA mode.", "status": "planned"},
                {"objective": "Exercise live traversal and combat using static analysis as runtime context.", "status": "planned"},
                {"objective": "Capture gameplay video, position history, events, defects, and a PDF report.", "status": "planned"},
            ],
            "objectives_covered": ReportService._covered_objectives(run, metrics),
            "objectives_omitted": ReportService._omitted_objectives(run, metrics, outcome),
            "uncovered_attributes": ReportService._uncovered_attributes(run, metrics),
            "test_process_changes": (
                "Lockstep MCP actions return per-action telemetry frames so movement, position trail, and recording "
                "coverage are sampled during bounded tool execution, while the game remains paused during LLM selection. "
                "The PDF keeps detailed evidence in a landscape appendix so long decision tables do not clip."
            ),
            "defect_summary_narrative": f"{defect_phrase} {major_risk}",
            "defect_patterns": ReportService._defect_patterns(defects),
            "test_item_limitations": ReportService._test_limitations(run, metrics),
            "dropped_features": "None.",
            "pass_fail_summary": {
                "map_navigation": "PASS" if map_navigation_pass else "FAIL",
                "combat_engagement": "PASS" if combat_pass else "FAIL",
                "resource_balance": "PASS" if resource_pass else "FAIL",
                "secret_coverage": secret_status,
                "overall_verdict": overall_verdict,
                "navigation_rationale": (
                    "The map exit was reached."
                    if passed
                    else (
                        f"The run ended with outcome '{outcome}' after visiting "
                        f"{metrics['position_cluster_count']} coarse position cluster(s)."
                    )
                ),
                "combat_rationale": (
                    f"{run.total_kills or 0} kill(s) recorded against {spawned_enemies} enemy/enemies that spawn "
                    f"at difficulty {run.difficulty_level}."
                ),
                "resource_rationale": (
                    f"Selected-difficulty health_ratio={health_ratio:.4f}, ammo_ratio={ammo_ratio:.4f}."
                ),
                "secret_rationale": (
                    "No secret sectors exist in static analysis."
                    if analysis and analysis.secret_sector_count == 0
                    else (
                        f"{run.secrets_found or 0} secret(s) found."
                        if (run.secrets_found or 0) > 0
                        else (
                            f"0 secrets found after {coverage_percent:.1f}% coarse cell coverage."
                            if coverage_percent >= 60
                            else f"0 secrets found, but only {coverage_percent:.1f}% coarse cell coverage was achieved."
                        )
                    )
                ),
            },
            "risk_areas": ReportService._risk_areas(run, defects, metrics),
            "good_quality_areas": ReportService._good_quality_areas(run, metrics, analysis),
            "major_activities_summary": (
                f"The pipeline statically analyzed the map, launched a ViZDoom MCP session, executed "
                f"{run.total_actions_taken or metrics['event_count']} lockstep MCP action(s), collected event and position "
                "telemetry, finalized recording artifacts, detected defects, and generated this report."
            ),
            "activity_variances": (
                "Run data is sparse or quality flags are present; treat gameplay conclusions as preliminary."
                if metrics["event_count"] < 3 or (quality_flags.get("warnings") or [])
                else "Run data includes multiple gameplay samples and can support concrete QA conclusions."
            ),
            "elapsed_time_seconds": run.duration_seconds,
            "total_actions_taken": run.total_actions_taken,
            # ---- 14-section professional QA report fields ----
            "executive_summary": ReportService._build_executive_summary(run, defects, metrics, analysis, outcome, overall_verdict),
            "critical_issues": ReportService._build_critical_issues(defects, run),
            "geometry_technical_analysis": ReportService._build_geometry_analysis(analysis, run),
            "gameplay_flow_analysis": ReportService._build_gameplay_flow(run, metrics, analysis),
            "combat_design_review": ReportService._build_combat_review(run, metrics, analysis, defects),
            "itemization_audit": ReportService._build_itemization_audit(run, metrics, analysis, defects),
            "ai_enemy_behavior": ReportService._build_ai_behavior(run, metrics, defects),
            "navigation_readability": ReportService._build_navigation_readability(run, metrics, analysis),
            "secrets_optional_content": ReportService._build_secrets_analysis(run, metrics, analysis),
            "multiplayer_analysis": "Not applicable. This QA run tested single-player mode only.",
            "performance_engine_compliance": ReportService._build_performance_analysis(analysis, run),
            "speedrunning_advanced_play": ReportService._build_speedrunning_analysis(run, metrics, analysis),
            "recommendations": ReportService._build_recommendations(run, defects, metrics, analysis),
            "final_verdict": ReportService._build_final_verdict(run, defects, metrics, analysis, overall_verdict),
        }

    @staticmethod
    def _is_pwad_crash(run: TestRun) -> bool:
        return run.failure_category == "pwad_crash" or run.outcome == "pwad_crash"

    @staticmethod
    def _factual_environment_fields(run: TestRun) -> dict[str, Any]:
        metadata = run.environment_metadata if isinstance(getattr(run, "environment_metadata", None), dict) else {}
        hardware = metadata.get("hardware") if isinstance(metadata.get("hardware"), dict) else {}
        software = metadata.get("software") if isinstance(metadata.get("software"), dict) else {}
        run_context = metadata.get("run") if isinstance(metadata.get("run"), dict) else {}
        factual_hardware = {
            "cpu": hardware.get("cpu", "not reported"),
            "ram_gb": hardware.get("ram_gb", "not reported"),
            "os": hardware.get("os", "not reported"),
        }
        factual_software = {
            "backend_python": software.get("backend_python", "not reported"),
            "fastapi": software.get("fastapi", "not reported"),
            "weasyprint": software.get("weasyprint", "not reported"),
            "ffmpeg": software.get("ffmpeg", "not reported"),
            "mcp_python": software.get("mcp_python", "not reported"),
            "fastmcp": software.get("fastmcp", "not reported"),
            "vizdoom": software.get("vizdoom", "not reported"),
            "doom_mcp": software.get("doom_mcp", "not reported"),
            "agent_model": run_context.get("llm_model", run.llm_model),
        }
        return {
            "summary": (
                f"The run used IWAD {run_context.get('iwad', run.iwad_used)}, "
                f"difficulty {run_context.get('difficulty', run.difficulty_level)}, "
                f"model {run_context.get('llm_model', run.llm_model)}, and a maximum budget of "
                f"{run_context.get('max_ticks', run.max_ticks)} game ticks. "
                "Environment versions below are measured values or explicitly marked not reported. "
                "Duration values distinguish wall-clock orchestration time from recorded gameplay time."
            ),
            "hardware": factual_hardware,
            "software": factual_software,
        }

    @staticmethod
    def _pwad_crash_report(payload: dict[str, Any]) -> dict[str, Any]:
        run: TestRun = payload["run"]
        analysis: StaticAnalysisResult | None = payload["analysis"]
        defects: list[Defect] = payload["defects"]
        metrics: dict[str, Any] = payload["metrics"]
        analysis_phrase = ReportService._analysis_phrase(analysis)
        diagnostic = run.error_message or run.failure_summary or "No raw runtime error was stored."
        environment = ReportService._factual_environment_fields(run)
        return {
            "report_purpose": (
                "Document that the PWAD crashed or failed to initialize under the configured "
                "ViZDoom/Freedoom test environment. This is a valid QA outcome: the product captured "
                "the failure as structured run, defect, and report evidence instead of dropping the test."
            ),
            "intended_audience": "Doom PWAD authors, level designers, QA engineers, and release owners.",
            "problem_and_escalation": (
                run.failure_summary
                or "The map could not be initialized by the configured test runtime."
            ),
            "test_items_summary": (
                f"Test item: {run.map_name} from WAD {run.wad_file_id}. "
                f"Static analysis context: {analysis_phrase}"
            ),
            "test_environment_summary": (
                f"{environment['summary']} Failure stage: {run.failure_stage or 'runtime initialization'}."
            ),
            "hardware_spec": environment["hardware"],
            "software_spec": environment["software"],
            "variances_from_plan": "Gameplay did not start because the PWAD crashed or failed runtime initialization.",
            "test_procedure_variances": (
                "No manual intervention was used. Trace, event, and recording endpoints remain valid even when empty."
            ),
            "test_case_variances": "Gameplay coverage is intentionally absent because the runtime never reached playable state.",
            "test_coverage_evaluation": (
                "Coverage is limited to upload, static analysis if available, runtime launch/preflight, error capture, "
                "defect creation, and report generation. No combat, traversal, item, or secret conclusions should be drawn."
            ),
            "objectives_planned": [
                {"objective": "Validate the map can initialize in the configured runtime.", "status": "planned"},
                {"objective": "Capture structured failure evidence if initialization fails.", "status": "planned"},
                {"objective": "Return valid run/report/defect endpoint payloads.", "status": "planned"},
            ],
            "objectives_covered": [
                {"objective": "Runtime failure capture", "evidence": diagnostic},
                {"objective": "Report artifact", "evidence": "A crash report JSON/PDF was generated."},
                {"objective": "Defect payload", "evidence": f"{len(defects)} defect(s) attached to the run."},
            ],
            "objectives_omitted": [
                {"objective": "Gameplay traversal", "reason": "The PWAD did not initialize into a playable episode."},
                {"objective": "Combat/resource coverage", "reason": "No gameplay state was available after startup failure."},
                {"objective": "Video artifact", "reason": "No recording is expected when gameplay never initializes."},
            ],
            "uncovered_attributes": "Traversal, combat, resource balance, secrets, and progression were not exercised.",
            "test_process_changes": (
                "Crash runs are converted into first-class QA reports with structured failure fields and endpoint evidence."
            ),
            "defect_summary_narrative": (
                "A PWAD crash/initialization defect was recorded. Review the raw diagnostic and validate required IWAD, "
                "map markers, resources, and compatibility settings."
            ),
            "defect_patterns": ReportService._defect_patterns(defects),
            "test_item_limitations": (
                "This report does not judge map balance or playability beyond runtime initialization. "
                "A successful runtime launch is required before gameplay quality can be evaluated."
            ),
            "dropped_features": "None.",
            "pass_fail_summary": {
                "map_navigation": "FAIL",
                "combat_engagement": "LIMITED",
                "resource_balance": "LIMITED",
                "secret_coverage": "LIMITED",
                "overall_verdict": "FAIL",
                "navigation_rationale": "The map did not initialize into a playable episode.",
                "combat_rationale": "No spawned combat state was available.",
                "resource_rationale": "Resource balance cannot be evaluated before runtime initialization.",
                "secret_rationale": "Secret coverage cannot be evaluated before runtime initialization.",
            },
            "risk_areas": [
                {"area": "Runtime compatibility", "risk": diagnostic},
                {"area": "Release readiness", "risk": "Players may be unable to launch this PWAD in the tested setup."},
            ],
            "good_quality_areas": [
                {"area": "Failure evidence", "evidence": "The backend preserved the crash as structured QA output."},
                {"area": "Static context", "evidence": "Static map analysis is included when available."},
            ],
            "major_activities_summary": (
                f"The backend validated the run request, attempted to launch {run.map_name}, captured the runtime failure, "
                "stored a defect, and generated this crash report."
            ),
            "activity_variances": (
                f"Trace events: {metrics['event_count']}. Position samples: {metrics['position_sample_count']}. "
                "Zero gameplay samples are expected for startup crashes."
            ),
            "elapsed_time_seconds": run.duration_seconds,
            "total_actions_taken": run.total_actions_taken or 0,
        }

    @staticmethod
    def _analysis_phrase(analysis: StaticAnalysisResult | None) -> str:
        if analysis is None:
            return "static analysis was unavailable."
        return (
            f"{analysis.thing_count_total} things, {analysis.thing_count_enemies} enemies, "
            f"{analysis.thing_count_items} items, {analysis.thing_count_keys} keys, "
            f"{analysis.secret_sector_count} secret sectors, {analysis.linedef_count} linedefs, "
            f"{analysis.sector_count} sectors, estimated difficulty {analysis.estimated_difficulty or 'unknown'}."
        )

    @staticmethod
    def _problem_statement(run: TestRun, defects: list[Defect], metrics: dict[str, Any]) -> str:
        if ReportService._is_pwad_crash(run):
            return run.failure_summary or "The PWAD crashed or failed to initialize in the configured test runtime."
        if run.status == "failed":
            return f"The QA run ended before producing a complete gameplay verdict: {run.error_message or run.outcome}."
        if defects:
            top = min(defects, key=lambda defect: defect.severity)
            return (
                f"The highest-severity open finding is '{top.title}' at severity {top.severity}. "
                "Review this before publishing the map."
            )
        if metrics["position_sample_count"] < 3:
            return "Gameplay evidence is limited because the run produced fewer than three position samples."
        return "No escalation blocker was detected from the collected automated evidence."

    @staticmethod
    def _display_outcome(run: TestRun, defects: list[Defect]) -> str:
        if any(defect.defect_type == "inconclusive_agent_stall" for defect in defects):
            return "inconclusive_agent_stall"
        if run.outcome == "timeout" and any(defect.defect_type == "softlock_navigation" for defect in defects):
            return "stuck"
        return run.outcome or run.status

    @staticmethod
    def _covered_objectives(run: TestRun, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        covered = [
            {"objective": "Map launch and initial state capture", "evidence": f"Run status: {run.status}."},
            {"objective": "Agent decision logging", "evidence": f"{metrics['event_count']} decision event(s) recorded."},
        ]
        if metrics["position_sample_count"]:
            covered.append(
                {
                    "objective": "Movement telemetry",
                    "evidence": f"{metrics['position_sample_count']} position sample(s) across {metrics['position_cluster_count']} cluster(s).",
                }
            )
        if run.recording_mp4_path:
            covered.append({"objective": "Gameplay recording", "evidence": f"/runs/{run.id}/recording"})
        return covered

    @staticmethod
    def _omitted_objectives(
        run: TestRun,
        metrics: dict[str, Any],
        outcome: str | None = None,
    ) -> list[dict[str, Any]]:
        omitted: list[dict[str, Any]] = []
        display_outcome = outcome or run.outcome or run.status
        if display_outcome != "map_completed":
            omitted.append({"objective": "Verified map exit", "reason": f"Run outcome was {display_outcome}."})
        if metrics["position_cluster_count"] < 3:
            omitted.append({"objective": "Broad spatial coverage", "reason": "The automated playthrough did not visit at least three coarse map areas."})
        if not run.recording_mp4_path:
            omitted.append({"objective": "Video artifact", "reason": "No recording path was produced."})
        return omitted or [{"objective": "None", "reason": "All planned high-level objectives produced evidence."}]

    @staticmethod
    def _uncovered_attributes(run: TestRun, metrics: dict[str, Any]) -> str:
        missing = []
        if run.outcome != "map_completed":
            missing.append("exit reliability")
        secret_sector_count = int(metrics.get("secret_sector_count") or 0)
        if (
            secret_sector_count > 0
            and metrics["max_secrets"] in (None, 0)
            and float(metrics.get("coverage_percent") or 0) >= 60
        ):
            missing.append("secret accessibility")
        if metrics["position_cluster_count"] < 3:
            missing.append("full-map traversal depth")
        return ", ".join(missing) if missing else "No major attributes remained uncovered by this run."

    @staticmethod
    def _defect_patterns(defects: list[Defect]) -> str:
        if not defects:
            return "No repeated defect pattern was identified."
        counts: dict[str, int] = {}
        for defect in defects:
            counts[defect.defect_type] = counts.get(defect.defect_type, 0) + 1
        return "; ".join(f"{defect_type}: {count}" for defect_type, count in sorted(counts.items()))

    @staticmethod
    def _test_limitations(run: TestRun, metrics: dict[str, Any]) -> str:
        limitations = [
            "Automated play can miss secrets or optional combat paths that require map-specific intent.",
            "Single-run results should be confirmed with additional seeds or manual review before release decisions.",
        ]
        if run.status == "failed":
            limitations.insert(0, "The run ended before gameplay coverage was complete.")
        if metrics["position_sample_count"] < 3:
            limitations.insert(0, "Telemetry volume was too low for strong spatial conclusions.")
        if metrics.get("hidden_enemy_count"):
            limitations.insert(
                0,
                f"{metrics['hidden_enemy_count']} raw enemy/enemies did not spawn at difficulty {run.difficulty_level}; "
                "combat conclusions only apply to spawned enemies.",
            )
        return " ".join(limitations)

    @staticmethod
    def _major_risk(run: TestRun, defects: list[Defect], metrics: dict[str, Any]) -> str:
        if run.status == "failed":
            return "Primary risk: the automated QA run did not complete gameplay coverage."
        if defects:
            return "Primary risk: at least one detected defect needs author review."
        if metrics.get("hidden_enemy_count"):
            return "Primary risk: selected-difficulty skill flags hide enemies found by raw static analysis."
        if metrics["position_cluster_count"] < 3:
            return "Primary risk: coverage is too narrow to prove the whole map is shippable."
        return "Primary risk is low for the paths exercised in this automated run."

    @staticmethod
    def _risk_areas(run: TestRun, defects: list[Defect], metrics: dict[str, Any]) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        outcome = ReportService._display_outcome(run, defects)
        if run.status == "failed":
            area = "Runtime compatibility" if ReportService._is_pwad_crash(run) else "Run completion"
            risks.append({"area": area, "risk": run.failure_summary or run.error_message or "Run ended before completion."})
        if outcome != "map_completed":
            risks.append({"area": "Progression", "risk": f"Map exit was not verified; outcome was {outcome}."})
        if metrics["position_cluster_count"] < 3:
            risks.append({"area": "Traversal coverage", "risk": "The automated playthrough visited too few coarse position clusters."})
        if metrics.get("hidden_enemy_count"):
            risks.append(
                {
                    "area": "Difficulty flags",
                    "risk": (
                        f"{metrics['hidden_enemy_count']} enemy/enemies are present in raw THINGS but do not spawn "
                        f"at difficulty {run.difficulty_level}."
                    ),
                }
            )
        for defect in defects[:5]:
            risks.append({"area": defect.defect_type, "risk": defect.title})
        return risks or [{"area": "Exercised path", "risk": "No high-risk issue was observed."}]

    @staticmethod
    def _good_quality_areas(
        run: TestRun,
        metrics: dict[str, Any],
        analysis: StaticAnalysisResult | None,
    ) -> list[dict[str, Any]]:
        areas = []
        if run.status == "completed":
            areas.append({"area": "Runtime stability", "evidence": "The backend completed the run lifecycle."})
        if metrics["position_sample_count"] >= 3:
            areas.append({"area": "Telemetry", "evidence": "The run includes multiple position samples."})
        if run.recording_mp4_path:
            areas.append({"area": "Evidence capture", "evidence": "A gameplay recording artifact was produced."})
        if analysis is not None:
            areas.append({"area": "Static context", "evidence": "The report includes parsed map structure and thing counts."})
        return areas or [{"area": "Initial launch", "evidence": "The map was accepted into the QA pipeline."}]

    # ---- 14-section professional QA report builders ----

    @staticmethod
    def _build_executive_summary(
        run: TestRun, defects: list[Defect], metrics: dict[str, Any],
        analysis: StaticAnalysisResult | None, outcome: str, overall_verdict: str,
    ) -> str:
        spawned = int(metrics.get("spawned_enemy_count") or 0)
        kills = run.total_kills or 0
        coverage = float(metrics.get("coverage_percent") or 0)
        defect_count = len(defects)
        severity_1 = sum(1 for d in defects if d.severity == 1)
        parts = [
            f"Automated QA analysis of map {run.map_name} (IWAD: {run.iwad_used}, difficulty {run.difficulty_level}).",
            f"Outcome: {outcome}. Overall verdict: {overall_verdict}.",
            f"The automated playthrough executed {run.total_actions_taken or 0} lockstep decisions over "
            f"{run.duration_seconds or 0} wall-clock seconds, achieving {coverage:.1f}% coarse cell coverage.",
        ]
        if spawned > 0:
            parts.append(f"Combat: {kills}/{spawned} enemies eliminated ({kills/spawned*100:.0f}% kill rate).")
        if defect_count:
            parts.append(f"Defects detected: {defect_count} ({severity_1} critical/major).")
        else:
            parts.append("No confirmed defects were detected during this run.")
        if analysis:
            parts.append(
                f"Map geometry: {analysis.linedef_count} linedefs, {analysis.sector_count} sectors, "
                f"{analysis.secret_sector_count} secret sector(s)."
            )
        return " ".join(parts)

    @staticmethod
    def _build_critical_issues(defects: list[Defect], run: TestRun) -> str:
        if not defects:
            return "No critical issues were identified during this automated QA pass."
        lines = []
        for defect in sorted(defects, key=lambda d: (d.severity, d.priority)):
            sev_label = {1: "Critical", 2: "Major", 3: "Moderate", 4: "Minor", 5: "Cosmetic"}.get(
                defect.severity, f"Severity-{defect.severity}"
            )
            lines.append(
                f"[{sev_label}] {defect.title} — {defect.description[:200]}"
                + (f" (tick {defect.detected_at_tick})" if defect.detected_at_tick else "")
            )
        return "\n".join(lines)

    @staticmethod
    def _build_geometry_analysis(analysis: StaticAnalysisResult | None, run: TestRun) -> str:
        if not analysis:
            return "Static analysis was unavailable. Geometry assessment requires parsed WAD data."
        parts = [
            f"Map dimensions: {analysis.map_width_units or '?'} x {analysis.map_height_units or '?'} Doom units.",
            f"Linedefs: {analysis.linedef_count}. Sectors: {analysis.sector_count}. Vertices: {analysis.vertex_count or '?'}.",
            f"Thing count: {analysis.thing_count_total} total ({analysis.thing_count_enemies} enemies, "
            f"{analysis.thing_count_items} items, {analysis.thing_count_keys} keys).",
        ]
        # Vanilla Doom limits check
        if analysis.linedef_count and analysis.linedef_count > 32768:
            parts.append("WARNING: Linedef count exceeds vanilla Doom limit (32768). Requires limit-removing port.")
        if analysis.sector_count and analysis.sector_count > 32768:
            parts.append("WARNING: Sector count exceeds vanilla Doom limit (32768). Requires limit-removing port.")
        if analysis.vertex_count and analysis.vertex_count > 65536:
            parts.append("WARNING: Vertex count exceeds vanilla Doom limit (65536).")
        # Visplane estimate
        if analysis.sector_count and analysis.sector_count > 128:
            parts.append(f"Sector count ({analysis.sector_count}) is elevated. Monitor for visplane overflow risk.")
        return " ".join(parts)

    @staticmethod
    def _build_gameplay_flow(run: TestRun, metrics: dict[str, Any], analysis: StaticAnalysisResult | None) -> str:
        coverage = float(metrics.get("coverage_percent") or 0)
        clusters = metrics.get("position_cluster_count", 0)
        movement = metrics.get("movement_distance_units", 0)
        parts = [
            f"Player movement: {movement:.0f} map units across {clusters} coarse position cluster(s).",
            f"Map coverage: {coverage:.1f}% of estimated cells explored.",
        ]
        if run.outcome == "map_completed":
            parts.append("The map exit was reached — full progression path validated.")
        elif run.outcome == "timeout":
            parts.append("Run timed out before reaching the map exit. Progression may be blocked or insufficient budget.")
        elif run.outcome == "player_died":
            parts.append("The automated player died. Combat pressure or resource deficit may be factors.")
        elif run.outcome in ("stuck", "inconclusive_agent_stall"):
            parts.append("The agent stalled. Possible geometry trap, navigation ambiguity, or agent limitation.")
        if analysis:
            door_count = getattr(analysis, "door_count", None)
            lift_count = getattr(analysis, "lift_count", None)
            teleporter_count = getattr(analysis, "teleporter_count", None)
            if door_count:
                parts.append(f"Map contains {door_count} doors, {lift_count or 0} lifts, {teleporter_count or 0} teleporters.")
        return " ".join(parts)

    @staticmethod
    def _build_combat_review(
        run: TestRun, metrics: dict[str, Any],
        analysis: StaticAnalysisResult | None, defects: list[Defect],
    ) -> str:
        spawned = int(metrics.get("spawned_enemy_count") or 0)
        kills = run.total_kills or 0
        hitscanner_pct = float((analysis or StaticAnalysisResult()).hitscanner_percent or 0)
        parts = []
        if spawned == 0:
            parts.append("No enemies spawn at the selected difficulty. Combat review not applicable.")
        else:
            kill_rate = kills / spawned * 100
            parts.append(f"Kill rate: {kills}/{spawned} ({kill_rate:.0f}%).")
            if kill_rate < 25:
                parts.append("Kill rate is very low. The agent may be avoiding combat or lacking ammo/weapons.")
            elif kill_rate < 50:
                parts.append("Kill rate is moderate. Some encounters may have been bypassed.")
            if hitscanner_pct > 40:
                parts.append(f"Hitscanner ratio is high ({hitscanner_pct:.0f}%). Expect ranged pressure on the player.")
            combat_defects = [d for d in defects if "combat" in d.defect_type or d.defect_type == "ammo_starvation"]
            if combat_defects:
                parts.append(f"{len(combat_defects)} combat-related defect(s) detected.")
        health_ratio = float(analysis.health_ratio or 1.0) if analysis else 1.0
        ammo_ratio = float(analysis.ammo_ratio or 1.0) if analysis else 1.0
        if health_ratio < 0.2:
            parts.append("Health economy is critically low relative to monster HP.")
        if ammo_ratio < 0.5:
            parts.append("Ammo economy is deficient relative to monster HP.")
        return " ".join(parts) if parts else "Combat data is insufficient for detailed review."

    @staticmethod
    def _build_itemization_audit(
        run: TestRun, metrics: dict[str, Any],
        analysis: StaticAnalysisResult | None, defects: list[Defect],
    ) -> str:
        if not analysis:
            return "Static analysis unavailable. Itemization audit requires parsed WAD data."
        parts = [
            f"Health pickups: {analysis.total_health_pickup_pts or 0} HP worth.",
            f"Armor pickups: {analysis.total_armor_pickup_pts or 0} points.",
            f"Health ratio: {analysis.health_ratio:.4f}. Ammo ratio: {analysis.ammo_ratio:.4f}.",
        ]
        if analysis.health_ratio < 0.2:
            parts.append("SEVERITY: Health economy is critically low. Players will face ammo starvation.")
        elif analysis.health_ratio < 0.4:
            parts.append("Health economy is tight. Resource management will be challenging.")
        if analysis.ammo_ratio < 0.5:
            parts.append("SEVERITY: Ammo economy is critically low. Melee combat or infighting may be required.")
        elif analysis.ammo_ratio < 0.8:
            parts.append("Ammo economy is tight. Conservation will be necessary.")
        items = [d for d in defects if d.defect_type in ("static_ammo_risk", "static_health_risk", "ammo_starvation")]
        if items:
            parts.append(f"{len(items)} itemization-related defect(s) flagged.")
        return " ".join(parts)

    @staticmethod
    def _build_ai_behavior(run: TestRun, metrics: dict[str, Any], defects: list[Defect]) -> str:
        parts = []
        flags = metrics.get("agent_quality_flags") or {}
        warnings = flags.get("warnings", [])
        if warnings:
            parts.append(f"Agent quality warnings: {len(warnings)}.")
            for w in warnings[:3]:
                parts.append(f"  - {w}")
        stuck_defects = [d for d in defects if d.defect_type in ("softlock_navigation", "inconclusive_agent_stall")]
        if stuck_defects:
            parts.append(f"Navigation stall detected: {len(stuck_defects)} occurrence(s). Agent may have encountered geometry traps.")
        progress = metrics.get("progress_metrics") or {}
        progress_score = progress.get("progress_score", 0)
        if progress_score < 5:
            parts.append("Agent progress score is low. Navigation effectiveness may be limited.")
        if not parts:
            parts.append("Agent behavior was within normal parameters for this run.")
        return " ".join(parts)

    @staticmethod
    def _build_navigation_readability(run: TestRun, metrics: dict[str, Any], analysis: StaticAnalysisResult | None) -> str:
        coverage = float(metrics.get("coverage_percent") or 0)
        clusters = metrics.get("position_cluster_count", 0)
        parts = [
            f"Coarse cell coverage: {coverage:.1f}%.",
            f"Position clusters visited: {clusters}.",
        ]
        if coverage < 20:
            parts.append("Coverage is critically low. The agent explored very little of the map.")
        elif coverage < 50:
            parts.append("Coverage is moderate. Significant portions of the map remain unexplored.")
        if analysis and analysis.secret_sector_count > 0:
            secrets_found = run.secrets_found or 0
            parts.append(f"Secrets: {secrets_found}/{analysis.secret_sector_count} found.")
        return " ".join(parts)

    @staticmethod
    def _build_secrets_analysis(run: TestRun, metrics: dict[str, Any], analysis: StaticAnalysisResult | None) -> str:
        if not analysis or analysis.secret_sector_count == 0:
            return "No secret sectors detected in static analysis."
        secrets_found = run.secrets_found or 0
        coverage = float(metrics.get("coverage_percent") or 0)
        parts = [
            f"Secret sectors: {analysis.secret_sector_count}.",
            f"Secrets found: {secrets_found}.",
            f"Map coverage: {coverage:.1f}%.",
        ]
        if secrets_found == 0 and coverage >= 40:
            parts.append("No secrets found at sufficient coverage. Possible unreachable secret or poor placement.")
        elif secrets_found == 0:
            parts.append("No secrets found, but coverage may be insufficient to draw conclusions.")
        return " ".join(parts)

    @staticmethod
    def _build_performance_analysis(analysis: StaticAnalysisResult | None, run: TestRun) -> str:
        if not analysis:
            return "Static analysis unavailable. Performance assessment requires geometry data."
        parts = []
        # Vanilla Doom limits
        vanilla_limits = {
            "linedefs": 32768, "sidedefs": 65536, "sectors": 32768,
            "vertices": 65536, "segments": 65536, "subsectors": 32768,
            "nodes": 32768, "things": 4096,
        }
        if analysis.linedef_count:
            ratio = analysis.linedef_count / vanilla_limits["linedefs"] * 100
            parts.append(f"Linedefs: {analysis.linedef_count}/{vanilla_limits['linedefs']} ({ratio:.0f}% of vanilla limit).")
            if ratio > 80:
                parts.append("WARNING: Approaching vanilla linedef limit.")
        if analysis.sector_count:
            ratio = analysis.sector_count / vanilla_limits["sectors"] * 100
            parts.append(f"Sectors: {analysis.sector_count}/{vanilla_limits['sectors']} ({ratio:.0f}% of vanilla limit).")
        if analysis.thing_count_total:
            ratio = analysis.thing_count_total / vanilla_limits["things"] * 100
            parts.append(f"Things: {analysis.thing_count_total}/{vanilla_limits['things']} ({ratio:.0f}% of vanilla limit).")
        parts.append("Compatible with limit-removing source ports (Boom, MBF, PrBoom+).")
        return " ".join(parts)

    @staticmethod
    def _build_speedrunning_analysis(run: TestRun, metrics: dict[str, Any], analysis: StaticAnalysisResult | None) -> str:
        parts = []
        if run.outcome == "map_completed":
            parts.append("Map completion achieved. Speedrun route analysis is possible from the position trail data.")
        else:
            parts.append("Map was not completed. Full speedrun route analysis requires a completed run.")
        if analysis:
            parts.append(
                f"Map dimensions: {analysis.map_width_units or '?'} x {analysis.map_height_units or '?'} units. "
                "Larger maps may have more sequence break opportunities."
            )
        parts.append("Potential speedrun elements: linedef skips, glide spots, arch-vile jumps, and exit shortcuts.")
        return " ".join(parts)

    @staticmethod
    def _build_recommendations(
        run: TestRun, defects: list[Defect], metrics: dict[str, Any],
        analysis: StaticAnalysisResult | None,
    ) -> str:
        recs = []
        if defects:
            sev1 = [d for d in defects if d.severity == 1]
            sev2 = [d for d in defects if d.severity == 2]
            if sev1:
                recs.append(f"PRIORITY 1: Address {len(sev1)} critical/major defect(s) before release.")
            if sev2:
                recs.append(f"PRIORITY 2: Review {len(sev2)} moderate defect(s) for gameplay impact.")
        coverage = float(metrics.get("coverage_percent") or 0)
        if coverage < 50:
            recs.append("Increase run budget or test additional maps to improve coverage confidence.")
        if run.outcome != "map_completed":
            recs.append("Investigate the run outcome to determine if the issue is map-side or agent-side.")
        if analysis and analysis.health_ratio < 0.2:
            recs.append("Add health pickups to improve survivability at the tested difficulty.")
        if analysis and analysis.ammo_ratio < 0.5:
            recs.append("Add ammo pickups or reduce monster count to prevent resource starvation.")
        if not recs:
            recs.append("No immediate action required. Map passed automated QA checks.")
        return " ".join(recs)

    @staticmethod
    def _build_final_verdict(
        run: TestRun, defects: list[Defect], metrics: dict[str, Any],
        analysis: StaticAnalysisResult | None, overall_verdict: str,
    ) -> str:
        coverage = float(metrics.get("coverage_percent") or 0)
        spawned = int(metrics.get("spawned_enemy_count") or 0)
        kills = run.total_kills or 0
        parts = [
            f"Overall Quality Rating: {'3/5' if overall_verdict == 'PASS' else '2/5' if overall_verdict == 'PARTIAL' else '1/5'}.",
            f"Technical Stability: {'PASS' if run.status == 'completed' else 'FAIL'}.",
            f"Gameplay Rating: {overall_verdict}.",
        ]
        if spawned > 0:
            parts.append(f"Combat Effectiveness: {kills}/{spawned} kills ({kills/spawned*100:.0f}%).")
        parts.append(f"Coverage: {coverage:.1f}%.")
        if overall_verdict == "PASS":
            parts.append("Release Readiness: CONDITIONAL PASS — verify with additional runs.")
        else:
            parts.append("Release Readiness: NOT READY — address defects and re-test.")
        return " ".join(parts)

    @staticmethod
    def _run_snapshot(run: TestRun) -> dict[str, Any]:
        keys = [
            "id",
            "wad_file_id",
            "map_name",
            "difficulty_level",
            "iwad_used",
            "llm_model",
            "max_ticks",
            "status",
            "started_at",
            "completed_at",
            "duration_seconds",
            "outcome",
            "error_message",
            "failure_category",
            "failure_stage",
            "failure_summary",
            "failure_diagnostics",
            "final_hp",
            "final_armor",
            "total_kills",
            "secrets_found",
            "total_items_collected",
            "total_actions_taken",
            "total_llm_calls",
            "recording_metadata",
            "progress_metrics",
            "agent_quality_flags",
        ]
        result = {key: getattr(run, key) for key in keys}
        result["recording_mp4_url"] = f"/runs/{run.id}/recording" if (run.recording_mp4_path or (run.recording_metadata or {}).get("quality_status") == "ok") else None
        return result

    @staticmethod
    def _analysis_snapshot(analysis: StaticAnalysisResult | None) -> dict[str, Any] | None:
        if analysis is None:
            return None
        keys = [
            "map_name",
            "map_title",
            "map_display_name",
            "map_title_source",
            "thing_count_total",
            "thing_count_enemies",
            "thing_count_items",
            "thing_count_keys",
            "thing_count_weapons",
            "linedef_count",
            "sector_count",
            "secret_sector_count",
            "vertex_count",
            "map_width_units",
            "map_height_units",
            "total_monster_hp",
            "total_health_pickup_pts",
            "total_armor_pickup_pts",
            "hitscanner_percent",
            "health_ratio",
            "ammo_ratio",
            "estimated_difficulty",
            "enemy_breakdown",
            "item_breakdown",
            "spawn_summary_by_skill",
        ]
        result = {key: getattr(analysis, key) for key in keys}
        result["map_overview_png_url"] = (
            f"/wads/{analysis.wad_file_id}/map-png?map_name={analysis.map_name}"
            if analysis.map_overview_png_path else None
        )
        return result

    @staticmethod
    def _event_snapshot(event: GameEvent) -> dict[str, Any]:
        action = event.action_taken or {}
        action_output = action.get("mcp_output") if isinstance(action.get("mcp_output"), dict) else {}
        action_summary = action.get("mcp_action_summary")
        if not isinstance(action_summary, dict):
            action_summary = action_output.get("action_summary") if isinstance(action_output, dict) else None
        return {
            "tick": event.tick_number,
            "event_type": event.event_type,
            "position": {"x": event.player_x, "y": event.player_y, "angle": event.player_angle},
            "health": event.health,
            "armor": event.armor,
            "kills": event.kill_count,
            "items": event.item_count,
            "secrets": event.secret_count,
            "damage_received": event.damage_received,
            "mcp_tool": action.get("mcp_tool"),
            "mcp_executed_tool": action.get("mcp_executed_tool") or action.get("mcp_tool"),
            "mcp_params": action.get("mcp_params"),
            "mcp_action_summary": action_summary if isinstance(action_summary, dict) else None,
            "reasoning": (event.llm_reasoning or "")[:500],
        }

    @staticmethod
    def _decision_snapshot(decision: AgentDecision) -> dict[str, Any]:
        return {
            "sequence_number": decision.sequence_number,
            "tick_before": decision.tick_before,
            "tick_after": decision.tick_after,
            "status": decision.status,
            "reasoning_summary": (decision.reasoning_summary or "")[:500],
            "mcp_tool": decision.mcp_tool,
            "mcp_input": decision.mcp_input,
            "mcp_stop_reason": decision.mcp_stop_reason,
            "decision_source": decision.decision_source,
            "validation_rejection": (
                (decision.mcp_output or {}).get("action_summary", {}).get("validation_error")
                if isinstance(decision.mcp_output, dict)
                else None
            ),
            "llm_duration_ms": decision.llm_duration_ms,
            "mcp_duration_ms": decision.mcp_duration_ms,
            "error_message": decision.error_message,
        }

    @staticmethod
    def _defect_snapshot(defect: Defect) -> dict[str, Any]:
        return {
            "severity": defect.severity,
            "priority": defect.priority,
            "defect_type": defect.defect_type,
            "fingerprint": defect.fingerprint,
            "title": defect.title,
            "description": defect.description,
            "detected_at_tick": defect.detected_at_tick,
            "first_seen_tick": defect.first_seen_tick,
            "last_seen_tick": defect.last_seen_tick,
            "occurrence_count": defect.occurrence_count,
            "position": {"x": defect.position_x, "y": defect.position_y},
            "recommendation": defect.recommendation,
        }

    @staticmethod
    def _position_snapshot(position: AgentPositionTrail | None) -> dict[str, Any] | None:
        if position is None:
            return None
        return {
            "tick": position.tick_number,
            "x": position.x,
            "y": position.y,
            "angle": position.angle,
            "health": position.health,
        }

    @staticmethod
    def _image_data_uri(path_value: str | None) -> str | None:
        if not path_value:
            return None
        path = Path(path_value)
        if not path.exists():
            return None
        with contextlib.suppress(Exception):
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
        return None

    @staticmethod
    def _difficulty_rows(analysis: StaticAnalysisResult | None, selected_difficulty: int) -> list[dict[str, Any]]:
        if analysis is None:
            return []
        summaries = getattr(analysis, "spawn_summary_by_skill", None) or {}
        rows = []
        for skill in range(1, 6):
            row = summaries.get(str(skill)) or summaries.get(skill) if isinstance(summaries, dict) else None
            if not isinstance(row, dict):
                row = {
                    "thing_count_enemies": getattr(analysis, "thing_count_enemies", 0),
                    "thing_count_items": getattr(analysis, "thing_count_items", 0),
                    "health_ratio": getattr(analysis, "health_ratio", 0),
                    "ammo_ratio": getattr(analysis, "ammo_ratio", 0),
                    "estimated_difficulty": getattr(analysis, "estimated_difficulty", "unknown"),
                }
            rows.append(
                {
                    "skill": skill,
                    "tested": skill == selected_difficulty,
                    "enemies": row.get("thing_count_enemies", 0),
                    "items": row.get("thing_count_items", 0),
                    "health_ratio": row.get("health_ratio", 0),
                    "ammo_ratio": row.get("ammo_ratio", 0),
                    "estimated_difficulty": row.get("estimated_difficulty", "unknown"),
                    "warning": int(row.get("thing_count_enemies") or 0) == 0,
                }
            )
        return rows

    @staticmethod
    def _position_trail_overlay_data_uri(
        map_path: str | None,
        positions: list[AgentPositionTrail],
        events: list[GameEvent],
        map_bounds: dict[str, int] | None = None,
    ) -> str | None:
        if not map_path or not positions:
            return None
        path = Path(map_path)
        if not path.exists():
            return None
        try:
            image = Image.open(path).convert("RGBA")
            draw = ImageDraw.Draw(image, "RGBA")
            if map_bounds:
                min_x = map_bounds["min_x"]
                max_x = map_bounds["max_x"]
                min_y = map_bounds["min_y"]
                max_y = map_bounds["max_y"]
            else:
                all_points = [(position.x, position.y) for position in positions]
                min_x, max_x, min_y, max_y = _point_bounds(all_points)

            def project(x: float, y: float) -> tuple[int, int]:
                width, height = image.size
                px = int(20 + ((x - min_x) / max(max_x - min_x, 1)) * (width - 40))
                py = int(height - 20 - ((y - min_y) / max(max_y - min_y, 1)) * (height - 40))
                return px, py

            trail_points = [project(position.x, position.y) for position in positions]
            if len(trail_points) > 1:
                draw.line(trail_points, fill=(37, 99, 235, 235), width=6, joint="curve")
                draw.line(trail_points, fill=(147, 197, 253, 210), width=2, joint="curve")
            for x, y in trail_points:
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(59, 130, 246, 180), outline=(255, 255, 255, 180), width=1)
            if trail_points:
                start_x, start_y = trail_points[0]
                end_x, end_y = trail_points[-1]
                draw.ellipse((start_x - 8, start_y - 8, start_x + 8, start_y + 8), fill=(22, 163, 74, 240), outline=(255, 255, 255, 230), width=2)
                draw.ellipse((end_x - 9, end_y - 9, end_x + 9, end_y + 9), fill=(245, 158, 11, 245), outline=(255, 255, 255, 240), width=2)
            for event in events:
                if event.event_type == "normal":
                    continue
                x, y = project(event.player_x, event.player_y)
                color = {
                    "kill": (220, 38, 38, 220),
                    "stuck": (245, 158, 11, 220),
                    "death": (0, 0, 0, 230),
                    "item_pickup": (22, 163, 74, 220),
                }.get(event.event_type, (8, 145, 178, 220))
                if event.event_type == "death":
                    draw.line((x - 10, y - 10, x + 10, y + 10), fill=color, width=5)
                    draw.line((x + 10, y - 10, x - 10, y + 10), fill=color, width=5)
                else:
                    draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color, outline=(255, 255, 255, 230), width=2)
            from io import BytesIO

            buffer = BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
        except Exception:
            return None

    def _render_pdf(self, run_id: UUID, report: dict[str, Any], payload: dict[str, Any]) -> Path:
        self.settings.report_storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.report_storage_dir / f"{run_id}.pdf"
        HTML(string=self._render_pdf_html(report, payload)).write_pdf(path)
        return path

    @staticmethod
    def _render_pdf_html(report: dict[str, Any], payload: dict[str, Any]) -> str:
        verdict_keys = ["map_navigation", "combat_engagement", "resource_balance", "secret_coverage", "overall_verdict"]
        rationale_keys = ["navigation_rationale", "combat_rationale", "resource_rationale", "secret_rationale"]
        display_defects = payload["defects"][:25]
        all_decisions = payload.get("decisions", [])
        if len(all_decisions) > 16:
            display_decisions = [*all_decisions[:8], *all_decisions[-8:]]
        else:
            display_decisions = all_decisions
        defect_omitted_count = max(len(payload["defects"]) - len(display_defects), 0)
        decision_omitted_count = max(len(all_decisions) - len(display_decisions), 0)
        display_outcome = ReportService._display_outcome(payload["run"], payload["defects"])
        analysis = payload.get("analysis")
        run = payload["run"]
        map_thumbnail = ReportService._image_data_uri(getattr(analysis, "map_overview_png_path", None))
        trail_overlay = ReportService._position_trail_overlay_data_uri(
            getattr(analysis, "map_overview_png_path", None),
            payload.get("position_trail") or [],
            payload.get("events") or [],
            payload.get("map_bounds") or ReportService._analysis_map_bounds(analysis),
        )
        metric_cards = [
            {"label": "Wall-clock sec", "value": getattr(run, "duration_seconds", None) or 0},
            {"label": "Gameplay sec", "value": (getattr(run, "recording_metadata", None) or {}).get("duration_seconds", 0)},
            {"label": "Actions", "value": getattr(run, "total_actions_taken", None) or 0},
            {"label": "Final HP", "value": getattr(run, "final_hp", None) or 0},
            {"label": "Kills/Spawned", "value": f"{getattr(run, 'total_kills', None) or 0}/{payload['metrics'].get('spawned_enemy_count', 0)}"},
            {"label": "Secrets", "value": getattr(run, "secrets_found", None) or 0},
            {"label": "Defects", "value": len(payload["defects"])},
        ]
        difficulty_rows = ReportService._difficulty_rows(analysis, getattr(run, "difficulty_level", 3))
        event_rows = []
        for event in payload["notable_events"]:
            action = event.action_taken or {}
            output = action.get("mcp_output") if isinstance(action.get("mcp_output"), dict) else {}
            summary = output.get("action_summary") if isinstance(output, dict) else {}
            event_rows.append(
                {
                    "tick": event.tick_number,
                    "event_type": event.event_type,
                    "position": f"{event.player_x:.1f}, {event.player_y:.1f}",
                    "health": event.health,
                    "tool": action.get("mcp_executed_tool") or action.get("mcp_tool") or "",
                    "stop_reason": summary.get("stop_reason") if isinstance(summary, dict) else None,
                }
            )
        decision_rows = [
            {
                "sequence_number": decision.sequence_number,
                "tick_before": decision.tick_before,
                "tick_after": decision.tick_after,
                "mcp_tool": decision.mcp_tool,
                "mcp_stop_reason": decision.mcp_stop_reason,
                "decision_source": getattr(decision, "decision_source", "gemini"),
                "validation_rejection": (
                    (getattr(decision, "mcp_output", None) or {}).get("action_summary", {}).get("validation_error")
                    if isinstance(getattr(decision, "mcp_output", None), dict)
                    else None
                ),
                "reasoning_summary": decision.reasoning_summary,
                "mcp_input": ReportService._json_block(getattr(decision, "mcp_input", None), limit=700),
                "mcp_output": ReportService._json_block(getattr(decision, "mcp_output", None), limit=900),
            }
            for decision in display_decisions
        ]
        templates_dir = Path(__file__).resolve().parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)))
        template = env.get_template("report.html.j2")
        return template.render(
            run=payload["run"],
            analysis=payload["analysis"],
            defects=display_defects,
            decisions=decision_rows,
            defect_omitted_count=defect_omitted_count,
            decision_omitted_count=decision_omitted_count,
            event_rows=event_rows,
            metrics=payload["metrics"],
            report=report,
            verdict_keys=verdict_keys,
            rationale_keys=rationale_keys,
            display_outcome=display_outcome,
            map_thumbnail=map_thumbnail,
            trail_overlay=trail_overlay,
            metric_cards=metric_cards,
            difficulty_rows=difficulty_rows,
        )

    @staticmethod
    def _json_block(value: Any, limit: int = 1800) -> str:
        if value in (None, {}, []):
            return ""
        try:
            text = json.dumps(value, indent=2, sort_keys=True, default=str)
        except TypeError:
            text = str(value)
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _analysis_map_bounds(analysis: StaticAnalysisResult | None) -> dict[str, int] | None:
        if analysis is None:
            return None
        features = (getattr(analysis, "spawn_summary_by_skill", None) or {}).get("_map_features")
        if not isinstance(features, dict):
            return None
        bounds = features.get("bounds")
        if not isinstance(bounds, dict):
            return None
        try:
            min_x = int(bounds["min_x"])
            max_x = int(bounds["max_x"])
            min_y = int(bounds["min_y"])
            max_y = int(bounds["max_y"])
        except (KeyError, TypeError, ValueError):
            return None
        if min_x == max_x or min_y == max_y:
            return None
        return {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}


def _point_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points] or [0.0]
    ys = [point[1] for point in points] or [0.0]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    if min_x == max_x:
        min_x -= 1
        max_x += 1
    if min_y == max_y:
        min_y -= 1
        max_y += 1
    return min_x, max_x, min_y, max_y
