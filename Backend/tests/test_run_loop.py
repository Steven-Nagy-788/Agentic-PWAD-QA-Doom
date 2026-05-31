from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import StaticAnalysisResult, TestRun, WadFile
from app.services.mcp_client_service import McpStartupError
from app.services.run_loop import _classify_startup_failure, _estimate_total_map_cells, _execute_tool, _history_position_from_state


def _mock_run():
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.wad_file_id = uuid4()
    run.static_analysis_id = uuid4()
    run.map_name = "MAP01"
    run.difficulty_level = 3
    run.iwad_used = "freedoom2"
    run.llm_model = "gemini-2.5-flash-lite"
    run.max_ticks = 5000
    run.status = "pending"
    run.behavior_profile = "thorough"
    run.started_at = None
    run.completed_at = None
    return run


def _mock_wad():
    wad = MagicMock(spec=WadFile)
    wad.id = uuid4()
    wad.stored_path = "/tmp/test.wad"
    wad.iwad_required = "freedoom2"
    return wad


def _mock_analysis():
    an = MagicMock(spec=StaticAnalysisResult)
    an.id = uuid4()
    an.wad_file_id = uuid4()
    an.map_name = "MAP01"
    an.map_width_units = 512
    an.map_height_units = 512
    return an


def test_estimate_total_map_cells_uses_static_analysis_dimensions() -> None:
    analysis = MagicMock()
    analysis.map_width_units = 513
    analysis.map_height_units = 512
    assert _estimate_total_map_cells(analysis) == 6


def test_startup_failure_classifies_pwad_crash_prefix() -> None:
    outcome, fields = _classify_startup_failure(McpStartupError("PWAD_CRASH: map MAP01 crashed during preflight"))

    assert outcome == "pwad_crash"
    assert fields["failure_category"] == "pwad_crash"
    assert fields["failure_stage"] == "wad_loading"


def test_startup_failure_classifies_infra_timeout_prefix() -> None:
    outcome, fields = _classify_startup_failure(
        McpStartupError("INFRA_TIMEOUT: Map MAP01 could not be loaded safely by ViZDoom")
    )

    assert outcome == "error"
    assert fields["failure_category"] == "infrastructure"
    assert fields["failure_stage"] == "mcp_connect_retry_exhausted"


def test_history_position_uses_uppercase_vizdoom_variables() -> None:
    x, y, angle = _history_position_from_state(
        {"game_variables": {"POSITION_X": 123.5, "POSITION_Y": -42, "ANGLE": 270}}
    )

    assert x == 123.5
    assert y == -42
    assert angle == 270


@pytest.mark.asyncio
async def test_execute_tool_passes_valid_stale_target_to_mcp_unchanged_after_normalization() -> None:
    mcp = AsyncMock()
    mcp.call_tool.return_value = {"game_variables": {"POSITION_X": 0, "POSITION_Y": 0}}
    decision = {"mcp_tool": "aim_and_shoot", "mcp_params": {"object_id": 99, "shots": 2}}

    _, call = await _execute_tool(mcp, decision, {"objects": []})

    mcp.call_tool.assert_awaited_once()
    assert call["tool"] == "aim_and_shoot"
    assert call["input"]["object_id"] == 99


@pytest.mark.asyncio
async def test_execute_tool_rejects_invalid_params_without_fallback_explore() -> None:
    mcp = AsyncMock()
    decision = {"mcp_tool": "move_to", "mcp_params": {}}

    response, call = await _execute_tool(mcp, decision, {"tic": 12, "game_variables": {}})

    mcp.call_tool.assert_not_called()
    assert call["service"] == "backend-validation"
    assert call["tool"] == "move_to"
    assert response["action_summary"]["stop_reason"] == "invalid_params"


@pytest.mark.asyncio
async def test_execute_tool_explore_keeps_technical_defaults_without_runtime_error() -> None:
    mcp = AsyncMock()
    mcp.call_tool.return_value = {"game_variables": {"POSITION_X": 0, "POSITION_Y": 0}}
    decision = {"mcp_tool": "explore", "mcp_params": {}}

    await _execute_tool(mcp, decision)

    mcp.call_tool.assert_awaited_once()
    params = mcp.call_tool.await_args.args[1]
    assert params["max_tics"] == 80
    assert params["stop_on_enemy"] is True
    assert params["stop_on_item"] is True


