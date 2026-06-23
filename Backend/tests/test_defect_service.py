from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    Defect,
    GameEvent,
    NotableEventScreenshot,
    StaticAnalysisResult,
    TestRun,
    WadHypothesis,
)
from app.repositories.defect_repository import DefectRepository
from app.services.defect_service import DefectService, _streak_episodes


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    mock_repo = MagicMock(spec=DefectRepository)
    mock_repo.create = AsyncMock()
    mock_repo.list_by_run = AsyncMock(return_value=[])
    svc = DefectService(mock_db)
    svc.repo = mock_repo
    return svc


def make_event(
    tick: int,
    event_type: str = "normal",
    x: float = 0,
    y: float = 0,
    health: int = 100,
    ammo_bullets: int = 10,
    ammo_shells: int = 0,
    ammo_rockets: int = 0,
    ammo_cells: int = 0,
    kill_count: int = 0,
    secret_count: int = 0,
    action_taken: dict | None = None,
) -> GameEvent:
    event = MagicMock(spec=GameEvent)
    event.tick_number = tick
    event.event_type = event_type
    event.player_x = x
    event.player_y = y
    event.health = health
    event.ammo_bullets = ammo_bullets
    event.ammo_shells = ammo_shells
    event.ammo_rockets = ammo_rockets
    event.ammo_cells = ammo_cells
    event.kill_count = kill_count
    event.secret_count = secret_count
    event.action_taken = action_taken
    return event


@pytest.mark.asyncio
async def test_visual_defects_skip_cleanly_without_gemini_key(mock_db):
    gemini = MagicMock()
    gemini.settings.gemini_api_key = ""

    await DefectService(mock_db, gemini_service=gemini)._vision_defects(uuid4())

    mock_db.execute.assert_not_awaited()


# ── _streak_episodes ──────────────────────────────────────


def test_streak_episodes_detects_streak():
    events = [make_event(i, health=5) for i in range(70)]
    episodes = _streak_episodes(events, lambda e: e.health < 10, minimum_length=61)
    assert len(episodes) == 1
    assert len(episodes[0]) == 70


def test_streak_episodes_gap_resets():
    below = [make_event(i, health=5) for i in range(40)]
    above = [make_event(50, health=100)]
    more_below = [make_event(i, health=5) for i in range(51, 81)]
    episodes = _streak_episodes(below + above + more_below, lambda e: e.health < 10, minimum_length=30)
    assert len(episodes) == 2


def test_streak_episodes_too_short_ignored():
    events = [make_event(i, health=5) for i in range(10)]
    episodes = _streak_episodes(events, lambda e: e.health < 10, minimum_length=61)
    assert len(episodes) == 0


# ── _difficulty_spawn_mismatch ────────────────────────────


@pytest.mark.asyncio
async def test_difficulty_spawn_mismatch_detects_hidden_enemies(service, mock_db):
    run = MagicMock(spec=TestRun)
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.thing_count_enemies = 10
    analysis.thing_count_items = 5
    analysis.spawn_summary_by_skill = {
        "3": {"thing_count_enemies": 2, "thing_count_items": 3},
        "_map_features": {},
    }
    run.difficulty_level = 3
    await service._difficulty_spawn_mismatch(run, analysis)
    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "difficulty_spawn_mismatch"
    assert "enemies" in args.description
    assert args.severity == 2


@pytest.mark.asyncio
async def test_difficulty_spawn_mismatch_all_spawn_no_defect(service, mock_db):
    run = MagicMock(spec=TestRun)
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.thing_count_enemies = 10
    analysis.thing_count_items = 5
    analysis.spawn_summary_by_skill = {
        "3": {"thing_count_enemies": 10, "thing_count_items": 5},
        "_map_features": {},
    }
    run.difficulty_level = 3
    await service._difficulty_spawn_mismatch(run, analysis)
    service.repo.create.assert_not_called()


# ── _static_resource_balance ────────────────────────────


