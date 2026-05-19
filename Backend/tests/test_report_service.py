from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.report_service import ReportService


def test_report_section_normalization_handles_string_objectives() -> None:
    normalized = ReportService._normalize_report_sections(
        {
            "objectives_covered": ["Navigate to map exit"],
            "objectives_omitted": ["Combat - no enemies spawned at this difficulty"],
            "risk_areas": ["Difficulty flags: raw enemies are hidden"],
            "good_quality_areas": [{"area": "Runtime", "assessment": "Run completed"}],
        }
    )

    assert normalized["objectives_covered"] == [{"objective": "Navigate to map exit"}]
    assert normalized["objectives_omitted"] == [
        {"objective": "Combat", "reason": "no enemies spawned at this difficulty"}
    ]
    assert normalized["risk_areas"] == [{"area": "Difficulty flags", "risk": "raw enemies are hidden"}]
    assert normalized["good_quality_areas"][0]["assessment"] == "Run completed"


def test_pdf_html_does_not_render_blank_objective_labels() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        map_name="E1M1",
        outcome="map_completed",
        status="completed",
        duration_seconds=3,
        total_actions_taken=1,
        total_llm_calls=1,
        final_hp=100,
        total_kills=0,
        recording_mp4_path=None,
        difficulty_level=5,
    )
    analysis = SimpleNamespace(
        secret_sector_count=0,
        linedef_count=4,
        sector_count=1,
        map_width_units=128,
        map_height_units=128,
    )
    event = SimpleNamespace(
        tick_number=1,
        event_type="map_exit",
        player_x=0.0,
        player_y=0.0,
        health=100,
        action_taken={
            "mcp_tool": "explore",
            "mcp_output": {"action_summary": {"stop_reason": "episode_finished"}},
        },
    )
    report = ReportService._normalize_report_sections(
        {
            "report_purpose": "Autonomous QA run.",
            "pass_fail_summary": {"map_navigation": "PASS", "navigation_rationale": "Exit reached."},
            "objectives_covered": ["Navigate to map exit"],
            "objectives_omitted": [],
            "risk_areas": [],
            "good_quality_areas": ["Runtime: completed"],
        }
    )
    payload = {
        "run": run,
        "analysis": analysis,
        "defects": [],
        "notable_events": [event],
        "metrics": {
            "position_sample_count": 1,
            "movement_distance_units": 10.0,
            "raw_enemy_count": 8,
            "spawned_enemy_count": 0,
            "hidden_enemy_count": 8,
            "raw_item_count": 1,
            "spawned_item_count": 1,
            "hidden_item_count": 0,
            "selected_skill_summary": {"estimated_difficulty": "easy", "health_ratio": 0, "ammo_ratio": 0},
        },
    }

    html = ReportService._render_pdf_html(report, payload)

    assert "<strong>:</strong>" not in html
    assert "Navigate to map exit" in html
    assert "episode_finished" in html


def test_report_voice_sanitizer_avoids_agent_blame() -> None:
    sanitized = ReportService._sanitize_report_voice(
        {
            "summary": "The agent failed to engage enemies. The agent was unable to reach the exit.",
            "items": ["agent could not open the door", "agentic QA remains valid"],
        }
    )

    assert "agent failed" not in sanitized["summary"].lower()
    assert "agent was unable" not in sanitized["summary"].lower()
    assert "automated playthrough did not engage enemies" in sanitized["summary"]
    assert sanitized["items"][1] == "agentic QA remains valid"


def test_pwad_crash_report_is_first_class_qa_output() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        wad_file_id=uuid4(),
        map_name="E1M1",
        difficulty_level=3,
        iwad_used="freedoom1",
        llm_model="gemini-test",
        max_ticks=500,
        status="failed",
        outcome="pwad_crash",
        error_message="Map E1M1 could not be loaded safely by ViZDoom.",
        failure_category="pwad_crash",
        failure_stage="startup",
        failure_summary="PWAD crashed or failed to initialize under the configured ViZDoom/Freedoom test environment.",
        duration_seconds=None,
        total_actions_taken=0,
    )
    payload = {
        "run": run,
        "analysis": None,
        "defects": [],
        "metrics": {"event_count": 0, "position_sample_count": 0},
    }

    report = ReportService._pwad_crash_report(payload)

    assert report["pass_fail_summary"]["overall_verdict"] == "FAIL"
    assert "valid QA outcome" in report["report_purpose"]
    assert "No recording is expected" in str(report["objectives_omitted"])
