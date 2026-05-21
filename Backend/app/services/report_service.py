from __future__ import annotations

import json
import math
import re
import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Template
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.core.config import get_settings
from app.models import AgentDecision, AgentPositionTrail, Defect, GameEvent, StaticAnalysisResult, TestReport, TestRun
from app.repositories.defect_repository import DefectRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.run_repository import RunRepository
from app.services.analysis_service import selected_skill_spawn_summary
from app.services.prompt_service import report_prompt_path


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = ReportRepository(db)

    async def generate(self, run_id: UUID) -> TestReport:
        await self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"report:{run_id}"})
        existing = await self.repo.get_by_run(run_id)
        if existing is not None and existing.generation_status == "complete" and existing.pdf_path:
            if Path(existing.pdf_path).exists():
                return existing
        if existing is not None:
            await self.repo.update(existing, generation_status="generating", generation_error=None)
        run = await self.db.get(TestRun, run_id)
        if run is None:
            raise ValueError("Run not found")
        analysis = await self.db.get(StaticAnalysisResult, run.static_analysis_id) if run.static_analysis_id else None
        defects = await DefectRepository(self.db).list_by_run(run_id)
        events = list(
            (
                await self.db.execute(
                    select(GameEvent).where(GameEvent.run_id == run_id).order_by(GameEvent.tick_number)
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
                    .order_by(AgentPositionTrail.tick_number)
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
            "metrics": self._build_metrics(run, analysis, events, positions, decisions),
        }
        report_json = await self._call_gemini_or_fallback(payload)
        render_report = self._sanitize_report_voice(self._normalize_report_sections(report_json))
        pdf_path = self._render_pdf(run_id, render_report, payload)
        fields = self._report_fields(run, render_report, pdf_path)
        if existing is not None:
            created = await self.repo.update(existing, **fields)
        else:
            created = await self.repo.create(TestReport(run_id=run_id, **fields))
        await RunRepository(self.db).update(run, report_pdf_path=str(pdf_path))
        return created

    @staticmethod
    def _report_fields(run: TestRun, report_json: dict, pdf_path: Path) -> dict:
        def text_value(key: str) -> str | None:
            return ReportService._coerce_text(report_json.get(key))

        def json_value(key: str) -> Any:
            return report_json.get(key)

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
            "pdf_path": str(pdf_path),
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
        replacements = [
            (r"\b[Tt]he agent failed to\b", "the automated playthrough did not"),
            (r"\b[Aa]gent failed to\b", "automated playthrough did not"),
            (r"\b[Tt]he agent was unable to\b", "the automated playthrough did not"),
            (r"\b[Aa]gent was unable to\b", "automated playthrough did not"),
            (r"\b[Tt]he agent could not\b", "the automated playthrough did not"),
            (r"\b[Aa]gent could not\b", "automated playthrough did not"),
            (r"\b[Tt]he agent did not\b", "the automated playthrough did not"),
            (r"\b[Aa]gent did not\b", "automated playthrough did not"),
            (r"\b[Tt]he automated playthrough was unable to\b", "the automated playthrough did not"),
            (r"\b[Aa]utomated playthrough was unable to\b", "automated playthrough did not"),
            (r"\bAutomated automated playthrough\b", "Automated playthrough"),
            (r"\bautomated automated playthrough\b", "automated playthrough"),
            (r"\bAgent\b", "Automated playthrough"),
            (r"\bagent\b", "automated playthrough"),
        ]
        if isinstance(value, str):
            result = value
            for source, target in replacements:
                result = re.sub(source, target, result)
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
        for event in events:
            event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1
            action = event.action_taken or {}
            tool = action.get("mcp_tool") or "unknown"
            action_counts[tool] = action_counts.get(tool, 0) + 1

        movement_distance = 0.0
        clusters: set[tuple[int, int]] = set()
        previous: AgentPositionTrail | None = None
        for position in positions:
            clusters.add((round(position.x / 128), round(position.y / 128)))
            if previous is not None:
                movement_distance += math.hypot(position.x - previous.x, position.y - previous.y)
            previous = position

        first_position = positions[0] if positions else None
        last_position = positions[-1] if positions else None
        skill_summary = selected_skill_spawn_summary(analysis, run.difficulty_level)
        raw_enemy_count = int(analysis.thing_count_enemies or 0) if analysis else 0
        spawned_enemy_count = int(skill_summary.get("thing_count_enemies") or 0)
        raw_item_count = int(analysis.thing_count_items or 0) if analysis else 0
        spawned_item_count = int(skill_summary.get("thing_count_items") or 0)
        return {
            "event_count": len(events),
            "decision_count": len(decisions or []),
            "position_sample_count": len(positions),
            "position_cluster_count": len(clusters),
            "movement_distance_units": round(movement_distance, 1),
            "event_type_counts": event_type_counts,
            "action_counts": action_counts,
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
            "recording_mp4_path": run.recording_mp4_path,
            "report_pdf_path": run.report_pdf_path,
            "recording_metadata": run.recording_metadata or {},
            "progress_metrics": run.progress_metrics or {},
            "agent_quality_flags": run.agent_quality_flags or {},
            "recording_file_size_bytes": (
                Path(run.recording_mp4_path).stat().st_size
                if run.recording_mp4_path and Path(run.recording_mp4_path).exists()
                else None
            ),
        }

    async def _call_gemini_or_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback_report(payload)
        prompt = report_prompt_path().read_text()
        compact = {
            "run": self._run_snapshot(payload["run"]),
            "analysis": self._analysis_snapshot(payload["analysis"]),
            "metrics": payload["metrics"],
            "defects": [self._defect_snapshot(defect) for defect in payload["defects"][:50]],
            "notable_events": [self._event_snapshot(event) for event in payload["notable_events"][:20]],
            "first_ticks": [self._event_snapshot(event) for event in payload["first_ticks"]],
            "last_ticks": [self._event_snapshot(event) for event in payload["last_ticks"]],
            "decision_trace": [self._decision_snapshot(decision) for decision in payload.get("decisions", [])[:30]],
        }
        if not self.settings.gemini_api_key:
            return fallback
        try:
            from google import genai

            def generate() -> str:
                client = genai.Client(api_key=self.settings.gemini_api_key)
                response = client.models.generate_content(
                    model=self.settings.llm_model,
                    contents=f"{prompt}\n\nDATA:\n{json.dumps(compact, default=str)}",
                )
                return response.text or "{}"

            text = await asyncio.to_thread(generate)
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end < start:
                raise ValueError("Report model did not return JSON")
            generated = json.loads(text[start : end + 1])
            return self._merge_report_defaults(fallback, generated)
        except Exception:
            return fallback

    @staticmethod
    def _merge_report_defaults(defaults: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
        merged = dict(defaults)
        for key, value in generated.items():
            if key == "pass_fail_summary":
                continue
            if value not in (None, "", [], {}):
                merged[key] = value
        return merged

    @staticmethod
    def _fallback_report(payload: dict[str, Any]) -> dict[str, Any]:
        run: TestRun = payload["run"]
        analysis: StaticAnalysisResult | None = payload["analysis"]
        defects: list[Defect] = payload["defects"]
        metrics: dict[str, Any] = payload["metrics"]
        if ReportService._is_pwad_crash(run):
            return ReportService._pwad_crash_report(payload)
        outcome = ReportService._display_outcome(run, defects)
        passed = run.status == "completed" and run.outcome == "map_completed"
        outcome_sentence = "The map was completed." if passed else f"The run ended with outcome '{outcome}'."
        defect_phrase = "No defects were detected." if not defects else f"{len(defects)} defect(s) were detected."
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
        secret_pass = bool((analysis and analysis.secret_sector_count == 0) or (run.secrets_found or 0) > 0)
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
        recording_note = (
            f" Recording quality status: {recording_meta.get('quality_status', 'unknown')}; "
            f"{recording_meta.get('frame_count', 0)} frames, "
            f"{recording_meta.get('unique_frame_count', 0)} unique frames, "
            f"{recording_meta.get('duration_seconds', 0)} seconds at {recording_meta.get('fps', 'unknown')} FPS."
        )
        progress_note = (
            f" Agent progress score: {progress_metrics.get('progress_score', 0)} with "
            f"{progress_metrics.get('meaningful_progress_events', 0)} meaningful progress event(s). "
            f"Quality flags: {quality_flags.get('quality_status', 'unknown')}."
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
            "test_environment_summary": (
                f"The run used IWAD {run.iwad_used}, difficulty {run.difficulty_level}, "
                f"model {run.llm_model}, and a maximum budget of {run.max_ticks} game ticks."
            ),
            "hardware_spec": {
                "runner": "Local backend host",
                "rendering": "ViZDoom offscreen frame capture",
                "database": "PostgreSQL run history and telemetry store",
            },
            "software_spec": {
                "backend": "FastAPI",
                "game_runtime": "ViZDoom through MCP",
                "report_renderer": "WeasyPrint PDF generation",
                "agent_model": run.llm_model,
            },
            "variances_from_plan": (
                "The run finished inside the requested tick budget."
                if run.status == "completed"
                else f"The run did not complete normally: {run.error_message or outcome}."
            ),
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
                "secret_coverage": "PASS" if secret_pass else "FAIL",
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
                    else f"{run.secrets_found or 0} secret(s) found."
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
        }

    @staticmethod
    def _is_pwad_crash(run: TestRun) -> bool:
        return run.failure_category == "pwad_crash" or run.outcome == "pwad_crash"

    @staticmethod
    def _pwad_crash_report(payload: dict[str, Any]) -> dict[str, Any]:
        run: TestRun = payload["run"]
        analysis: StaticAnalysisResult | None = payload["analysis"]
        defects: list[Defect] = payload["defects"]
        metrics: dict[str, Any] = payload["metrics"]
        analysis_phrase = ReportService._analysis_phrase(analysis)
        diagnostic = run.error_message or run.failure_summary or "No raw runtime error was stored."
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
                f"The run used IWAD {run.iwad_used}, difficulty {run.difficulty_level}, "
                f"model {run.llm_model}, and a maximum budget of {run.max_ticks} game ticks. "
                f"Failure stage: {run.failure_stage or 'runtime initialization'}."
            ),
            "hardware_spec": {
                "runner": "Local backend host",
                "rendering": "ViZDoom offscreen frame capture",
                "database": "PostgreSQL run history and telemetry store",
            },
            "software_spec": {
                "backend": "FastAPI",
                "game_runtime": "ViZDoom through MCP",
                "report_renderer": "WeasyPrint PDF generation",
                "agent_model": run.llm_model,
            },
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
        if run.outcome == "timeout" and any(defect.defect_type == "softlock_navigation" for defect in defects):
            return "stuck"
        return run.outcome or run.status

    @staticmethod
    def _covered_objectives(run: TestRun, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        covered = [
            {"objective": "Map launch and initial state capture", "evidence": f"Run status: {run.status}."},
            {"objective": "Director decision logging", "evidence": f"{metrics['event_count']} decision event(s) recorded."},
        ]
        if metrics["position_sample_count"]:
            covered.append(
                {
                    "objective": "Movement telemetry",
                    "evidence": f"{metrics['position_sample_count']} position sample(s) across {metrics['position_cluster_count']} cluster(s).",
                }
            )
        if run.recording_mp4_path:
            covered.append({"objective": "Gameplay recording", "evidence": run.recording_mp4_path})
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
        if metrics["max_secrets"] in (None, 0):
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
            "recording_mp4_path",
            "recording_metadata",
            "progress_metrics",
            "agent_quality_flags",
        ]
        return {key: getattr(run, key) for key in keys}

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
            "map_overview_png_path",
        ]
        return {key: getattr(analysis, key) for key in keys}

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
        return {"tick": position.tick_number, "x": position.x, "y": position.y, "health": position.health}

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
        display_decisions = payload.get("decisions", [])[:40]
        defect_omitted_count = max(len(payload["defects"]) - len(display_defects), 0)
        display_outcome = ReportService._display_outcome(payload["run"], payload["defects"])
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
        return Template(
            """
            <html>
            <head>
              <style>
                @page { size: A4; margin: 18mm 16mm; }
                @page appendix { size: A4 landscape; margin: 12mm; }
                body { font-family: sans-serif; color: #1f2933; font-size: 11px; line-height: 1.45; }
                h1 { font-size: 24px; margin: 0 0 4px; page-break-after: avoid; }
                h2 { font-size: 15px; margin: 18px 0 8px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; page-break-after: avoid; }
                h3 { font-size: 12px; margin: 10px 0 4px; page-break-after: avoid; }
                p { margin: 0 0 7px; }
                table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 10px; table-layout: fixed; }
                thead { display: table-header-group; }
                tr { page-break-inside: avoid; break-inside: avoid; }
                th, td { border: 1px solid #d7dee8; padding: 5px; vertical-align: top; overflow-wrap: anywhere; }
                th { background: #eef2f7; text-align: left; }
                .muted { color: #52606d; font-size: 10px; }
                .badge { display: inline-block; padding: 2px 6px; border: 1px solid #9fb3c8; border-radius: 3px; font-size: 10px; margin: 0 3px 4px 0; }
                .verdict-PASS { border-color: #39a35b; }
                .verdict-FAIL { border-color: #c94b4b; }
                .verdict-PARTIAL, .verdict-LIMITED { border-color: #c3912f; }
                ul { margin-top: 4px; padding-left: 16px; }
                li { margin-bottom: 4px; }
                .section { page-break-inside: avoid; }
                .appendix { page: appendix; page-break-before: always; }
                .appendix table { table-layout: fixed; font-size: 8.5px; page-break-inside: auto; }
                .appendix td, .appendix th { padding: 4px; word-break: break-word; overflow-wrap: anywhere; }
                .decision-card { border: 1px solid #d7dee8; padding: 6px; margin: 0 0 6px; break-inside: avoid; page-break-inside: avoid; }
                .decision-meta { color: #52606d; font-size: 8.5px; margin-bottom: 2px; }
                .mono { font-family: monospace; font-size: 8.5px; }
              </style>
            </head>
            <body>
              <h1>Doom PWAD QA Report</h1>
              <p class="muted">Run {{ run.id }} | Map {{ run.map_name }} | Outcome {{ display_outcome }}</p>

              {% if report.report_purpose or report.pass_fail_summary or report.problem_and_escalation %}
              <div class="section">
                <h2>Executive Summary</h2>
                {% if report.report_purpose %}<p>{{ report.report_purpose }}</p>{% endif %}
                {% if report.pass_fail_summary %}
                <p><strong>Pass/fail:</strong>
                {% for key in verdict_keys %}
                  {% if report.pass_fail_summary.get(key) %}
                  <span class="badge verdict-{{ report.pass_fail_summary.get(key) }}">{{ key }}: {{ report.pass_fail_summary.get(key) }}</span>
                  {% endif %}
                {% endfor %}
                </p>
                <ul>
                {% for key in rationale_keys %}
                  {% if report.pass_fail_summary.get(key) %}<li>{{ report.pass_fail_summary.get(key) }}</li>{% endif %}
                {% endfor %}
                </ul>
                {% endif %}
                {% if report.problem_and_escalation %}<p>{{ report.problem_and_escalation }}</p>{% endif %}
              </div>
              {% endif %}

              {% if report.test_items_summary or report.test_environment_summary %}
              <h2>Test Item And Environment</h2>
              {% if report.test_items_summary %}<p>{{ report.test_items_summary }}</p>{% endif %}
              {% if report.test_environment_summary %}<p>{{ report.test_environment_summary }}</p>{% endif %}
              <table>
                <tr><th>Metric</th><th>Value</th><th>Metric</th><th>Value</th></tr>
                <tr><td>Status</td><td>{{ run.status }}</td><td>Duration</td><td>{{ run.duration_seconds }}</td></tr>
                <tr><td>Actions</td><td>{{ run.total_actions_taken }}</td><td>LLM calls</td><td>{{ run.total_llm_calls }}</td></tr>
                <tr><td>Final HP</td><td>{{ run.final_hp }}</td><td>Kills</td><td>{{ run.total_kills }}</td></tr>
                <tr><td>Position samples</td><td>{{ metrics.position_sample_count }}</td><td>Movement units</td><td>{{ metrics.movement_distance_units }}</td></tr>
                <tr><td>Recording</td><td colspan="3">{{ run.recording_mp4_path or "Not produced" }}</td></tr>
              </table>
              {% endif %}

              <h2>Recording And Agent Quality</h2>
              <table>
                <tr><th>Recording</th><th>Value</th><th>Agent progress</th><th>Value</th></tr>
                <tr><td>Status</td><td>{{ metrics.recording_metadata.quality_status or "unknown" }}</td><td>Progress score</td><td>{{ metrics.progress_metrics.progress_score or 0 }}</td></tr>
                <tr><td>Frames</td><td>{{ metrics.recording_metadata.frame_count or 0 }} total / {{ metrics.recording_metadata.unique_frame_count or 0 }} unique</td><td>Meaningful progress</td><td>{{ metrics.progress_metrics.meaningful_progress_events or 0 }}</td></tr>
                <tr><td>Video shape</td><td>{{ metrics.recording_metadata.width or "?" }} x {{ metrics.recording_metadata.height or "?" }} @ {{ metrics.recording_metadata.fps or "?" }} FPS</td><td>Completed objects</td><td>{{ metrics.progress_metrics.completed_object_count or 0 }}</td></tr>
                <tr><td>Gameplay time</td><td>{{ metrics.recording_metadata.gameplay_seconds or "?" }}s, {{ metrics.recording_metadata.advanced_game_ticks or 0 }} tic(s)</td><td>Quality flags</td><td>{{ metrics.agent_quality_flags.quality_status or "unknown" }}</td></tr>
              </table>
              {% if metrics.recording_metadata.validation_warnings or metrics.agent_quality_flags.warnings %}
              <p><strong>Quality warnings:</strong>
              {% for item in metrics.recording_metadata.validation_warnings or [] %}<span class="badge verdict-FAIL">{{ item }}</span>{% endfor %}
              {% for item in metrics.agent_quality_flags.warnings or [] %}<span class="badge verdict-FAIL">{{ item }}</span>{% endfor %}
              </p>
              {% endif %}

              <h2>Static Analysis Context</h2>
              {% if analysis %}
              <table>
                <tr><th>Metric</th><th>Raw WAD</th><th>Difficulty {{ run.difficulty_level }}</th><th>Notes</th></tr>
                <tr>
                  <td>Enemies</td>
                  <td>{{ metrics.raw_enemy_count }}</td>
                  <td>{{ metrics.spawned_enemy_count }}</td>
                  <td>{{ metrics.hidden_enemy_count }} hidden by skill/multiplayer flags</td>
                </tr>
                <tr>
                  <td>Items</td>
                  <td>{{ metrics.raw_item_count }}</td>
                  <td>{{ metrics.spawned_item_count }}</td>
                  <td>{{ metrics.hidden_item_count }} hidden by skill/multiplayer flags</td>
                </tr>
                <tr><td>Secrets</td><td>{{ analysis.secret_sector_count }}</td><td>{{ analysis.secret_sector_count }}</td><td>Sector special 9</td></tr>
                <tr><td>Geometry</td><td>{{ analysis.linedef_count }} linedefs</td><td>{{ analysis.sector_count }} sectors</td><td>{{ analysis.map_width_units or "?" }} x {{ analysis.map_height_units or "?" }} units</td></tr>
              </table>
              <p>Selected-difficulty estimate: {{ metrics.selected_skill_summary.estimated_difficulty or "unknown" }}. Health ratio: {{ metrics.selected_skill_summary.health_ratio }}. Ammo ratio: {{ metrics.selected_skill_summary.ammo_ratio }}.</p>
              {% else %}
              <p>Static analysis was unavailable for this run.</p>
              {% endif %}

              {% if report.test_coverage_evaluation or report.objectives_covered or report.objectives_omitted or report.uncovered_attributes %}
              <h2>Coverage Evaluation</h2>
              {% if report.test_coverage_evaluation %}<p>{{ report.test_coverage_evaluation }}</p>{% endif %}
              {% if report.objectives_covered %}
              <h3>Objectives Covered</h3>
              <ul>{% for item in report.objectives_covered %}<li><strong>{{ item.objective }}:</strong> {{ item.evidence or item.status or item.assessment or "" }}</li>{% endfor %}</ul>
              {% endif %}
              {% if report.objectives_omitted %}
              <h3>Objectives Omitted</h3>
              <ul>{% for item in report.objectives_omitted %}<li><strong>{{ item.objective }}:</strong> {{ item.reason or item.evidence or item.status or "" }}</li>{% endfor %}</ul>
              {% endif %}
              {% if report.uncovered_attributes %}<p><strong>Uncovered attributes:</strong> {{ report.uncovered_attributes }}</p>{% endif %}
              {% endif %}

              {% if report.defect_summary_narrative or report.defect_patterns or defects or report.risk_areas %}
              <h2>Defects And Risks</h2>
              {% if report.defect_summary_narrative %}<p>{{ report.defect_summary_narrative }}</p>{% endif %}
              {% if report.defect_patterns %}<p><strong>Patterns:</strong> {{ report.defect_patterns }}</p>{% endif %}
              {% if defects %}
              {% if defect_omitted_count %}
              <p class="muted">Showing the first {{ defects|length }} defects; {{ defect_omitted_count }} additional deduplicated defects are stored in the API.</p>
              {% endif %}
              <table>
                <tr><th>Severity</th><th>Priority</th><th>Type</th><th>Tick</th><th>Description</th></tr>
                {% for defect in defects %}
                <tr>
                  <td>{{ defect.severity }}</td>
                  <td>{{ defect.priority }}</td>
                  <td>{{ defect.defect_type }}</td>
                  <td>{{ defect.detected_at_tick }}</td>
                  <td><strong>{{ defect.title }}</strong><br>{{ defect.description }}</td>
                </tr>
                {% endfor %}
              </table>
              {% else %}
              <p>No defects are currently attached to this run.</p>
              {% endif %}
              {% if report.risk_areas %}
              <h3>Risk Areas</h3>
              <ul>{% for item in report.risk_areas %}<li><strong>{{ item.area }}:</strong> {{ item.risk }} {{ item.reason or "" }}</li>{% endfor %}</ul>
              {% endif %}
              {% endif %}

              {% if report.major_activities_summary or report.activity_variances %}
              <h2>Activity Log Summary</h2>
              {% if report.major_activities_summary %}<p>{{ report.major_activities_summary }}</p>{% endif %}
              {% if report.activity_variances %}<p>{{ report.activity_variances }}</p>{% endif %}
              {% endif %}

              {% if report.test_item_limitations or report.good_quality_areas %}
              <h2>Limitations And Recommendations</h2>
              {% if report.test_item_limitations %}<p>{{ report.test_item_limitations }}</p>{% endif %}
              {% if report.good_quality_areas %}
              <h3>Good Quality Areas</h3>
              <ul>{% for item in report.good_quality_areas %}<li><strong>{{ item.area }}:</strong> {{ item.evidence or item.assessment or "" }}</li>{% endfor %}</ul>
              {% endif %}
              {% endif %}

              {% if event_rows or decisions %}
              <div class="appendix">
              <h2>Evidence Appendix</h2>
              {% if event_rows %}
              <h3>Notable Event Trace</h3>
              <table>
                <thead><tr><th style="width: 8%">Tick</th><th style="width: 12%">Event</th><th style="width: 14%">Position</th><th style="width: 6%">HP</th><th style="width: 18%">MCP Action</th><th>Stop reason</th></tr></thead>
                <tbody>
                {% for event in event_rows %}
                <tr>
                  <td>{{ event.tick }}</td>
                  <td>{{ event.event_type }}</td>
                  <td>{{ event.position }}</td>
                  <td>{{ event.health }}</td>
                  <td>{{ event.tool }}</td>
                  <td>{{ event.stop_reason or "" }}</td>
                </tr>
                {% endfor %}
                </tbody>
              </table>
              {% endif %}

              {% if decisions %}
              <h3>LLM/MCP Decision Trace</h3>
                {% for decision in decisions %}
                <div class="decision-card">
                  <div class="decision-meta">#{{ decision.sequence_number }} | ticks {{ decision.tick_before }} -> {{ decision.tick_after }} | tool <span class="mono">{{ decision.mcp_tool or "" }}</span> | stop <span class="mono">{{ decision.mcp_stop_reason or "" }}</span></div>
                  <div>{{ decision.reasoning_summary or "" }}</div>
                </div>
                {% endfor %}
              {% endif %}
              </div>
              {% endif %}
            </body>
            </html>
            """
        ).render(
            run=payload["run"],
            analysis=payload["analysis"],
            defects=display_defects,
            decisions=display_decisions,
            defect_omitted_count=defect_omitted_count,
            event_rows=event_rows,
            metrics=payload["metrics"],
            report=report,
            verdict_keys=verdict_keys,
            rationale_keys=rationale_keys,
            display_outcome=display_outcome,
        )