@pytest.mark.asyncio
async def test_execute_tool_select_weapon_uses_full_settling_window_by_default() -> None:
    mcp = AsyncMock()
    mcp.call_tool.return_value = {"game_variables": {"SELECTED_WEAPON": 2}}
    decision = {"mcp_tool": "select_weapon", "mcp_params": {"weapon_slot": 2}}

    await _execute_tool(mcp, decision)

    params = mcp.call_tool.await_args.args[1]
    assert params["weapon_slot"] == 2
    assert params["max_tics"] == 20


def _base_patches():
    return [
        patch("app.services.run_loop.SessionLocal"),
        patch("app.services.run_loop.McpDoomClient"),
        patch("app.services.run_loop.GeminiService"),
        patch("app.services.run_loop.RecordingService"),
        patch("app.services.run_loop.websocket_service"),
        patch("app.services.run_loop.DefectService"),
        patch("app.services.run_loop.ReportService"),
        patch("app.services.run_loop.WadRepository"),
        patch("app.services.run_loop.RunRepository"),
        patch("app.services.run_loop.get_behavior_profile"),
        patch("app.services.run_loop.render_agent_prompt"),
        patch("app.services.run_loop.RUN_TASKS", {}),
    ]


def _setup_loop_patches():
    return [
        patch("app.services.run_loop._lockstep_should_stop_as_stuck", return_value=False),
        patch("app.services.run_loop._factual_game_tic", return_value=1),
        patch("app.services.run_loop._track_visited_cell"),
        patch("app.services.run_loop._finalize_lockstep_decision"),
        patch("app.services.run_loop._lockstep_progress_metrics", return_value={"progress_score": 0}),
        patch("app.services.run_loop._lockstep_quality_flags", return_value={"quality_status": "unknown"}),
    ]


def _make_session(db):
    sess = AsyncMock()
    sess.__aenter__.return_value = db
    return sess


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock()
    db.execute = AsyncMock(return_value=_empty_result())
    return db


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


def _setup_ws(mock_ws):
    mock_ws.broadcast = AsyncMock()
    mock_ws.cleanup_run = AsyncMock()
    return mock_ws


async def _update_run(run, **fields):
    for key, value in fields.items():
        setattr(run, key, value)
    return run


def _make_mcp(mock_mcp_cls, start_side_effect=None, state_data=None):
    mcp = AsyncMock()
    if start_side_effect:
        mcp.start_game = AsyncMock(side_effect=start_side_effect)
    else:
        mcp.start_game = AsyncMock()
    if state_data is None:
        state_data = {"episode_finished": True, "game_variables": {"x": 0, "y": 0, "health": 100}}
    mcp.get_state = AsyncMock(return_value=(state_data, b""))
    mcp.get_runtime_metadata = AsyncMock(return_value={})
    mcp.stop_game = AsyncMock()
    mock_mcp_cls.return_value.__aenter__.return_value = mcp
    mock_mcp_cls.return_value.__aexit__.return_value = None
    return mcp


def _make_gemini(mock_gemini_cls):
    gemini = AsyncMock()
    gemini.decide = AsyncMock(
        return_value=(
            {
                "reasoning_summary": "Test decision.",
                "mcp_tool": "explore",
                "mcp_params": {},
                "observed_issue": None,
            },
            {"prompt_tokens": 100, "completion_tokens": 50},
        )
    )
    mock_gemini_cls.return_value = gemini
    return gemini


def _make_recorder(mock_rec_cls):
    rec = AsyncMock()
    rec.write_frame = MagicMock()
    rec.finalize = MagicMock(return_value="/tmp/recording.mp4")
    rec.path = MagicMock()
    rec.path.exists.return_value = True
    rec.validate = MagicMock(
        return_value={
            "quality_status": "ok",
            "frame_count": 10,
            "unique_frame_count": 8,
            "fps": 15,
            "width": 640,
            "height": 480,
            "gameplay_seconds": 5,
            "advanced_game_ticks": 100,
        }
    )
    rec.save_screenshot = MagicMock(return_value="/tmp/screenshot.png")
    mock_rec_cls.return_value = rec
    return rec


