from __future__ import annotations

import logging
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import Defect, GameEvent, TestRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(
    *,
    run_id: uuid4 | None = None,
    status: str = "running",
    started_at: datetime | None = None,
    error_message: str | None = None,
) -> MagicMock:
    run = MagicMock(spec=TestRun)
    run.id = run_id or uuid4()
    run.status = status
    run.started_at = started_at
    run.error_message = error_message
    return run


def _make_db(run_orm: MagicMock | None = None):
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=run_orm)
    db.execute = AsyncMock(return_value=_empty_result())
    return db


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


def _make_session_local(db):
    ctx = AsyncMock()
    ctx.__aenter__.return_value = db
    ctx.__aexit__.return_value = None
    factory = MagicMock()
    factory.return_value = ctx
    return factory


def _make_ws():
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    ws.cleanup_run = AsyncMock()
    return ws


def _make_recorder(finalize_return="/tmp/recording.mp4", path_exists=True):
    rec = MagicMock()
    rec.finalize.return_value = finalize_return
    rec.path = MagicMock()
    rec.path.exists.return_value = path_exists
    rec.validate.return_value = {
        "quality_status": "ok",
        "frame_count": 10,
        "unique_frame_count": 8,
        "fps": 15,
        "width": 640,
        "height": 480,
        "gameplay_seconds": 5,
        "advanced_game_ticks": 100,
    }
    return rec


def _make_defect():
    d = MagicMock(spec=Defect)
    d.defect_type = "stuck_path"
    d.fingerprint = "abc123"
    d.title = "Agent stuck in corridor"
    d.severity = "medium"
    d.detected_at_tick = 42
    return d


def _make_event():
    ev = MagicMock(spec=GameEvent)
    ev.health = 80
    ev.armor = 50
    ev.kill_count = 5
    ev.secret_count = 1
    ev.item_count = 3
    return ev


def _make_gemini():
    return AsyncMock()


async def _fake_update(run_orm, **fields):
    """Simulate RunRepository.update by applying kwargs to the ORM mock."""
    for key, value in fields.items():
        setattr(run_orm, key, value)


def _base_kwargs(*, run_id=None, outcome="completed", mcp_client=None):
    rid = run_id or uuid4()
    return dict(
        run_id=rid,
        outcome=outcome,
        mcp_client=mcp_client,
        recorder=_make_recorder(),
        lockstep_state={"completed_object_ids": {}, "hypotheses": []},
        total_actions=10,
        total_llm_calls=5,
        latest_event=_make_event(),
        failure_fields={},
        wad_file_id=uuid4(),
        map_name="MAP01",
        max_ticks=500,
        gemini=_make_gemini(),
    )


# ---------------------------------------------------------------------------
# Patch factory
# ---------------------------------------------------------------------------

