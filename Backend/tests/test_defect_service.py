from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Defect, GameEvent, StaticAnalysisResult, TestRun
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
    return event


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