@pytest.mark.asyncio
async def test_normal_completion():
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()

    with (
        patch("app.services.run_loop.SessionLocal") as mock_session_local,
        patch("app.services.run_loop.McpDoomClient") as mock_mcp_cls,
        patch("app.services.run_loop.GeminiService") as mock_gemini_cls,
        patch("app.services.run_loop.RecordingService") as mock_rec_cls,
        patch("app.services.run_loop.websocket_service") as mock_ws,
        patch("app.services.run_loop.DefectService") as mock_defect_cls,
        patch("app.services.run_loop.ReportService") as mock_report_cls,
        patch("app.services.run_loop.WadRepository") as mock_wad_repo_cls,
        patch("app.services.run_loop.RunRepository") as mock_run_repo_cls,
        patch("app.services.run_loop.get_behavior_profile") as mock_get_profile,
        patch("app.services.run_loop.render_agent_prompt") as mock_render_prompt,
        patch("app.services.run_loop.RUN_TASKS", {}),
        patch("app.services.run_loop._lockstep_should_stop_as_stuck", return_value=False),
        patch("app.services.run_loop._factual_game_tic", return_value=1),
        patch("app.services.run_loop._track_visited_cell"),
        patch("app.services.run_loop._finalize_lockstep_decision"),
        patch("app.services.run_loop._lockstep_progress_metrics", return_value={"progress_score": 0}),
        patch("app.services.run_loop._lockstep_quality_flags", return_value={"quality_status": "unknown"}),
    ):
        db = _make_db()
        db.get.side_effect = lambda cls, id: {TestRun: run, StaticAnalysisResult: analysis}.get(cls)

        mock_session_local.return_value = _make_session(db)
        _setup_ws(mock_ws)

        mock_wad_repo = AsyncMock()
        mock_wad_repo.get_by_id = AsyncMock(return_value=wad)
        mock_wad_repo_cls.return_value = mock_wad_repo

        mock_run_repo = AsyncMock()
        mock_run_repo.update = AsyncMock(side_effect=_update_run)
        mock_run_repo_cls.return_value = mock_run_repo

        _make_mcp(mock_mcp_cls, state_data={"episode_finished": True, "game_variables": {"x": 0, "y": 0, "health": 100}})
        _make_gemini(mock_gemini_cls)
        _make_recorder(mock_rec_cls)

        mock_get_profile.return_value = MagicMock(
            throttle_delays={"combat": 0.5, "low_health": 1.0, "stuck": 2.0, "default": 1.5},
        )
        mock_render_prompt.return_value = "Test prompt."

        mock_defect_svc = AsyncMock()
        mock_defect_svc.detect_for_run = AsyncMock()
        mock_defect_cls.return_value = mock_defect_svc

        mock_report_svc = AsyncMock()
        mock_report_svc.generate = AsyncMock()
        mock_report_cls.return_value = mock_report_svc

        from app.services.run_loop import agent_run_task

        await agent_run_task(run.id)

        mock_wad_repo.get_by_id.assert_awaited_once_with(run.wad_file_id)
        mock_defect_svc.detect_for_run.assert_awaited_once()
        mock_report_svc.generate.assert_awaited_once()
        assert db.commit.called