def _patch_all(
    *,
    run_orm=None,
    ws=None,
    defect_cls_side_effect=None,
    report_cls_side_effect=None,
    run_tasks_dict=None,
):
    ws = ws or _make_ws()
    tasks = run_tasks_dict if run_tasks_dict is not None else {}
    db = _make_db(run_orm)
    session_local = _make_session_local(db)

    run_repo = AsyncMock()
    run_repo.update = AsyncMock(side_effect=_fake_update)
    run_repo_cls = MagicMock(return_value=run_repo)

    defect_svc = AsyncMock()
    defect_svc.detect_for_run = AsyncMock()
    defect_cls = MagicMock(return_value=defect_svc)
    if defect_cls_side_effect is not None:
        defect_svc.detect_for_run.side_effect = defect_cls_side_effect

    defect_repo = AsyncMock()
    defect_repo.list_by_run = AsyncMock(return_value=[])
    defect_repo_cls = MagicMock(return_value=defect_repo)

    report_svc = AsyncMock()
    report_svc.generate = AsyncMock()
    report_svc.mark_error = AsyncMock()
    report_cls = MagicMock(return_value=report_svc)
    if report_cls_side_effect is not None:
        report_svc.generate.side_effect = report_cls_side_effect

    memory_svc = AsyncMock()
    memory_svc.persist_spatial_memory = AsyncMock()
    memory_svc.persist_hypotheses = AsyncMock()
    memory_cls = MagicMock(return_value=memory_svc)

    patches = [
        patch("app.services.run_finalizer.SessionLocal", session_local),
        patch("app.services.run_finalizer.websocket_service", ws),
        patch("app.services.run_finalizer.RunRepository", run_repo_cls),
        patch("app.services.run_finalizer.DefectService", defect_cls),
        patch("app.services.run_finalizer.DefectRepository", defect_repo_cls),
        patch("app.services.run_finalizer.ReportService", report_cls),
        patch("app.services.run_finalizer.RunMemoryService", memory_cls),
        patch("app.services.run_finalizer.RUN_TASKS", tasks),
        patch("app.services.run_finalizer._lockstep_progress_metrics",
              return_value={"progress_score": 0.5}),
        patch("app.services.run_finalizer._lockstep_quality_flags",
              return_value={"quality_status": "ok"}),
        patch("app.services.run_finalizer._normalize_run_outcome",
              side_effect=lambda o: o),
        patch("app.services.run_finalizer._json_safe",
              side_effect=lambda v: v),
    ]
    return patches, {
        "db": db,
        "ws": ws,
        "run_repo": run_repo,
        "defect_svc": defect_svc,
        "defect_repo": defect_repo,
        "report_svc": report_svc,
        "memory_svc": memory_svc,
        "tasks": tasks,
    }


def _activate(patches, extra=None):
    """Start all patches and return an ExitStack."""
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    if extra:
        for p in extra:
            stack.enter_context(p)
    return stack


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_normal_completion_all_steps_execute():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(
        run_id=run_id, status="running",
        started_at=datetime.now(UTC) - timedelta(seconds=30),
    )
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    kwargs["recorder"].finalize.assert_called_once()
    kwargs["recorder"].validate.assert_called_once()
    ctx["run_repo"].update.assert_awaited_once()
    calls = [str(c) for c in ctx["ws"].broadcast.await_args_list]
    assert any("recording_status" in c for c in calls)
    assert any("quality_summary" in c for c in calls)
    ctx["defect_svc"].detect_for_run.assert_awaited_once()
    ctx["memory_svc"].persist_spatial_memory.assert_awaited_once()
    ctx["memory_svc"].persist_hypotheses.assert_awaited_once()
    ctx["report_svc"].generate.assert_awaited_once_with(run_id)
    assert any("state" in str(c) for c in calls)
    ctx["ws"].cleanup_run.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_mcp_client_none_skips_stop_game():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id, mcp_client=None)

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["ws"].cleanup_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_client_present_calls_stop_game():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    mcp = AsyncMock()
    mcp.stop_game = AsyncMock()
    kwargs = _base_kwargs(run_id=run_id, mcp_client=mcp)

    with _activate(P):
        await finalize_run(**kwargs)

    mcp.stop_game.assert_awaited_once()


@pytest.mark.asyncio
async def test_recording_path_none_but_path_exists():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["recorder"] = _make_recorder(finalize_return=None, path_exists=True)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "recording_mp4_path" in update_call.kwargs


@pytest.mark.asyncio
async def test_recording_path_none_and_path_not_exists():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["recorder"] = _make_recorder(finalize_return=None, path_exists=False)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "recording_mp4_path" not in update_call.kwargs
    ctx["ws"].cleanup_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_latest_event_none_skips_final_fields():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["latest_event"] = None

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    call_kwargs = update_call.kwargs
    assert "final_hp" not in call_kwargs
    assert "final_armor" not in call_kwargs
    assert "total_kills" not in call_kwargs


@pytest.mark.asyncio
async def test_run_status_already_failed_not_overridden():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="failed")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id, outcome="error")

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "status" not in update_call.kwargs


@pytest.mark.asyncio
async def test_run_status_already_cancelled_not_overridden():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="cancelled")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id, outcome="cancelled")

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "status" not in update_call.kwargs


