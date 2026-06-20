from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.report_service import ReportService


def _full_payload() -> dict:
    run = SimpleNamespace(
        id=uuid4(),
        map_name="E1M1",
        iwad_used="freedoom2",
        difficulty_level=3,
        llm_model="gemini-test",
        outcome="map_completed",
        status="completed",
        duration_seconds=15,
        total_kills=5,
        total_deaths=0,
        final_hp=80,
        final_armor=25,
        secrets_found=1,
        total_items_collected=3,
        total_actions_taken=4,
        total_llm_calls=4,
        max_ticks=3000,
        wad_file_id=uuid4(),
        recording_mp4_path="/tmp/run.mp4",
        recording_metadata={"quality_status": "ok"},
        progress_metrics={"coverage_percent": 35.0},
        agent_quality_flags={"warnings": []},
        error_message=None,
        failure_summary=None,
        failure_category=None,
        failure_stage=None,
        failure_diagnostics=None,
        behavior_profile=None,
        environment_metadata={},
        report_pdf_path=None,
        seed=None,
        started_at=None,
        completed_at=None,
    )
    analysis = SimpleNamespace(
        map_name="E1M1",
        map_title="Hangar",
        map_display_name="Hangar",
        map_title_source="lump",
        thing_count_total=20,
        thing_count_enemies=12,
        thing_count_items=5,
        thing_count_keys=1,
        thing_count_weapons=2,
        linedef_count=64,
        sector_count=16,
        secret_sector_count=2,
        vertex_count=80,
        map_width_units=2048,
        map_height_units=2048,
        total_monster_hp=240,
        total_health_pickup_pts=50,
        total_armor_pickup_pts=25,
        hitscanner_percent=30.0,
        health_ratio=0.2083,
        ammo_ratio=0.85,
        estimated_difficulty="medium",
        enemy_breakdown={"ZOMBIEMAN": 8, "IMP": 4},
        item_breakdown={"HEALTH": 3, "ARMOR": 2},
        spawn_summary_by_skill={},
        wad_file_id=uuid4(),
        map_overview_png_path=None,
        door_count=2,
        lift_count=1,
        teleporter_count=0,
    )
    metrics = {
        "event_count": 2,
        "decision_count": 1,
        "position_sample_count": 3,
        "position_cluster_count": 2,
        "movement_distance_units": 150.5,
        "raw_enemy_count": 12,
        "spawned_enemy_count": 8,
        "hidden_enemy_count": 4,
        "raw_item_count": 5,
        "spawned_item_count": 3,
        "hidden_item_count": 2,
        "selected_skill_summary": {"health_ratio": 0.2083, "ammo_ratio": 0.85},
        "coverage_percent": 35.0,
        "fallback_action_count": 0,
        "validation_rejection_count": 0,
        "recording_metadata": {"quality_status": "ok"},
        "progress_metrics": {"coverage_percent": 35.0},
        "agent_quality_flags": {"warnings": []},
    }
    return {
        "run": run,
        "analysis": analysis,
        "defects": [],
        "events": [],
        "decisions": [],
        "notable_events": [],
        "first_ticks": [],
        "last_ticks": [],
        "metrics": metrics,
    }


def _minimal_payload() -> dict:
    run = SimpleNamespace(
        id=uuid4(),
        map_name="MAP01",
        iwad_used="freedoom2",
        difficulty_level=3,
        llm_model="gemini-test",
        outcome="timeout",
        status="completed",
        duration_seconds=10,
        total_kills=None,
        total_deaths=None,
        final_hp=100,
        final_armor=0,
        secrets_found=None,
        total_items_collected=None,
        total_actions_taken=None,
        total_llm_calls=None,
        max_ticks=3000,
        wad_file_id=uuid4(),
        recording_mp4_path=None,
        recording_metadata={},
        progress_metrics={},
        agent_quality_flags={},
        error_message=None,
        failure_summary=None,
        failure_category=None,
        failure_stage=None,
        failure_diagnostics=None,
        behavior_profile=None,
        environment_metadata={},
        report_pdf_path=None,
        seed=None,
        started_at=None,
        completed_at=None,
    )
    return {
        "run": run,
        "analysis": None,
        "defects": [],
        "events": [],
        "decisions": [],
        "notable_events": [],
        "first_ticks": [],
        "last_ticks": [],
        "metrics": {
            "event_count": 0,
            "decision_count": 0,
            "position_sample_count": 0,
            "position_cluster_count": 0,
            "movement_distance_units": 0,
            "raw_enemy_count": 0,
            "spawned_enemy_count": 0,
            "hidden_enemy_count": 0,
            "raw_item_count": 0,
            "spawned_item_count": 0,
            "hidden_item_count": 0,
            "selected_skill_summary": {},
            "coverage_percent": None,
            "fallback_action_count": 0,
            "validation_rejection_count": 0,
            "recording_metadata": {},
            "progress_metrics": {},
            "agent_quality_flags": {},
        },
    }


