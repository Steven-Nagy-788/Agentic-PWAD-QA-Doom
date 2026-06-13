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
        environment_metadata={},
        report_pdf_path=None,
        seed=None,
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
        environment_metadata={},
        report_pdf_path=None,
        seed=None,
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


def test_build_report_llm_input_returns_expected_keys() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)

    assert "run_summary" in result
    assert "static_analysis" in result
    assert "metrics" in result
    assert "defects" in result
    assert "notable_events" in result
    assert "first_ticks" in result
    assert "last_ticks" in result
    assert "decision_trace" in result


def test_run_summary_contains_all_expected_fields() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)
    summary = result["run_summary"]

    assert summary["map_name"] == "E1M1"
    assert summary["iwad_used"] == "freedoom2"
    assert summary["difficulty_level"] == 3
    assert summary["llm_model"] == "gemini-test"
    assert summary["outcome"] == "map_completed"
    assert summary["status"] == "completed"
    assert summary["duration_seconds"] == 15
    assert summary["total_kills"] == 5
    assert summary["final_hp"] == 80
    assert summary["final_armor"] == 25
    assert summary["secrets_found"] == 1
    assert summary["total_items_collected"] == 3
    assert summary["total_actions_taken"] == 4
    assert summary["total_llm_calls"] == 4
    assert summary["max_ticks"] == 3000


def test_run_summary_fills_none_with_zeros() -> None:
    payload = _minimal_payload()
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)
    summary = result["run_summary"]

    assert summary["total_kills"] == 0
    assert summary["secrets_found"] == 0
    assert summary["total_items_collected"] == 0
    assert summary["total_actions_taken"] == 0
    assert summary["total_llm_calls"] == 0


def test_static_analysis_snapshot() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)
    analysis = result["static_analysis"]

    assert analysis is not None
    assert analysis["map_name"] == "E1M1"
    assert analysis["thing_count_enemies"] == 12
    assert analysis["thing_count_items"] == 5


def test_static_analysis_none_when_absent() -> None:
    payload = _minimal_payload()
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)
    assert result["static_analysis"] is None


def test_metrics_section_includes_key_fields() -> None:
    payload = _full_payload()
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)
    metrics = result["metrics"]

    assert metrics["raw_enemy_count"] == 12
    assert metrics["spawned_enemy_count"] == 8
    assert metrics["hidden_enemy_count"] == 4
    assert metrics["raw_item_count"] == 5
    assert metrics["spawned_item_count"] == 3
    assert metrics["hidden_item_count"] == 2
    assert metrics["event_count"] == 2
    assert metrics["decision_count"] == 1
    assert metrics["position_sample_count"] == 3
    assert metrics["position_cluster_count"] == 2
    assert metrics["movement_distance_units"] == 150.5
    assert metrics["coverage_percent"] == 35.0
    assert metrics["fallback_action_count"] == 0
    assert metrics["validation_rejection_count"] == 0


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
    )
    payload = _full_payload()
    payload["defects"] = [defect]
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)

    assert len(result["defects"]) == 1
    snap = result["defects"][0]
    assert snap["severity"] == 1
    assert snap["title"] == "Stuck in corner"
    assert snap["defect_type"] == "softlock_navigation"
    assert snap["detected_at_tick"] == 100
    assert snap["position"] == {"x": 512.0, "y": 256.0}


def test_notable_events_snapshotted() -> None:
    event = SimpleNamespace(
        tick_number=50,
        event_type="kill",
        player_x=100.0,
        player_y=200.0,
        player_angle=90.0,
        health=75,
        armor=10,
        kill_count=1,
        item_count=0,
        secret_count=0,
        damage_received=5,
        action_taken={
            "mcp_tool": "aim_and_shoot",
            "mcp_output": {"action_summary": {"hit": True}},
            "mcp_action_summary": {"hit": True},
            "mcp_params": {},
        },
        llm_reasoning="Shoot the enemy.",
    )
    payload = _full_payload()
    payload["notable_events"] = [event]
    payload["events"] = [event]
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)

    assert len(result["notable_events"]) == 1
    snap = result["notable_events"][0]
    assert snap["tick"] == 50
    assert snap["event_type"] == "kill"
    assert snap["mcp_tool"] == "aim_and_shoot"
    assert snap["reasoning"] == "Shoot the enemy."


def test_decision_trace_snapshotted() -> None:
    decision = SimpleNamespace(
        sequence_number=1,
        tick_before=10,
        tick_after=50,
        status="success",
        reasoning_summary="Move forward.",
        mcp_tool="explore",
        mcp_input={"max_tics": 80},
        mcp_stop_reason="turn_complete",
        decision_source="gemini",
        mcp_output={"action_summary": {"validation_error": None}},
        llm_duration_ms=120.5,
        mcp_duration_ms=30.0,
        error_message=None,
    )
    payload = _full_payload()
    payload["decisions"] = [decision]
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)

    assert len(result["decision_trace"]) == 1
    snap = result["decision_trace"][0]
    assert snap["sequence_number"] == 1
    assert snap["mcp_tool"] == "explore"
    assert snap["decision_source"] == "gemini"
    assert snap["llm_duration_ms"] == 120.5


def test_first_ticks_and_last_ticks_sliced() -> None:
    events = [
        SimpleNamespace(
            tick_number=i, event_type="normal",
            player_x=0.0, player_y=0.0, player_angle=0.0,
            health=100, armor=0, kill_count=0, item_count=0,
            secret_count=0, damage_received=0, action_taken={},
            llm_reasoning=None,
        )
        for i in range(10)
    ]
    payload = _full_payload()
    payload["events"] = events
    service = object.__new__(ReportService)
    result = service._build_report_llm_input(payload)

    assert len(result["first_ticks"]) == 5
    assert result["first_ticks"][0]["tick"] == 0
    assert result["first_ticks"][4]["tick"] == 4
    assert len(result["last_ticks"]) == 5
    assert result["last_ticks"][0]["tick"] == 5
    assert result["last_ticks"][4]["tick"] == 9
