"""Tests for execution time anomaly detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import AgentDecision, GameEvent, TestRun
from app.services.defect_service import DefectService


def _make_decision(
    tool: str,
    duration_ms: float,
    sequence: int = 1,
    stop_reason: str | None = None,
) -> AgentDecision:
    decision = MagicMock(spec=AgentDecision)
    decision.mcp_tool = tool
    decision.mcp_duration_ms = duration_ms
    decision.sequence_number = sequence
    decision.mcp_stop_reason = stop_reason
    decision.llm_input_summary = {"game_variables": {"HEALTH": 100}}
    return decision


def _make_event(tick: int) -> GameEvent:
    event = MagicMock(spec=GameEvent)
    event.tick_number = tick
    event.event_type = "normal"
    event.player_x = 100.0
    event.player_y = 200.0
    event.health = 100
    return event


@pytest.mark.asyncio
async def test_execution_time_no_decisions():
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    service = DefectService(mock_db)
    service.repo = mock_repo

    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    events = [_make_event(i) for i in range(10)]

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._execution_time_anomalies(run, events)
    mock_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_time_few_decisions_skipped():
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    service = DefectService(mock_db)
    service.repo = mock_repo

    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    events = [_make_event(i) for i in range(10)]

    decisions = [_make_decision("explore", 100.0, i) for i in range(3)]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = decisions
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._execution_time_anomalies(run, events)
    mock_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_time_normal_no_anomaly():
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    service = DefectService(mock_db)
    service.repo = mock_repo

    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    events = [_make_event(i) for i in range(10)]

    decisions = [_make_decision("explore", 100.0 + i * 10, i) for i in range(10)]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = decisions
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._execution_time_anomalies(run, events)
    mock_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_time_anomaly_detected():
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    service = DefectService(mock_db)
    service.repo = mock_repo

    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    events = [_make_event(i) for i in range(10)]

    decisions = [_make_decision("explore", 100.0, i) for i in range(10)]
    decisions[5] = _make_decision("explore", 5000.0, 5)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = decisions
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._execution_time_anomalies(run, events)
    mock_repo.create.assert_awaited_once()
    args = mock_repo.create.call_args[0][0]
    assert args.defect_type == "execution_time_anomaly"
    assert "explore" in args.title


@pytest.mark.asyncio
async def test_execution_time_high_ratio_higher_severity():
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    service = DefectService(mock_db)
    service.repo = mock_repo

    run = MagicMock(spec=TestRun)
    run.id = uuid4()
    events = [_make_event(i) for i in range(10)]

    decisions = [_make_decision("explore", 100.0, i) for i in range(10)]
    decisions[5] = _make_decision("explore", 10000.0, 5)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = decisions
    mock_db.execute = AsyncMock(return_value=result_mock)

    await service._execution_time_anomalies(run, events)
    args = mock_repo.create.call_args[0][0]
    assert args.severity == 2
