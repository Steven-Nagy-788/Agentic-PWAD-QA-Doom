from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from jinja2 import Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.core.config import get_settings
from app.models import Defect, GameEvent, StaticAnalysisResult, TestReport, TestRun
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
        if existing is not None:
            return existing
        run = await self.db.get(TestRun, run_id)
        if run is None:
            raise ValueError("Run not found")
        analysis = await self.db.get(StaticAnalysisResult, run.static_analysis_id) if run.static_analysis_id else None
        defects = (await self.db.execute(select(Defect).where(Defect.run_id == run_id))).scalars().all()
        events = (await self.db.execute(select(GameEvent).where(GameEvent.run_id == run_id).order_by(GameEvent.tick_number))).scalars().all()
        notable = [event for event in events if event.event_type != "normal"][:20]
        payload = {
            "run": run,
            "analysis": analysis,
            "defects": list(defects),
            "notable_events": notable,
            "first_ticks": list(events[:5]),
            "last_ticks": list(events[-5:]),
        }
        report_json = await self._call_gemini_or_fallback(payload)
        pdf_path = self._render_pdf(run_id, report_json, payload)
        report = TestReport(
            run_id=run_id,
            report_purpose=report_json.get("report_purpose"),
            test_items_summary=report_json.get("test_items_summary"),
            test_environment_summary=report_json.get("test_environment_summary"),
            defect_summary_narrative=report_json.get("defect_summary_narrative"),
            pass_fail_summary=report_json.get("pass_fail_summary"),
            pdf_path=str(pdf_path),
            generation_status="complete",
            elapsed_time_seconds=run.duration_seconds,
            total_actions_taken=run.total_actions_taken,
        )
        created = await self.repo.create(report)
        await RunRepository(self.db).update(run, report_pdf_path=str(pdf_path))
        return created

    async def _call_gemini_or_fallback(self, payload: dict) -> dict:
        prompt = report_prompt_path().read_text()
        compact = {
            "run": {k: str(v) for k, v in payload["run"].__dict__.items() if not k.startswith("_")},
            "defect_count": len(payload["defects"]),
            "notable_event_count": len(payload["notable_events"]),
        }
        if not self.settings.gemini_api_key:
            return self._fallback_report(payload)
        try:
            from google import genai

            client = genai.Client(api_key=self.settings.gemini_api_key)
            response = client.models.generate_content(
                model=self.settings.llm_model,
                contents=f"{prompt}\n\nDATA:\n{json.dumps(compact, default=str)}",
            )
            text = response.text or "{}"
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start : end + 1])
        except Exception:
            return self._fallback_report(payload)

    @staticmethod
    def _fallback_report(payload: dict) -> dict:
        run = payload["run"]
        defects = payload["defects"]
        return {
            "report_purpose": "Automated QA report for a Doom PWAD test run.",
            "test_items_summary": f"Map {run.map_name} was tested by an autonomous agent.",
            "test_environment_summary": f"IWAD {run.iwad_used}, model {run.llm_model}.",
            "defect_summary_narrative": f"{len(defects)} defects were detected.",
            "pass_fail_summary": {"map_completed": "PASS" if run.outcome == "map_completed" else "FAIL"},
        }

    def _render_pdf(self, run_id: UUID, report: dict, payload: dict) -> Path:
        self.settings.report_storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.report_storage_dir / f"{run_id}.pdf"
        html = Template(
            """
            <html><body>
            <h1>Doom PWAD QA Report</h1>
            <h2>Purpose</h2><p>{{ report.report_purpose }}</p>
            <h2>Summary</h2><p>{{ report.test_items_summary }}</p>
            <h2>Environment</h2><p>{{ report.test_environment_summary }}</p>
            <h2>Defects</h2><p>{{ report.defect_summary_narrative }}</p>
            <ul>{% for defect in defects %}<li>{{ defect.severity }} - {{ defect.title }}: {{ defect.description }}</li>{% endfor %}</ul>
            </body></html>
            """
        ).render(report=report, defects=payload["defects"])
        HTML(string=html).write_pdf(path)
        return path