@pytest.mark.asyncio
async def test_pwad_crash():
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()

    with (
        patch("app.services.run_loop.SessionLocal") as mock_session_local,
        patch("app.services.run_loop.McpDoomClient") as mock_mcp_cls,
        patch("app.services.run_loop.GeminiService") as mock_gemini_cls,
        patch("app.services.run_loop.RecordingService") as mock_rec_cls,
        patch("app.services.run_loop.websocket_service") as mock_ws,
        patch("app.services.run_loop.DefectService") as mock_defect_cls,
        patch("app.services.run_loop.ReportService") as mock_report_cls,
        patch("app.services.run_loop.WadRepository") as mock_wad_repo_cls,
        patch("app.services.run_loop.RunRepository") as mock_run_repo_cls,
        patch("app.services.run_loop.get_behavior_profile") as mock_get_profile,
        patch("app.services.run_loop.render_agent_prompt") as mock_render_prompt,
        patch("app.services.run_loop.RUN_TASKS", {}),
    ):
        db = _make_db()
        db.get.side_effect = lambda cls, id: {TestRun: run, StaticAnalysisResult: analysis}.get(cls)

        mock_session_local.return_value = _make_session(db)
        _setup_ws(mock_ws)

        mock_wad_repo = AsyncMock()
        mock_wad_repo.get_by_id = AsyncMock(return_value=wad)
        mock_wad_repo_cls.return_value = mock_wad_repo

        mock_run_repo = AsyncMock()
        mock_run_repo.update = AsyncMock(side_effect=_update_run)
        mock_run_repo_cls.return_value = mock_run_repo

        from app.services.mcp_client_service import McpStartupError

        _make_mcp(mock_mcp_cls, start_side_effect=McpStartupError("Simulated PWAD crash"))

        rec = AsyncMock()
        rec.write_frame = MagicMock()
        rec.finalize = MagicMock(return_value="/tmp/recording.mp4")
        rec.path = MagicMock()
        rec.path.exists.return_value = True
        rec.validate = MagicMock(
            return_value={"quality_status": "ok", "frame_count": 0, "unique_frame_count": 0, "fps": 15, "width": 640, "height": 480, "gameplay_seconds": 0, "advanced_game_ticks": 0}
        )
        mock_rec_cls.return_value = rec

        mock_get_profile.return_value = MagicMock(
            throttle_delays={"combat": 0.5, "low_health": 1.0, "stuck": 2.0, "default": 1.5},
        )
        mock_render_prompt.return_value = "Test prompt."

        mock_defect_svc = AsyncMock()
        mock_defect_svc.detect_for_run = AsyncMock()
        mock_defect_cls.return_value = mock_defect_svc

        mock_report_svc = AsyncMock()
        mock_report_svc.generate = AsyncMock()
        mock_report_cls.return_value = mock_report_svc

        from app.services.run_loop import agent_run_task

        await agent_run_task(run.id)

        mock_run_repo.update.assert_any_call(
            run,
            status="failed",
            outcome="error",
            error_message="Simulated PWAD crash",
            failure_category="infrastructure",
            failure_stage="mcp_connect_retry_exhausted",
            failure_summary="mcp-doom could not be reached or start_game did not respond after retrying.",
            failure_diagnostics={
                "raw_error": "Simulated PWAD crash",
                "exception_type": "McpStartupError",
                "user_facing_outcome": "infrastructure_error",
            },
        )
        rec.finalize.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled():
    run = _mock_run()
    run.status = "cancelled"
    wad = _mock_wad()
    analysis = _mock_analysis()

    with (
        patch("app.services.run_loop.SessionLocal") as mock_session_local,
        patch("app.services.run_loop.McpDoomClient") as mock_mcp_cls,
        patch("app.services.run_loop.WadRepository") as mock_wad_repo_cls,
        patch("app.services.run_loop.RunRepository") as mock_run_repo_cls,
        patch("app.services.run_loop.DefectService") as mock_defect_cls,
        patch("app.services.run_loop.ReportService") as mock_report_cls,
        patch("app.services.run_loop.get_behavior_profile") as mock_get_profile,
        patch("app.services.run_loop.render_agent_prompt") as mock_render_prompt,
        patch("app.services.run_loop.RecordingService") as mock_rec_cls,
        patch("app.services.run_loop.websocket_service") as mock_ws,
        patch("app.services.run_loop.RUN_TASKS", {}),
    ):
        db = _make_db()
        db.get.side_effect = lambda cls, id: {TestRun: run, StaticAnalysisResult: analysis}.get(cls)

        mock_session_local.return_value = _make_session(db)
        _setup_ws(mock_ws)

        mock_wad_repo = AsyncMock()
        mock_wad_repo.get_by_id = AsyncMock(return_value=wad)
        mock_wad_repo_cls.return_value = mock_wad_repo

        mock_run_repo = AsyncMock()
        mock_run_repo.update = AsyncMock(side_effect=_update_run)
        mock_run_repo_cls.return_value = mock_run_repo

        _make_mcp(mock_mcp_cls, start_side_effect=asyncio.CancelledError())

        mock_get_profile.return_value = MagicMock(
            throttle_delays={"combat": 0.5, "low_health": 1.0, "stuck": 2.0, "default": 1.5},
        )
        mock_render_prompt.return_value = "Test prompt."

        mock_defect_svc = AsyncMock()
        mock_defect_svc.detect_for_run = AsyncMock()
        mock_defect_cls.return_value = mock_defect_svc

        mock_report_svc = AsyncMock()
        mock_report_svc.generate = AsyncMock()
        mock_report_cls.return_value = mock_report_svc

        rec = AsyncMock()
        rec.write_frame = MagicMock()
        rec.finalize = MagicMock(return_value=None)
        rec.path = MagicMock()
        rec.path.exists.return_value = False
        rec.validate = MagicMock(
            return_value={"quality_status": "unknown", "frame_count": 0, "unique_frame_count": 0, "fps": 15, "width": 640, "height": 480, "gameplay_seconds": 0, "advanced_game_ticks": 0}
        )
        mock_rec_cls.return_value = rec

        from app.services.run_loop import agent_run_task

        await agent_run_task(run.id)

        mock_run_repo.update.assert_any_call(run, status="cancelled")
