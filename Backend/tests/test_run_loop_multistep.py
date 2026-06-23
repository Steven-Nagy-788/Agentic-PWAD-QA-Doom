"""Multi-iteration lockstep loop tests.

These tests exercise agent_run_task across 2-3 iterations of the while True
loop, verifying break conditions, throttle, combat logging, checkpoint
recording, and coverage warning generation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import StaticAnalysisResult, TestRun, WadFile


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mock_run():
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.wad_file_id = uuid4()
    run.static_analysis_id = uuid4()
    run.map_name = "MAP01"
    run.difficulty_level = 3
    run.iwad_used = "freedoom2"
    run.llm_model = "gemini-3.1-flash-lite"
    run.max_ticks = 5000
    run.status = "pending"
    run.behavior_profile = "thorough"
    run.seed = None
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
    an.spawn_summary_by_skill = {}
    an.thing_count_enemies = 10
    an.map_overview_png_path = None
    return an


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock()
    db.execute = AsyncMock(return_value=_empty_result())
    return db


def _make_session(db):
    sess = AsyncMock()
    sess.__aenter__.return_value = db
    sess.__aexit__.return_value = None
    return sess


def _mock_game_event(event_type="normal", health=100):
    ev = MagicMock()
    ev.id = uuid4()
    ev.event_type = event_type
    ev.health = health
    return ev


def _common_patches():
    """All patches needed for agent_run_task to reach the while True loop."""
    return {
        "session_local": patch("app.services.run_loop.SessionLocal"),
        "mcp_cls": patch("app.services.run_loop.McpDoomClient"),
        "gemini_cls": patch("app.services.run_loop.GeminiService"),
        "rec_cls": patch("app.services.run_loop.RecordingService"),
        "ws": patch("app.services.run_loop.websocket_service"),
        "defect_cls": patch("app.services.run_loop.DefectService"),
        "report_cls": patch("app.services.run_loop.ReportService"),
        "wad_repo_cls": patch("app.services.run_loop.WadRepository"),
        "run_repo_cls": patch("app.services.run_loop.RunRepository"),
        "config_repo_cls": patch("app.services.run_loop.ConfigRepository"),
        "get_profile": patch("app.services.run_loop.get_behavior_profile"),
        "render_prompt": patch("app.services.run_loop.render_agent_prompt"),
        "collector_cls": patch("app.services.run_loop.CollectorService"),
        "decision_repo_cls": patch("app.services.run_loop.AgentDecisionRepository"),
        "finalize_run": patch("app.services.run_loop.finalize_run", new_callable=AsyncMock),
        "run_tasks": patch("app.services.run_loop.RUN_TASKS", {}),
        # Phase-1 dependencies that touch DB/settings
        "cross_run_memory": patch("app.services.run_loop._build_cross_run_memory_context",
                                  new_callable=AsyncMock, return_value=""),
        "per_decision_cross_run": patch("app.services.run_loop._build_per_decision_cross_run_context",
                                        new_callable=AsyncMock, return_value={}),
        "env_metadata": patch("app.services.run_loop.collect_environment_metadata",
                              new_callable=AsyncMock, return_value={}),
        "skill_summary": patch("app.services.analysis_service.selected_skill_spawn_summary",
                               return_value={}),
    }


def _loop_patches():
    """Patches for utility functions called inside the while True loop."""
    return {
        "factual_tic": patch("app.services.run_loop._factual_game_tic", side_effect=[100, 200]),
        "track_cell": patch("app.services.run_loop._track_visited_cell"),
        "track_sectors": patch("app.services.run_loop._track_explored_sectors"),
        "finalize_decision": patch("app.services.run_loop._finalize_lockstep_decision"),
        "progress_metrics": patch("app.services.run_loop._lockstep_progress_metrics",
                                  return_value={"progress_score": 0}),
        "quality_flags": patch("app.services.run_loop._lockstep_quality_flags",
                               return_value={"quality_status": "unknown"}),
        "should_stop_stuck": patch("app.services.run_loop._lockstep_should_stop_as_stuck",
                                   return_value=False),
        "record_decision": patch("app.services.run_loop._record_decision_in_history"),
        "record_event": patch("app.services.run_loop._record_event_in_history"),
        "record_position": patch("app.services.run_loop._record_position_in_trail"),
        "update_objective": patch("app.services.run_loop._update_objective_history"),
        "merge_hypotheses": patch("app.services.run_loop._merge_hypotheses"),
        "gen_layout": patch("app.services.run_loop.generate_map_layout_png", return_value=None),
        "jpeg_b64": patch("app.services.run_loop.jpeg_b64", return_value="b64"),
        "png_to_frame": patch("app.services.run_loop.png_bytes_to_frame", return_value=MagicMock()),
        "update_lockstep": patch("app.services.run_loop._update_lockstep_after_action"),
        "sleep": patch("app.services.run_loop.asyncio.sleep", new_callable=AsyncMock),
    }


def _start_patches(patch_dict):
    return {k: v.start() for k, v in patch_dict.items()}


def _stop_patches(patch_dict):
    for v in patch_dict.values():
        v.stop()


def _wire_db(db, run, analysis, wad, sess):
    db.get.side_effect = lambda cls, id_: {TestRun: run, StaticAnalysisResult: analysis}.get(cls)
    return _make_session(db)


def _wire_common(started, run, wad, analysis):
    db = _make_db()
    db.get.side_effect = lambda cls, id_: {TestRun: run, StaticAnalysisResult: analysis}.get(cls)
    started["session_local"].return_value = _make_session(db)

    started["ws"].broadcast = AsyncMock()
    started["ws"].cleanup_run = AsyncMock()

    wad_repo = AsyncMock()
    wad_repo.get_by_id = AsyncMock(return_value=wad)
    started["wad_repo_cls"].return_value = wad_repo

    run_repo = AsyncMock()
    run_repo.update = AsyncMock()
    started["run_repo_cls"].return_value = run_repo

    started["config_repo_cls"].return_value = AsyncMock(get_all=AsyncMock(return_value={}))
    started["get_profile"].return_value = MagicMock(
        throttle_delays={"combat": 0.5, "low_health": 1.0, "stuck": 2.0, "default": 1.5},
        system_prompt_addendum="",
    )
    started["render_prompt"].return_value = "Test prompt."
    started["defect_cls"].return_value = MagicMock(detect_for_run=AsyncMock())
    started["report_cls"].return_value = MagicMock(generate=AsyncMock())

    return db


def _make_mcp(started):
    mcp = AsyncMock()
    mcp.start_game = AsyncMock()
    mcp.get_runtime_metadata = AsyncMock(return_value={})
    mcp.get_state = AsyncMock()
    mcp.call_tool = AsyncMock(return_value={})
    mcp.stop_game = AsyncMock()
    started["mcp_cls"].return_value.__aenter__.return_value = mcp
    started["mcp_cls"].return_value.__aexit__.return_value = None
    return mcp


def _make_gemini(started, decision=None):
    if decision is None:
        decision = {
            "reasoning_summary": "Test decision.",
            "mcp_tool": "explore",
            "mcp_params": {},
            "observed_issue": None,
        }
    gemini = AsyncMock()
    gemini.decide = AsyncMock(return_value=(decision, {"prompt_tokens": 100, "completion_tokens": 50}))
    started["gemini_cls"].return_value = gemini
    return gemini


def _make_recorder(started):
    rec = MagicMock()
    rec.write_frame = MagicMock()
    rec.finalize = MagicMock(return_value="/tmp/recording.mp4")
    rec.path = MagicMock()
    rec.path.exists.return_value = True
    rec.validate = MagicMock(return_value={
        "quality_status": "ok", "frame_count": 10, "unique_frame_count": 8,
        "fps": 15, "width": 640, "height": 480, "gameplay_seconds": 5,
        "advanced_game_ticks": 100,
    })
    rec.save_screenshot = MagicMock(return_value="/tmp/screenshot.png")
    started["rec_cls"].return_value = rec
    return rec


def _make_collector(started, events):
    mock_collector = started["collector_cls"].return_value
    mock_collector.collect = AsyncMock(side_effect=events)
    mock_collector.attach_screenshot = AsyncMock()
    return mock_collector


def _make_decision_repo(started):
    mock_repo = started["decision_repo_cls"].return_value
    mock_repo.create = AsyncMock(side_effect=lambda d: d)
    mock_repo.update = AsyncMock()
    return mock_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_iteration_episode_timeout():
    """First get_state returns normal state; second returns episode_timeout.
    Verify outcome='timeout' and two iterations execute."""
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        state_iter1 = {
            "episode_finished": False,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 100, "POSITION_Y": 200, "HEALTH": 100,
                "ARMOR": 0, "KILLCOUNT": 0, "TIC": 100,
            },
            "tic": 100,
        }
        state_iter2 = {
            "episode_finished": False,
            "episode_timeout": True,
            "game_variables": {
                "POSITION_X": 110, "POSITION_Y": 210, "HEALTH": 100,
                "ARMOR": 0, "KILLCOUNT": 0, "TIC": 200,
            },
            "tic": 200,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b"\x89PNG"),
            (state_iter2, b"\x89PNG"),
        ])

        tool_response = {
            "game_variables": {
                "POSITION_X": 105, "POSITION_Y": 205, "HEALTH": 100, "TIC": 150,
            },
            "action_summary": {"stop_reason": "tics_complete"},
        }
        mcp.call_tool = AsyncMock(side_effect=[
            {},   # get_threat_assessment  (iter 1)
            {},   # get_navigation_info   (iter 1)
            tool_response,  # explore      (iter 1)
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Exploring.",
            "mcp_tool": "explore",
            "mcp_params": {},
            "observed_issue": None,
        })

        ev1 = _mock_game_event(event_type="normal", health=100)
        ev2 = _mock_game_event(event_type="normal", health=100)
        _make_collector(started, [ev1, ev2])
        _make_decision_repo(started)

        # Patch _factual_game_tic to return controlled tick values
        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[100, 200],
        )
        loop["factual_tic"].start()

        from app.services.run_loop import agent_run_task
        await agent_run_task(run.id)

        # get_state called twice (one per iteration)
        assert mcp.get_state.await_count == 2

        # LLM called once (iter 1). Iter 2 hits _situation_finished before LLM.
        started["gemini_cls"].return_value.decide.assert_awaited_once()

        # Run repo updated
        assert started["run_repo_cls"].return_value.update.call_count >= 1

    finally:
        _stop_patches(all_patches)


@pytest.mark.asyncio
async def test_multi_iteration_max_ticks_exceeded():
    """Result tick exceeds max_ticks -> outcome='timeout' and loop breaks."""
    run = _mock_run()
    run.max_ticks = 300
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        state_iter1 = {
            "episode_finished": False,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 10, "POSITION_Y": 20, "HEALTH": 100, "TIC": 100,
            },
            "tic": 100,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b""),
        ])

        result_state = {
            "game_variables": {
                "POSITION_X": 15, "POSITION_Y": 25, "HEALTH": 100, "TIC": 350,
            },
            "tic": 350,
        }
        tool_response = {**result_state, "action_summary": {"stop_reason": "tics_complete"}}
        mcp.call_tool = AsyncMock(side_effect=[
            {},   # get_threat_assessment
            {},   # get_navigation_info
            tool_response,  # explore
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Moving forward.",
            "mcp_tool": "explore",
            "mcp_params": {},
            "observed_issue": None,
        })

        ev = _mock_game_event(event_type="normal", health=100)
        _make_collector(started, [ev])
        _make_decision_repo(started)

        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[100, 350],
        )
        loop["factual_tic"].start()

        from app.services.run_loop import agent_run_task
        await agent_run_task(run.id)

        # Only one iteration executed (result_tick=350 > max_ticks=300)
        assert mcp.get_state.await_count == 1
        started["gemini_cls"].return_value.decide.assert_awaited_once()

    finally:
        _stop_patches(all_patches)


@pytest.mark.asyncio
async def test_multi_iteration_throttle():
    """When throttle_seconds > 0, the loop broadcasts throttle status and sleeps."""
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        state_iter1 = {
            "episode_finished": False,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 50, "POSITION_Y": 60, "HEALTH": 100, "TIC": 50,
            },
            "tic": 50,
        }
        state_iter2 = {
            "episode_finished": True,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 55, "POSITION_Y": 65, "HEALTH": 100, "TIC": 150,
            },
            "tic": 150,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b""),
            (state_iter2, b""),
        ])

        result_state = {
            "game_variables": {
                "POSITION_X": 55, "POSITION_Y": 65, "HEALTH": 100, "TIC": 100,
            },
            "tic": 100,
        }
        tool_response = {**result_state, "action_summary": {"stop_reason": "tics_complete"}}
        mcp.call_tool = AsyncMock(side_effect=[
            {},   # get_threat_assessment (iter 1)
            {},   # get_navigation_info  (iter 1)
            tool_response,  # explore     (iter 1)
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Explore.",
            "mcp_tool": "explore",
            "mcp_params": {},
            "observed_issue": None,
        })

        ev1 = _mock_game_event(event_type="normal", health=100)
        ev2 = _mock_game_event(event_type="normal", health=100)
        _make_collector(started, [ev1, ev2])
        _make_decision_repo(started)

        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[50, 100, 150],
        )
        loop["factual_tic"].start()

        # Override the throttle patch to return a specific value
        loop["sleep"].stop()
        loop["sleep"] = patch("app.services.run_loop.asyncio.sleep", new_callable=AsyncMock)
        sleep_mock = loop["sleep"].start()

        with patch("app.services.run_loop._compute_dynamic_throttle", return_value=2.5):
            from app.services.run_loop import agent_run_task
            await agent_run_task(run.id)

        # Throttle should cause a broadcast with phase="lockstep_throttle"
        ws = started["ws"]
        throttle_broadcasts = [
            call
            for call in ws.broadcast.call_args_list
            if len(call.args) >= 2
            and isinstance(call.args[1], dict)
            and call.args[1].get("phase") == "lockstep_throttle"
        ]
        assert len(throttle_broadcasts) >= 1, "Expected at least one throttle status broadcast"
        payload = throttle_broadcasts[0].args[1]
        assert payload["sleep_seconds"] == 2.5

        # asyncio.sleep should have been called with the throttle duration
        assert sleep_mock.awaited
        sleep_args = [c.args[0] for c in sleep_mock.call_args_list]
        assert 2.5 in sleep_args

    finally:
        _stop_patches(all_patches)


@pytest.mark.asyncio
async def test_multi_iteration_combat_logging():
    """When mcp_tool is aim_and_shoot with target_killed stop_reason,
    _update_combat_log is called with correct arguments."""
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        state_iter1 = {
            "episode_finished": False,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 0, "POSITION_Y": 0, "HEALTH": 80,
                "DAMAGECOUNT": 10, "TIC": 50,
            },
            "tic": 50,
        }
        state_iter2 = {
            "episode_finished": True,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 5, "POSITION_Y": 5, "HEALTH": 80, "TIC": 150,
            },
            "tic": 150,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b""),
            (state_iter2, b""),
        ])

        result_state_iter1 = {
            "game_variables": {
                "POSITION_X": 5, "POSITION_Y": 5, "HEALTH": 80,
                "DAMAGECOUNT": 25, "TIC": 100,
            },
            "tic": 100,
            "action_summary": {
                "stop_reason": "target_killed",
                "weapon_used": "shotgun",
                "shots_fired": 3,
                "hits_landed": 2,
                "kills": 1,
                "target_distance": 200.0,
                "target_name": "Zombieman",
            },
        }
        mcp.call_tool = AsyncMock(side_effect=[
            {},   # get_threat_assessment
            {},   # get_navigation_info
            result_state_iter1,  # aim_and_shoot
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Enemy spotted, engaging.",
            "mcp_tool": "aim_and_shoot",
            "mcp_params": {"object_id": 42},
            "observed_issue": None,
        })

        ev1 = _mock_game_event(event_type="kill", health=80)
        ev2 = _mock_game_event(event_type="normal", health=80)
        _make_collector(started, [ev1, ev2])
        _make_decision_repo(started)

        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[50, 100, 150],
        )
        loop["factual_tic"].start()

        with patch("app.services.run_loop._compute_dynamic_throttle", return_value=0):
            with patch("app.services.run_loop._update_combat_log") as mock_combat_log:
                from app.services.run_loop import agent_run_task
                await agent_run_task(run.id)

        mock_combat_log.assert_called_once()
        kwargs = mock_combat_log.call_args[1]
        assert kwargs["object_id"] == 42
        assert kwargs["weapon"] == "shotgun"
        assert kwargs["shots"] == 3
        assert kwargs["hits"] == 2
        assert kwargs["killed"] is True
        assert kwargs["distance"] == 200.0

    finally:
        _stop_patches(all_patches)


@pytest.mark.asyncio
async def test_multi_iteration_checkpoint_recording():
    """When stop_reason is 'target_killed', _record_checkpoint is called."""
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        state_iter1 = {
            "episode_finished": False,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 10, "POSITION_Y": 10, "HEALTH": 90, "TIC": 50,
            },
            "tic": 50,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b""),
        ])

        result_state = {
            "game_variables": {
                "POSITION_X": 15, "POSITION_Y": 15, "HEALTH": 90, "TIC": 100,
            },
            "tic": 100,
            "action_summary": {
                "stop_reason": "target_killed",
                "weapon_used": "chaingun",
                "shots_fired": 5,
                "hits_landed": 3,
                "kills": 1,
                "target_distance": 150.0,
                "target_name": "Imp",
            },
        }
        mcp.call_tool = AsyncMock(side_effect=[
            {},   # get_threat_assessment
            {},   # get_navigation_info
            result_state,  # aim_and_shoot
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Kill the imp.",
            "mcp_tool": "aim_and_shoot",
            "mcp_params": {"object_id": 7},
            "observed_issue": None,
        })

        ev = _mock_game_event(event_type="kill", health=90)
        _make_collector(started, [ev])
        _make_decision_repo(started)

        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[50, 100],
        )
        loop["factual_tic"].start()

        with patch("app.services.run_loop._compute_dynamic_throttle", return_value=0):
            with patch("app.services.run_loop._record_checkpoint") as mock_checkpoint:
                with patch("app.services.run_loop._update_combat_log"):
                    from app.services.run_loop import agent_run_task
                    await agent_run_task(run.id)

        mock_checkpoint.assert_called_once()
        call_args = mock_checkpoint.call_args
        # _record_checkpoint(lockstep_state, tick, x, y, event)
        assert call_args[0][1] == 100   # tick
        assert call_args[0][2] == 15.0  # x
        assert call_args[0][3] == 15.0  # y
        assert "target_killed" in call_args[0][4]

    finally:
        _stop_patches(all_patches)


@pytest.mark.asyncio
async def test_multi_iteration_coverage_warning():
    """When visited_cells is low and ticks_remaining is low,
    coverage_warning is generated and passed to _build_llm_input."""
    run = _mock_run()
    run.max_ticks = 500
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        # tick=400, max_ticks=500 -> ticks_remaining=100 < 500*0.7=350
        # visited_cells empty (track_visited_cell patched) -> coverage_percent=0 < 20
        state_iter1 = {
            "episode_finished": False,
            "episode_timeout": False,
            "game_variables": {
                "POSITION_X": 0, "POSITION_Y": 0, "HEALTH": 100, "TIC": 400,
            },
            "tic": 400,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b""),
        ])

        result_state = {
            "game_variables": {
                "POSITION_X": 5, "POSITION_Y": 5, "HEALTH": 100, "TIC": 450,
            },
            "tic": 450,
            "action_summary": {"stop_reason": "tics_complete"},
        }
        mcp.call_tool = AsyncMock(side_effect=[
            {},   # get_threat_assessment
            {},   # get_navigation_info
            result_state,  # explore
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Exploring.",
            "mcp_tool": "explore",
            "mcp_params": {},
            "observed_issue": None,
        })

        ev = _mock_game_event(event_type="normal", health=100)
        _make_collector(started, [ev])
        _make_decision_repo(started)

        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[400, 450],
        )
        loop["factual_tic"].start()

        with patch("app.services.run_loop._compute_dynamic_throttle", return_value=0):
            with patch("app.services.run_loop._build_llm_input") as mock_build:
                # Return a valid llm_input dict so the rest of the loop works
                mock_build.return_value = {
                    "game_tic": 400,
                    "ticks_remaining": 100,
                    "player": {"health": 100, "armor": 0, "position": {"x": 0, "y": 0}},
                }
                from app.services.run_loop import agent_run_task
                await agent_run_task(run.id)

        # Verify _build_llm_input was called with a coverage_warning
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["coverage_warning"] is not None
        assert "CRITICAL" in call_kwargs["coverage_warning"] or "WARNING" in call_kwargs["coverage_warning"]
        assert "0.0%" in call_kwargs["coverage_warning"]
        assert call_kwargs["ticks_remaining"] == 100

    finally:
        _stop_patches(all_patches)


@pytest.mark.asyncio
async def test_three_iterations_completes_normally():
    """Three iterations: iter1 explores, iter2 explores, iter3 returns episode_finished.
    Verify all three iterations execute correctly."""
    run = _mock_run()
    wad = _mock_wad()
    analysis = _mock_analysis()
    common = _common_patches()
    loop = _loop_patches()
    all_patches = {**common, **loop}
    started = _start_patches(all_patches)

    try:
        _wire_common(started, run, wad, analysis)
        mcp = _make_mcp(started)
        _make_recorder(started)

        state_iter1 = {
            "episode_finished": False, "episode_timeout": False,
            "game_variables": {"POSITION_X": 0, "POSITION_Y": 0, "HEALTH": 100, "TIC": 10},
            "tic": 10,
        }
        state_iter2 = {
            "episode_finished": False, "episode_timeout": False,
            "game_variables": {"POSITION_X": 50, "POSITION_Y": 50, "HEALTH": 100, "TIC": 50},
            "tic": 50,
        }
        state_iter3 = {
            "episode_finished": True, "episode_timeout": False,
            "game_variables": {"POSITION_X": 100, "POSITION_Y": 100, "HEALTH": 100, "TIC": 100},
            "tic": 100,
        }
        mcp.get_state = AsyncMock(side_effect=[
            (state_iter1, b""),
            (state_iter2, b""),
            (state_iter3, b""),
        ])

        result1 = {
            "game_variables": {"POSITION_X": 50, "POSITION_Y": 50, "TIC": 30},
            "tic": 30,
            "action_summary": {"stop_reason": "tics_complete"},
        }
        result2 = {
            "game_variables": {"POSITION_X": 100, "POSITION_Y": 100, "TIC": 80},
            "tic": 80,
            "action_summary": {"stop_reason": "tics_complete"},
        }
        mcp.call_tool = AsyncMock(side_effect=[
            {}, {}, result1,   # iter1: threat, nav, explore
            {}, {}, result2,   # iter2: threat, nav, explore
        ])

        _make_gemini(started, decision={
            "reasoning_summary": "Explore.",
            "mcp_tool": "explore",
            "mcp_params": {},
            "observed_issue": None,
        })

        ev1 = _mock_game_event(event_type="normal", health=100)
        ev2 = _mock_game_event(event_type="normal", health=100)
        ev3 = _mock_game_event(event_type="normal", health=100)
        _make_collector(started, [ev1, ev2, ev3])
        _make_decision_repo(started)

        loop["factual_tic"].stop()
        loop["factual_tic"] = patch(
            "app.services.run_loop._factual_game_tic",
            side_effect=[10, 30, 50, 80, 100],
        )
        loop["factual_tic"].start()

        with patch("app.services.run_loop._compute_dynamic_throttle", return_value=0):
            from app.services.run_loop import agent_run_task
            await agent_run_task(run.id)

        # get_state called 3 times (one per iteration)
        assert mcp.get_state.await_count == 3
        # LLM called for iter1 and iter2 (iter3 is terminal -> _situation_finished -> no LLM)
        assert started["gemini_cls"].return_value.decide.await_count == 2
        # Collector collect called 3 times
        assert started["collector_cls"].return_value.collect.await_count == 3

    finally:
        _stop_patches(all_patches)