@pytest.mark.asyncio
async def test_duration_seconds_computed_when_started_at_set():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    started = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    run_orm = _make_run(run_id=run_id, status="running", started_at=started)
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "duration_seconds" in update_call.kwargs
    assert isinstance(update_call.kwargs["duration_seconds"], int)


@pytest.mark.asyncio
async def test_no_duration_when_started_at_is_none():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running", started_at=None)
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "duration_seconds" not in update_call.kwargs


@pytest.mark.asyncio
async def test_run_orm_none_early_return():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    P, ctx = _patch_all(run_orm=None)
    kwargs = _base_kwargs(run_id=run_id)
    ctx["tasks"][run_id] = "something"

    with _activate(P):
        await finalize_run(**kwargs)

    assert run_id not in ctx["tasks"]
    ctx["run_repo"].update.assert_not_awaited()


@pytest.mark.asyncio
async def test_defect_detection_failure_rollback_and_warning(caplog):
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(
        run_orm=run_orm,
        defect_cls_side_effect=RuntimeError("Defect analysis exploded"),
    )
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P), caplog.at_level(logging.WARNING, logger="app.services.run_finalizer"):
        await finalize_run(**kwargs)

    ctx["db"].rollback.assert_awaited()
    assert "Defect detection failed" in caplog.text
    ctx["ws"].cleanup_run.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_spatial_memory_failure_rollback_and_warning(caplog):
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    ctx["memory_svc"].persist_spatial_memory.side_effect = RuntimeError("Memory write failed")

    with _activate(P), caplog.at_level(logging.WARNING, logger="app.services.run_finalizer"):
        await finalize_run(**kwargs)

    ctx["db"].rollback.assert_awaited()
    assert "Reviewer analytics persistence failed" in caplog.text
    ctx["ws"].cleanup_run.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_report_generation_failure_marks_error_and_broadcasts():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(
        run_orm=run_orm,
        report_cls_side_effect=RuntimeError("PDF rendering failed"),
    )
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["report_svc"].mark_error.assert_awaited()
    calls = [str(c) for c in ctx["ws"].broadcast.await_args_list]
    assert any("error" in c for c in calls)
    ctx["ws"].cleanup_run.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_run_tasks_cleanup_happens_in_all_cases():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    tasks = {run_id: "task_obj"}
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm, run_tasks_dict=tasks)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    assert run_id not in ctx["tasks"]


@pytest.mark.asyncio
async def test_run_tasks_cleanup_on_early_return():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    tasks = {run_id: "task_obj"}
    P, ctx = _patch_all(run_orm=None, run_tasks_dict=tasks)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    assert run_id not in ctx["tasks"]


@pytest.mark.asyncio
async def test_websocket_cleanup_run_always_called():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["ws"].cleanup_run.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_ws_broadcasts_defects():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    defects = [_make_defect(), _make_defect()]
    P, ctx = _patch_all(run_orm=run_orm)
    ctx["defect_repo"].list_by_run = AsyncMock(return_value=defects)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    defect_broadcasts = [
        c for c in ctx["ws"].broadcast.await_args_list
        if "defect" in str(c)
    ]
    assert len(defect_broadcasts) >= 2


@pytest.mark.asyncio
async def test_report_generating_and_complete_broadcast():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    calls = [str(c) for c in ctx["ws"].broadcast.await_args_list]
    assert any("generating" in c for c in calls)
    assert any("complete" in c for c in calls)


@pytest.mark.asyncio
async def test_failure_fields_merged_into_final():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="failed")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id, outcome="error")
    kwargs["failure_fields"] = {
        "failure_category": "pwad_crash",
        "failure_stage": "wad_loading",
        "error_message": "PWAD crashed",
    }

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert update_call.kwargs.get("failure_category") == "pwad_crash"
    assert update_call.kwargs.get("failure_stage") == "wad_loading"
    assert update_call.kwargs.get("error_message") == "PWAD crashed"


@pytest.mark.asyncio
async def test_recording_path_set_when_finalize_returns_path():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["recorder"] = _make_recorder(finalize_return="/output/game.mp4", path_exists=True)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert update_call.kwargs.get("recording_mp4_path") == "/output/game.mp4"


