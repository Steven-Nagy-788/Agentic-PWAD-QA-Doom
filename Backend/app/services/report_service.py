from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.core.config import get_settings
from app.models import AgentPositionTrail, Defect, GameEvent, StaticAnalysisResult, TestReport, TestRun
from app.repositories.report_repository import ReportRepository
from app.repositories.run_repository import RunRepository
from app.services.prompt_service import report_prompt_path


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = ReportRepository(db)

    async def generate(self, run_id: UUID) -> TestReport:
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
        defects = list((await self.db.execute(select(Defect).where(Defect.run_id == run_id))).scalars().all())
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
        notable = [event for event in events if event.event_type != "normal"][:20]
        payload = {
            "run": run,
            "analysis": analysis,
            "defects": defects,
            "events": events,
            "notable_events": notable,
            "first_ticks": list(events[:5]),
            "last_ticks": list(events[-5:]),
            "position_trail": positions,
            "metrics": self._build_metrics(run, events, positions),
        }
        report_json = await self._call_gemini_or_fallback(payload)
        pdf_path = self._render_pdf(run_id, report_json, payload)
        fields = self._report_fields(run, report_json, pdf_path)
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
            "objectives_planned": ReportService._coerce_json_value(json_value("objectives_planned")),
            "objectives_covered": ReportService._coerce_json_value(json_value("objectives_covered")),
            "objectives_omitted": ReportService._coerce_json_value(json_value("objectives_omitted")),
            "uncovered_attributes": text_value("uncovered_attributes"),
            "test_process_changes": text_value("test_process_changes"),
            "defect_summary_narrative": text_value("defect_summary_narrative"),
            "defect_patterns": text_value("defect_patterns"),
            "test_item_limitations": text_value("test_item_limitations"),
            "dropped_features": text_value("dropped_features"),
            "pass_fail_summary": ReportService._coerce_json_object(json_value("pass_fail_summary")),
            "risk_areas": ReportService._coerce_json_value(json_value("risk_areas")),
            "good_quality_areas": ReportService._coerce_json_value(json_value("good_quality_areas")),
            "major_activities_summary": text_value("major_activities_summary"),
            "activity_variances": text_value("activity_variances"),
            "elapsed_time_seconds": report_json.get("elapsed_time_seconds") or run.duration_seconds,
            "total_actions_taken": report_json.get("total_actions_taken") or run.total_actions_taken,
            "pdf_path": str(pdf_path),
        }

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
    def _build_metrics(
        run: TestRun,
        events: list[GameEvent],
        positions: list[AgentPositionTrail],
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
        return {
            "event_count": len(events),
            "position_sample_count": len(positions),
            "position_cluster_count": len(clusters),
            "movement_distance_units": round(movement_distance, 1),
            "event_type_counts": event_type_counts,
            "action_counts": action_counts,
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
        }
        if not self.settings.gemini_api_key:
            return fallback
        try:
            from google import genai

            client = genai.Client(api_key=self.settings.gemini_api_key)
            response = client.models.generate_content(
                model=self.settings.llm_model,
                contents=f"{prompt}\n\nDATA:\n{json.dumps(compact, default=str)}",
            )
            text = response.text or "{}"
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
            if value not in (None, "", [], {}):
                merged[key] = value
        return merged

    @staticmethod
    def _fallback_report(payload: dict[str, Any]) -> dict[str, Any]:
        run: TestRun = payload["run"]
        analysis: StaticAnalysisResult | None = payload["analysis"]
        defects: list[Defect] = payload["defects"]
        metrics: dict[str, Any] = payload["metrics"]
        outcome = run.outcome or run.status
        passed = run.status == "completed" and run.outcome == "map_completed"
        completed = "completed" if passed else f"ended with outcome '{outcome}'"
        defect_phrase = "No defects were detected." if not defects else f"{len(defects)} defect(s) were detected."
        coverage_phrase = (
            f"The agent recorded {metrics['event_count']} decision events, "
            f"{metrics['position_sample_count']} movement samples, "
            f"{metrics['position_cluster_count']} position cluster(s), and "
            f"{metrics['movement_distance_units']} map units of movement."
        )
        analysis_phrase = ReportService._analysis_phrase(analysis)
        major_risk = ReportService._major_risk(run, defects, metrics)

        return {
            "report_purpose": (
                "Document the automated agentic QA run, combine static map analysis with live play telemetry, "
                "and give map authors concrete evidence about completion, traversal, combat, and defects."
            ),
            "intended_audience": "Doom PWAD authors, level designers, QA engineers, and release owners.",
            "problem_and_escalation": ReportService._problem_statement(run, defects, metrics),
            "test_items_summary": (
                f"Test item: {run.map_name} from WAD {run.wad_file_id}. "
                f"Static analysis context: {analysis_phrase}"
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
                "No manual gameplay intervention was used. The report reflects autonomous agent decisions and MCP telemetry."
            ),
            "test_case_variances": (
                "Coverage depth depends on available agent time, LLM decisions, and whether the map exposes progression cues."
            ),
            "test_coverage_evaluation": f"{coverage_phrase} {completed}.",
            "objectives_planned": [
                {"objective": "Validate the map starts correctly in single-player QA mode.", "status": "planned"},
                {"objective": "Exercise live traversal and combat using static analysis as agent context.", "status": "planned"},
                {"objective": "Capture gameplay video, position history, events, defects, and a PDF report.", "status": "planned"},
            ],
            "objectives_covered": ReportService._covered_objectives(run, metrics),
            "objectives_omitted": ReportService._omitted_objectives(run, metrics),
            "uncovered_attributes": ReportService._uncovered_attributes(run, metrics),
            "test_process_changes": (
                "Compound MCP actions now return per-action telemetry frames so movement, position trail, and recording "
                "coverage are sampled during gameplay rather than only after each LLM decision."
            ),
            "defect_summary_narrative": f"{defect_phrase} {major_risk}",
            "defect_patterns": ReportService._defect_patterns(defects),
            "test_item_limitations": ReportService._test_limitations(run, metrics),
            "dropped_features": "None.",
            "pass_fail_summary": {
                "map_completion": "PASS" if passed else "FAIL",
                "agent_survival": "PASS" if (run.final_hp or 0) > 0 else "FAIL",
                "runtime_status": run.status,
                "outcome": outcome,
                "evidence_quality": "PASS" if metrics["position_sample_count"] >= 3 else "LIMITED",
            },
            "risk_areas": ReportService._risk_areas(run, defects, metrics),
            "good_quality_areas": ReportService._good_quality_areas(run, metrics, analysis),
            "major_activities_summary": (
                f"The pipeline statically analyzed the map, launched a ViZDoom MCP session, executed "
                f"{run.total_actions_taken or metrics['event_count']} agent action(s), collected event and position "
                "telemetry, finalized recording artifacts, detected defects, and generated this report."
            ),
            "activity_variances": (
                "Run data is sparse; treat gameplay conclusions as preliminary."
                if metrics["event_count"] < 3
                else "Run data includes multiple gameplay samples and can support concrete QA conclusions."
            ),
            "elapsed_time_seconds": run.duration_seconds,
            "total_actions_taken": run.total_actions_taken,
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
        if run.status == "failed":
            return f"The QA pipeline failed before producing a complete gameplay verdict: {run.error_message or run.outcome}."
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
            covered.append({"objective": "Gameplay recording", "evidence": run.recording_mp4_path})
        return covered

    @staticmethod
    def _omitted_objectives(run: TestRun, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        omitted: list[dict[str, Any]] = []
        if run.outcome != "map_completed":
            omitted.append({"objective": "Verified map exit", "reason": f"Run outcome was {run.outcome or run.status}."})
        if metrics["position_cluster_count"] < 3:
            omitted.append({"objective": "Broad spatial coverage", "reason": "The agent did not visit at least three coarse map areas."})
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
            limitations.insert(0, "The run ended in a pipeline error, so gameplay coverage is incomplete.")
        if metrics["position_sample_count"] < 3:
            limitations.insert(0, "Telemetry volume was too low for strong spatial conclusions.")
        return " ".join(limitations)

    @staticmethod
    def _major_risk(run: TestRun, defects: list[Defect], metrics: dict[str, Any]) -> str:
        if run.status == "failed":
            return "Primary risk: the automation pipeline could not complete this run."
        if defects:
            return "Primary risk: at least one detected defect needs author review."
        if metrics["position_cluster_count"] < 3:
            return "Primary risk: coverage is too narrow to prove the whole map is shippable."
        return "Primary risk is low for the paths exercised in this automated run."

    @staticmethod
    def _risk_areas(run: TestRun, defects: list[Defect], metrics: dict[str, Any]) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        if run.status == "failed":
            risks.append({"area": "Pipeline reliability", "risk": run.error_message or "Run failed."})
        if run.outcome != "map_completed":
            risks.append({"area": "Progression", "risk": f"Map exit was not verified; outcome was {run.outcome}."})
        if metrics["position_cluster_count"] < 3:
            risks.append({"area": "Traversal coverage", "risk": "The agent visited too few coarse position clusters."})
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
            "final_hp",
            "final_armor",
            "total_kills",
            "secrets_found",
            "total_items_collected",
            "total_actions_taken",
            "total_llm_calls",
            "recording_mp4_path",
        ]
        return {key: getattr(run, key) for key in keys}

    @staticmethod
    def _analysis_snapshot(analysis: StaticAnalysisResult | None) -> dict[str, Any] | None:
        if analysis is None:
            return None
        keys = [
            "map_name",
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
            "map_overview_png_path",
        ]
        return {key: getattr(analysis, key) for key in keys}

    @staticmethod
    def _event_snapshot(event: GameEvent) -> dict[str, Any]:
        action = event.action_taken or {}
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
            "mcp_params": action.get("mcp_params"),
            "reasoning": (event.llm_reasoning or "")[:500],
        }

    @staticmethod
    def _defect_snapshot(defect: Defect) -> dict[str, Any]:
        return {
            "severity": defect.severity,
            "priority": defect.priority,
            "defect_type": defect.defect_type,
            "title": defect.title,
            "description": defect.description,
            "detected_at_tick": defect.detected_at_tick,
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
        html = Template(
            """
            <html>
            <head>
              <style>
                body { font-family: sans-serif; color: #1f2933; line-height: 1.45; }
                h1 { font-size: 28px; margin: 0 0 6px; }
                h2 { font-size: 17px; margin: 24px 0 8px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }
                h3 { font-size: 13px; margin: 12px 0 4px; }
                p { margin: 0 0 8px; }
                table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 11px; }
                th, td { border: 1px solid #d7dee8; padding: 6px; vertical-align: top; }
                th { background: #eef2f7; text-align: left; }
                .muted { color: #52606d; font-size: 11px; }
                .badge { display: inline-block; padding: 2px 6px; border: 1px solid #9fb3c8; border-radius: 3px; font-size: 11px; }
                ul { margin-top: 4px; }
                li { margin-bottom: 4px; }
              </style>
            </head>
            <body>
              <h1>Doom PWAD QA Report</h1>
              <p class="muted">Run {{ run.id }} | Map {{ run.map_name }} | Outcome {{ run.outcome or run.status }}</p>

              <h2>Executive Summary</h2>
              <p>{{ report.report_purpose }}</p>
              <p><strong>Pass/fail:</strong>
                {% for key, value in (report.pass_fail_summary or {}).items() %}
                  <span class="badge">{{ key }}: {{ value }}</span>
                {% endfor %}
              </p>
              <p>{{ report.problem_and_escalation }}</p>

              <h2>Test Item And Environment</h2>
              <p>{{ report.test_items_summary }}</p>
              <p>{{ report.test_environment_summary }}</p>
              <table>
                <tr><th>Metric</th><th>Value</th><th>Metric</th><th>Value</th></tr>
                <tr><td>Status</td><td>{{ run.status }}</td><td>Duration</td><td>{{ run.duration_seconds }}</td></tr>
                <tr><td>Actions</td><td>{{ run.total_actions_taken }}</td><td>LLM calls</td><td>{{ run.total_llm_calls }}</td></tr>
                <tr><td>Final HP</td><td>{{ run.final_hp }}</td><td>Kills</td><td>{{ run.total_kills }}</td></tr>
                <tr><td>Position samples</td><td>{{ metrics.position_sample_count }}</td><td>Movement units</td><td>{{ metrics.movement_distance_units }}</td></tr>
                <tr><td>Recording</td><td colspan="3">{{ run.recording_mp4_path or "Not produced" }}</td></tr>
              </table>

              <h2>Static Analysis Context</h2>
              {% if analysis %}
              <table>
                <tr><th>Things</th><th>Enemies</th><th>Items</th><th>Keys</th><th>Secrets</th><th>Linedefs</th><th>Sectors</th></tr>
                <tr>
                  <td>{{ analysis.thing_count_total }}</td>
                  <td>{{ analysis.thing_count_enemies }}</td>
                  <td>{{ analysis.thing_count_items }}</td>
                  <td>{{ analysis.thing_count_keys }}</td>
                  <td>{{ analysis.secret_sector_count }}</td>
                  <td>{{ analysis.linedef_count }}</td>
                  <td>{{ analysis.sector_count }}</td>
                </tr>
              </table>
              <p>Estimated difficulty: {{ analysis.estimated_difficulty or "unknown" }}. Health ratio: {{ analysis.health_ratio }}. Ammo ratio: {{ analysis.ammo_ratio }}.</p>
              {% else %}
              <p>Static analysis was unavailable for this run.</p>
              {% endif %}

              <h2>Coverage Evaluation</h2>
              <p>{{ report.test_coverage_evaluation }}</p>
              <h3>Objectives Covered</h3>
              <ul>{% for item in report.objectives_covered or [] %}<li><strong>{{ item.objective }}:</strong> {{ item.evidence }}</li>{% endfor %}</ul>
              <h3>Objectives Omitted</h3>
              <ul>{% for item in report.objectives_omitted or [] %}<li><strong>{{ item.objective }}:</strong> {{ item.reason }}</li>{% endfor %}</ul>
              <p><strong>Uncovered attributes:</strong> {{ report.uncovered_attributes }}</p>

              <h2>Defects And Risks</h2>
              <p>{{ report.defect_summary_narrative }}</p>
              <p><strong>Patterns:</strong> {{ report.defect_patterns }}</p>
              {% if defects %}
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
              <h3>Risk Areas</h3>
              <ul>{% for item in report.risk_areas or [] %}<li><strong>{{ item.area }}:</strong> {{ item.risk }}</li>{% endfor %}</ul>

              <h2>Activity Log Summary</h2>
              <p>{{ report.major_activities_summary }}</p>
              <p>{{ report.activity_variances }}</p>
              {% if notable_events %}
              <table>
                <tr><th>Tick</th><th>Event</th><th>Position</th><th>HP</th><th>Action</th></tr>
                {% for event in notable_events %}
                <tr>
                  <td>{{ event.tick_number }}</td>
                  <td>{{ event.event_type }}</td>
                  <td>{{ "%.1f"|format(event.player_x) }}, {{ "%.1f"|format(event.player_y) }}</td>
                  <td>{{ event.health }}</td>
                  <td>{{ (event.action_taken or {}).get("mcp_tool") }}</td>
                </tr>
                {% endfor %}
              </table>
              {% else %}
              <p>No non-normal gameplay events were recorded.</p>
              {% endif %}

              <h2>Limitations And Recommendations</h2>
              <p>{{ report.test_item_limitations }}</p>
              <h3>Good Quality Areas</h3>
              <ul>{% for item in report.good_quality_areas or [] %}<li><strong>{{ item.area }}:</strong> {{ item.evidence }}</li>{% endfor %}</ul>
            </body>
            </html>
            """
        ).render(
            run=payload["run"],
            analysis=payload["analysis"],
            defects=payload["defects"],
            notable_events=payload["notable_events"],
            metrics=payload["metrics"],
            report=report,
        )
        HTML(string=html).write_pdf(path)
        return path
