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
        recording_metadata={
            "quality_status": "ok",
            "frame_count": 45,
            "unique_frame_count": 40,
            "width": 640,
            "height": 480,
            "fps": 15,
            "advanced_game_ticks": 105,
            "gameplay_seconds": 3.0,
            "validation_warnings": [],
        },
        progress_metrics={
            "progress_score": 3,
            "meaningful_progress_events": 1,
            "completed_object_count": 1,
        },
        agent_quality_flags={"quality_status": "ok", "warnings": []},
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
            "recording_metadata": run.recording_metadata,
            "progress_metrics": run.progress_metrics,
            "agent_quality_flags": run.agent_quality_flags,
        },
        "decisions": [
            SimpleNamespace(
                sequence_number=1,
                tick_before=1,
                tick_after=10,
                mcp_tool="explore",
                mcp_stop_reason="episode_finished",
                reasoning_summary="Short QA-facing decision rationale.",
            )
        ],
    }

    html = ReportService._render_pdf_html(report, payload)

    assert "<strong>:</strong>" not in html
    assert "Navigate to map exit" in html
    assert "episode_finished" in html
    assert "@page appendix" in html
    assert "Evidence Appendix" in html
    assert "decision-card" in html
    assert "Recording And Agent Quality" in html


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


def test_pdf_html_marks_recording_available_from_url_even_with_warning_status() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        map_name="MAP01",
        outcome="timeout",
        status="completed",
        duration_seconds=10,
        total_actions_taken=2,
        total_llm_calls=2,
        final_hp=50,
        total_kills=0,
        secrets_found=0,
        recording_mp4_path="/tmp/run.mp4",
        recording_metadata={"quality_status": "warning", "frame_count": 5},
        progress_metrics={},
        agent_quality_flags={},
        difficulty_level=3,
    )
    payload = {
        "run": run,
        "analysis": None,
        "defects": [],
        "notable_events": [],
        "metrics": {
            "recording_mp4_url": f"/runs/{run.id}/recording",
            "recording_metadata": run.recording_metadata,
            "progress_metrics": {},
            "agent_quality_flags": {},
            "spawned_enemy_count": 0,
        },
        "decisions": [],
    }
    html = ReportService._render_pdf_html({"test_items_summary": "Run summary"}, payload)
    assert "available via API" in html
    assert "Not produced" not in html


def test_uncovered_attributes_do_not_flag_secrets_when_map_has_none() -> None:
    run = SimpleNamespace(outcome="map_completed")
    metrics = {
        "max_secrets": 0,
        "secret_sector_count": 0,
        "coverage_percent": 95.0,
        "position_cluster_count": 4,
    }

    assert ReportService._uncovered_attributes(run, metrics) == "No major attributes remained uncovered by this run."


def test_uncovered_attributes_flag_unfound_secrets_after_high_coverage() -> None:
    run = SimpleNamespace(outcome="map_completed")
    metrics = {
        "max_secrets": 0,
        "secret_sector_count": 2,
        "coverage_percent": 95.0,
        "position_cluster_count": 4,
    }

    assert ReportService._uncovered_attributes(run, metrics) == "secret accessibility"