@pytest.mark.asyncio
async def test_completed_at_timestamp_set():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert "completed_at" in update_call.kwargs
    assert isinstance(update_call.kwargs["completed_at"], datetime)


@pytest.mark.asyncio
async def test_total_actions_and_llm_calls_recorded():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["total_actions"] = 42
    kwargs["total_llm_calls"] = 17

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert update_call.kwargs["total_actions_taken"] == 42
    assert update_call.kwargs["total_llm_calls"] == 17


@pytest.mark.asyncio
async def test_final_broadcast_includes_max_ticks():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["max_ticks"] = 9999

    with _activate(P):
        await finalize_run(**kwargs)

    state_broadcasts = [
        c for c in ctx["ws"].broadcast.await_args_list
        if "state" in str(c)
    ]
    assert len(state_broadcasts) >= 1
    assert "9999" in str(state_broadcasts[-1])


@pytest.mark.asyncio
async def test_weapon_count_in_total_items():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["latest_event"] = _make_event()
    kwargs["latest_event"].item_count = 2
    kwargs["lockstep_state"] = {
        "completed_object_ids": {
            "1": {"target_type": "weapon"},
            "2": {"target_type": "health"},
            "3": {"target_type": "weapon"},
        },
        "hypotheses": [],
    }

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert update_call.kwargs.get("total_items_collected") == 4


@pytest.mark.asyncio
async def test_db_commit_called_after_update():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["db"].commit.assert_awaited()


@pytest.mark.asyncio
async def test_status_set_to_completed_for_running_runs():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    update_call = ctx["run_repo"].update.await_args_list[0]
    assert update_call.kwargs.get("status") == "completed"


@pytest.mark.asyncio
async def test_hypotheses_passed_to_persist():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    kwargs["lockstep_state"] = {
        "completed_object_ids": {},
        "hypotheses": [
            {"claim": "door locked", "confidence": 0.8},
            {"claim": "secret nearby", "confidence": 0.3},
        ],
    }

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["memory_svc"].persist_hypotheses.assert_awaited_once()
    call_kwargs = ctx["memory_svc"].persist_hypotheses.await_args.kwargs
    assert len(call_kwargs["in_run_hypotheses"]) == 2


@pytest.mark.asyncio
async def test_report_error_updates_run_error_message():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(
        run_orm=run_orm,
        report_cls_side_effect=RuntimeError("PDF render boom"),
    )
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["report_svc"].mark_error.assert_awaited_once()
    args = ctx["report_svc"].mark_error.await_args
    assert args.args[0] == run_id
    assert "PDF render boom" in args.args[1]


@pytest.mark.asyncio
async def test_spatial_memory_failure_does_not_prevent_report():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)
    ctx["memory_svc"].persist_spatial_memory.side_effect = RuntimeError("boom")

    with _activate(P):
        await finalize_run(**kwargs)

    ctx["report_svc"].generate.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_broadcasts_recording_metadata():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running")
    P, ctx = _patch_all(run_orm=run_orm)
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    recording_broadcasts = [
        c for c in ctx["ws"].broadcast.await_args_list
        if "recording_status" in str(c)
    ]
    assert len(recording_broadcasts) == 1
    payload = recording_broadcasts[0].args[1]
    assert payload["type"] == "recording_status"
    assert payload["metadata"]["quality_status"] == "ok"


@pytest.mark.asyncio
async def test_error_report_updates_run_orm_error_message():
    from app.services.run_finalizer import finalize_run

    run_id = uuid4()
    run_orm = _make_run(run_id=run_id, status="running", error_message=None)
    P, ctx = _patch_all(
        run_orm=run_orm,
        report_cls_side_effect=RuntimeError("PDF fail"),
    )
    kwargs = _base_kwargs(run_id=run_id)

    with _activate(P):
        await finalize_run(**kwargs)

    assert ctx["run_repo"].update.await_count == 2
    second_call = ctx["run_repo"].update.await_args_list[1]
    assert second_call.kwargs.get("error_message") == "Report generation failed: PDF fail"