@pytest.mark.asyncio
async def test_static_resource_balance_detects_low_ammo(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.ammo_ratio = 0.0833
    analysis.health_ratio = 1.0
    analysis.total_monster_hp = 1200
    analysis.total_health_pickup_pts = 200
    await service._static_resource_balance(run, analysis)
    assert service.repo.create.await_count == 1
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "static_ammo_risk"
    assert args.resolution_status == "candidate"


@pytest.mark.asyncio
async def test_static_resource_balance_detects_low_health(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.ammo_ratio = 1.0
    analysis.health_ratio = 0.0
    analysis.total_monster_hp = 3200
    analysis.total_health_pickup_pts = 0
    await service._static_resource_balance(run, analysis)
    assert service.repo.create.await_count == 1
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "static_health_risk"
    assert args.resolution_status == "candidate"


@pytest.mark.asyncio
async def test_static_resource_balance_detects_both_low(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.ammo_ratio = 0.08
    analysis.health_ratio = 0.0
    analysis.total_monster_hp = 1200
    analysis.total_health_pickup_pts = 0
    await service._static_resource_balance(run, analysis)
    assert service.repo.create.await_count == 2
    args1 = service.repo.create.call_args_list[0][0][0]
    args2 = service.repo.create.call_args_list[1][0][0]
    assert args1.defect_type == "static_ammo_risk"
    assert args2.defect_type == "static_health_risk"


@pytest.mark.asyncio
async def test_static_resource_balance_skips_when_adequate(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.ammo_ratio = 0.8
    analysis.health_ratio = 0.5
    analysis.total_monster_hp = 1000
    analysis.total_health_pickup_pts = 500
    await service._static_resource_balance(run, analysis)
    service.repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_static_resource_balance_skips_when_no_analysis(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    await service._static_resource_balance(run, None)
    service.repo.create.assert_not_called()


# ── _repeated_death_location ──────────────────────────────


@pytest.mark.asyncio
async def test_repeated_death_location_detects_duplicate(service, mock_db):
    events = [
        make_event(10, "death", x=100, y=200),
        make_event(50, "death", x=105, y=195),
    ]
    await service._repeated_deaths(uuid4(), events)
    service.repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_death_location_single_skipped(service, mock_db):
    events = [make_event(10, "death", x=100, y=200)]
    await service._repeated_deaths(uuid4(), events)
    service.repo.create.assert_not_called()


# ── _ammo_starvation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_ammo_starvation_detects_episode(service, mock_db):
    events = [make_event(i, ammo_bullets=0, ammo_shells=0, ammo_rockets=0, ammo_cells=0) for i in range(70)]
    await service._ammo_starvation(uuid4(), events)
    service.repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_ammo_starvation_gap_resets_two_episodes(service, mock_db):
    first = [make_event(i, ammo_bullets=0, ammo_shells=0, ammo_rockets=0, ammo_cells=0) for i in range(70)]
    mid = [make_event(80, ammo_bullets=50)]
    second = [make_event(90 + i, ammo_bullets=0, ammo_shells=0, ammo_rockets=0, ammo_cells=0) for i in range(70)]
    await service._ammo_starvation(uuid4(), first + mid + second)
    assert service.repo.create.await_count == 2


@pytest.mark.asyncio
async def test_ammo_starvation_uses_usable_attack_ammo_not_legacy_slots(service, mock_db):
    events = [
        make_event(
            i,
            ammo_bullets=0,
            ammo_shells=0,
            ammo_rockets=0,
            ammo_cells=0,
            action_taken={"resource_state": {"usable_attack_ammo": 50}},
        )
        for i in range(70)
    ]
    await service._ammo_starvation(uuid4(), events)
    service.repo.create.assert_not_called()


# ── _health_deficit ───────────────────────────────────────


@pytest.mark.asyncio
async def test_health_deficit_detects_episode(service, mock_db):
    events = [make_event(i, health=5) for i in range(40)]
    await service._health_deficit(uuid4(), events)
    service.repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_deficit_above_threshold_skipped(service, mock_db):
    events = [make_event(i, health=50) for i in range(100)]
    await service._health_deficit(uuid4(), events)
    service.repo.create.assert_not_called()


# ── softlock ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_softlock_creates_defect_for_stuck_timeout(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.outcome = "timeout"
    run.id = uuid4()
    events = [make_event(i, event_type="stuck") for i in range(5, 20)]
    await service._softlock(run, events)
    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "softlock_navigation"


@pytest.mark.asyncio
async def test_softlock_timeout_little_movement(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.outcome = "timeout"
    run.id = uuid4()
    events = [make_event(i, x=0, y=0) for i in range(20)]
    await service._softlock(run, events)
    service.repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_softlock_records_guard_injected_take_action_stuck_as_inconclusive_without_mutating_outcome(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.outcome = "timeout"
    run.id = uuid4()
    events = [
        make_event(
            i,
            event_type="stuck",
            action_taken={
                "mcp_tool": "take_action",
                "mcp_executed_tool": "take_action",
                "mcp_action_summary": {"stop_reason": "tics_complete"},
            },
        )
        for i in range(5, 10)
    ]

    await service._softlock(run, events)

    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "inconclusive_agent_stall"
    assert run.outcome == "timeout"


@pytest.mark.asyncio
async def test_softlock_no_defect_for_map_completed(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.outcome = "map_completed"
    run.id = uuid4()
    events = [make_event(i) for i in range(20)]
    await service._softlock(run, events)
    service.repo.create.assert_not_called()


# ── _unreachable_secrets ──────────────────────────────────


@pytest.mark.asyncio
async def test_unreachable_secrets_detects_missed_secrets(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.progress_metrics = {"coverage_percent": 75.0}
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.secret_sector_count = 3
    events = [make_event(100, secret_count=0)]
    await service._unreachable_secrets(run, events, analysis)
    service.repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_unreachable_secrets_no_defect_when_none_exist(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.progress_metrics = {"coverage_percent": 75.0}
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.secret_sector_count = 0
    events = [make_event(100, secret_count=0)]
    await service._unreachable_secrets(run, events, analysis)
    service.repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_unreachable_secrets_no_defect_when_secret_found(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.progress_metrics = {"coverage_percent": 75.0}
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.secret_sector_count = 3
    events = [make_event(100, secret_count=1)]
    await service._unreachable_secrets(run, events, analysis)
    service.repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_unreachable_secrets_no_defect_when_coverage_is_low(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.progress_metrics = {"coverage_percent": 17.5}
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.secret_sector_count = 3
    events = [make_event(100, secret_count=0)]
    await service._unreachable_secrets(run, events, analysis)
    service.repo.create.assert_not_called()


# ── detect_for_run orchestration ──────────────────────────


@pytest.mark.asyncio
async def test_detect_for_run_orchestration(mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.failure_category = "pwad_crash"
    run.outcome = None
    run.static_analysis_id = uuid4()
    run.wad_file_id = uuid4()
    run.map_name = "MAP01"

    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.spawn_summary_by_skill = {"_map_features": {"voodoo_doll_risk": False}}
    mock_db.get = AsyncMock(return_value=analysis)

    events = [make_event(i) for i in range(5)]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = events
    mock_db.execute = AsyncMock(return_value=result_mock)

    gemini = MagicMock()
    gemini.settings.gemini_api_key = ""
    svc = DefectService(mock_db, gemini_service=gemini)

    called_detectors = []
    original_pwad = svc._pwad_crash
    original_voodoo = svc._voodoo_dolls
    original_diff = svc._difficulty_spawn_mismatch
    original_resource = svc._static_resource_balance
    original_vision = svc._vision_defects
    original_repeated = svc._repeated_deaths
    original_ammo = svc._ammo_starvation
    original_health = svc._health_deficit
    original_softlock = svc._softlock
    original_secrets = svc._unreachable_secrets
    original_promote = svc._promote_hypotheses
    original_link = svc._link_screenshots_to_defects

    async def track_pwad(r): called_detectors.append("_pwad_crash")
    async def track_voodoo(r, a): called_detectors.append("_voodoo_dolls")
    async def track_diff(r, a): called_detectors.append("_difficulty_spawn_mismatch")
    async def track_resource(r, a): called_detectors.append("_static_resource_balance")
    async def track_vision(rid): called_detectors.append("_vision_defects")
    async def track_repeated(rid, ev): called_detectors.append("_repeated_deaths")
    async def track_ammo(rid, ev): called_detectors.append("_ammo_starvation")
    async def track_health(rid, ev): called_detectors.append("_health_deficit")
    async def track_softlock(r, ev): called_detectors.append("_softlock")
    async def track_secrets(r, ev, a): called_detectors.append("_unreachable_secrets")
    async def track_promote(r): called_detectors.append("_promote_hypotheses")
    async def track_link(rid): called_detectors.append("_link_screenshots_to_defects")

    svc._pwad_crash = track_pwad
    svc._voodoo_dolls = track_voodoo
    svc._difficulty_spawn_mismatch = track_diff
    svc._static_resource_balance = track_resource
    svc._vision_defects = track_vision
    svc._repeated_deaths = track_repeated
    svc._ammo_starvation = track_ammo
    svc._health_deficit = track_health
    svc._softlock = track_softlock
    svc._unreachable_secrets = track_secrets
    svc._promote_hypotheses = track_promote
    svc._link_screenshots_to_defects = track_link

    await svc.detect_for_run(run)

    assert called_detectors == [
        "_pwad_crash",
        "_voodoo_dolls",
        "_difficulty_spawn_mismatch",
        "_static_resource_balance",
        "_vision_defects",
        "_repeated_deaths",
        "_ammo_starvation",
        "_health_deficit",
        "_softlock",
        "_unreachable_secrets",
        "_promote_hypotheses",
        "_link_screenshots_to_defects",
    ]


# ── _pwad_crash ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_pwad_crash_defect_created(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.failure_category = "pwad_crash"
    run.outcome = "timeout"
    run.failure_summary = "Segfault in WAD init"
    await service._pwad_crash(run)
    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "pwad_crash"
    assert args.severity == 1
    assert args.priority == 1


@pytest.mark.asyncio
async def test_pwad_crash_from_outcome(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.failure_category = "other"
    run.outcome = "pwad_crash"
    run.failure_summary = None
    await service._pwad_crash(run)
    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "pwad_crash"


@pytest.mark.asyncio
async def test_pwad_crash_not_created_for_other(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.failure_category = "timeout"
    run.outcome = "timeout"
    await service._pwad_crash(run)
    service.repo.create.assert_not_called()


# ── _voodoo_dolls ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_voodoo_dolls_detects(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.spawn_summary_by_skill = {
        "_map_features": {"voodoo_doll_risk": True, "player_start_count": 3}
    }
    await service._voodoo_dolls(run, analysis)
    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "geometry_voodoo_dolls"
    assert "3" in args.title


@pytest.mark.asyncio
async def test_voodoo_dolls_no_risk_no_defect(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    analysis = MagicMock(spec=StaticAnalysisResult)
    analysis.spawn_summary_by_skill = {
        "_map_features": {"voodoo_doll_risk": False}
    }
    await service._voodoo_dolls(run, analysis)
    service.repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_voodoo_dolls_no_analysis_skipped(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    await service._voodoo_dolls(run, None)
    service.repo.create.assert_not_called()


# ── _promote_hypotheses ───────────────────────────────────


@pytest.mark.asyncio
async def test_promote_hypotheses_creates_defects(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.wad_file_id = uuid4()
    run.map_name = "MAP01"

    hyp = MagicMock(spec=WadHypothesis)
    hyp.id = uuid4()
    hyp.confidence = 0.8
    hyp.tag = "BLOCKED_PATH"
    hyp.content = "Path blocked near start"

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [hyp]
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._promote_hypotheses(run)
    service.repo.create.assert_awaited_once()
    args = service.repo.create.call_args[0][0]
    assert args.defect_type == "recurring_blocked_path"
    assert args.severity == 2
    assert hyp.confirmed_at is not None


@pytest.mark.asyncio
async def test_promote_hypotheses_skips_low_confidence(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.wad_file_id = uuid4()
    run.map_name = "MAP01"

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._promote_hypotheses(run)
    service.repo.create.assert_not_called()
    call_args = mock_db.execute.call_args[0][0]
    compiled = call_args.compile(compile_kwargs={"literal_binds": True})
    assert "0.6" in str(compiled)


@pytest.mark.asyncio
async def test_promote_hypotheses_no_wad_file_id(service, mock_db):
    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    run.wad_file_id = None

    await service._promote_hypotheses(run)
    mock_db.execute.assert_not_awaited()
    service.repo.create.assert_not_called()


# ── _link_screenshots_to_defects ──────────────────────────


@pytest.mark.asyncio
async def test_link_screenshots_to_defects(service, mock_db):
    run_id = uuid4()
    event_id = 1
    screenshot_id = uuid4()

    screenshot = MagicMock(spec=NotableEventScreenshot)
    screenshot.game_event_id = event_id
    screenshot.id = screenshot_id

    screenshots_result = MagicMock()
    screenshots_result.scalars.return_value.all.return_value = [screenshot]

    event_row = MagicMock()
    event_row.tick_number = 42
    event_row.id = event_id
    events_result = MagicMock()
    events_result.__iter__ = lambda self: iter([event_row])

    defect = MagicMock(spec=Defect)
    defect.screenshot_id = None
    defect.detected_at_tick = 42
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect]

    mock_db.execute = AsyncMock(side_effect=[screenshots_result, events_result, defects_result])

    await service._link_screenshots_to_defects(run_id)
    assert defect.screenshot_id == screenshot_id


@pytest.mark.asyncio
async def test_link_screenshots_no_screenshots(service, mock_db):
    run_id = uuid4()
    screenshots_result = MagicMock()
    screenshots_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=screenshots_result)

    await service._link_screenshots_to_defects(run_id)
    assert mock_db.execute.await_count == 1
    service.repo.create.assert_not_called()