def test_build_raw_data_payload_returns_expected_keys() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)

    assert "run_summary" in result
    assert "static_analysis" in result
    assert "metrics" in result
    assert "defects" in result
    assert "game_events" in result
    assert "decision_trace" in result
    assert "position_trail" in result


def test_run_summary_contains_all_expected_fields() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    summary = result["run_summary"]

    assert summary["map_name"] == "E1M1"
    assert summary["iwad_used"] == "freedoom2"
    assert summary["difficulty_level"] == 3
    assert summary["llm_model"] == "gemini-test"
    assert summary["outcome"] == "map_completed"
    assert summary["status"] == "completed"
    assert summary["duration_seconds"] == 15
    assert summary["total_kills"] == 5
    assert summary["total_deaths"] == 0
    assert summary["final_hp"] == 80
    assert summary["final_armor"] == 25
    assert summary["secrets_found"] == 1
    assert summary["total_items_collected"] == 3
    assert summary["total_actions_taken"] == 4
    assert summary["total_llm_calls"] == 4
    assert summary["max_ticks"] == 3000
    assert summary["behavior_profile"] is None
    assert summary["started_at"] is None


def test_run_summary_preserves_none_values() -> None:
    payload = _minimal_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    summary = result["run_summary"]

    assert summary["total_kills"] is None
    assert summary["secrets_found"] is None
    assert summary["total_items_collected"] is None
    assert summary["total_actions_taken"] is None


def test_static_analysis_snapshot() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    analysis = result["static_analysis"]

    assert analysis is not None
    assert analysis["map_title"] == "Hangar"
    assert analysis["thing_count_enemies"] == 12
    assert analysis["thing_count_items"] == 5
    assert analysis["linedef_count"] == 64


def test_static_analysis_empty_dict_when_absent() -> None:
    payload = _minimal_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    assert result["static_analysis"] == {}


def test_metrics_section_includes_key_fields() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    metrics = result["metrics"]

    assert metrics["raw_enemy_count"] == 12
    assert metrics["spawned_enemy_count"] == 8
    assert metrics["hidden_enemy_count"] == 4
    assert metrics["raw_item_count"] == 5
    assert metrics["spawned_item_count"] == 3
    assert metrics["hidden_item_count"] == 2
    assert metrics["coverage_percent"] == 35.0
    assert metrics["fallback_action_count"] == 0
    assert metrics["position_cluster_count"] == 2


def test_defects_snapshotted() -> None:
    defect = SimpleNamespace(
        severity=1,
        priority=1,
        defect_type="softlock_navigation",
        fingerprint="abc123",
        title="Stuck in corner",
        description="Agent cannot navigate out.",
        detected_at_tick=100,
        first_seen_tick=90,
        last_seen_tick=100,
        occurrence_count=3,
        position_x=512.0,
        position_y=256.0,
        recommendation="Fix geometry.",
        resolution_status="open",
        reproduction_steps=None,
    )
    payload = _full_payload()
    payload["defects"] = [defect]
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)

    assert len(result["defects"]) == 1
    snap = result["defects"][0]
    assert snap["severity"] == 1
    assert snap["title"] == "Stuck in corner"
    assert snap["defect_type"] == "softlock_navigation"
    assert snap["detected_at_tick"] == 100
    assert snap["position_x"] == 512.0
    assert snap["position_y"] == 256.0
    assert snap["occurrence_count"] == 3


def test_game_events_empty_when_no_game_events() -> None:
    payload = _full_payload()
    payload["events"] = []
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    assert result["game_events"] == []


def test_decision_trace_empty_when_no_agent_decisions() -> None:
    payload = _full_payload()
    payload["decisions"] = []
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    assert result["decision_trace"] == []


def test_position_trail_empty_when_no_positions() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    assert result["position_trail"] == []


def test_failure_details_none_when_no_failure() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    assert result["failure_details"] is None


def test_failure_details_populated_when_failure_category_set() -> None:
    payload = _full_payload()
    payload["run"].failure_category = "pwad_crash"
    payload["run"].error_message = "Map failed to load"
    payload["run"].failure_summary = "Init failed"
    payload["run"].failure_stage = "init"
    payload["run"].failure_diagnostics = "error log here"
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    details = result["failure_details"]
    assert details is not None
    assert details["failure_category"] == "pwad_crash"
    assert details["failure_stage"] == "init"
    assert details["error_message"] == "Map failed to load"


def test_map_bounds_none_when_not_provided() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    assert result["map_bounds"] is None


def test_map_bounds_populated_when_provided() -> None:
    payload = _full_payload()
    payload["map_bounds"] = {"min_x": 0, "max_x": 2048, "min_y": 0, "max_y": 1024}
    service = object.__new__(ReportService)
    result = service._build_raw_data_payload(payload)
    bounds = result["map_bounds"]
    assert bounds["min_x"] == 0
    assert bounds["max_x"] == 2048
    assert bounds["min_y"] == 0
    assert bounds["max_y"] == 1024
