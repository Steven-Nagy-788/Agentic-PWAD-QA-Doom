from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.run_memory import RunMemoryService


def _result(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _rows(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = items
    return result


@pytest.mark.asyncio
async def test_recommend_behavior_profile_switches_thorough_to_fast_after_repeated_stuck() -> None:
    db = AsyncMock()
    db.execute.return_value = _result(
        [
            SimpleNamespace(outcome="stuck", behavior_profile="thorough")
            for _ in range(10)
        ]
    )
    service = RunMemoryService(db)
    selected = await service.recommend_behavior_profile(uuid4(), "MAP01", None, "thorough")
    assert selected == "fast"


@pytest.mark.asyncio
async def test_recommend_behavior_profile_respects_explicit_request() -> None:
    db = AsyncMock()
    service = RunMemoryService(db)
    selected = await service.recommend_behavior_profile(uuid4(), "MAP01", "thorough", "thorough")
    assert selected == "thorough"
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_build_cross_run_memory_summarizes_last_run_and_warnings() -> None:
    wad_id = uuid4()
    run_1 = uuid4()
    run_2 = uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _result(
            [
                SimpleNamespace(id=run_1, outcome="stuck", behavior_profile="thorough"),
                SimpleNamespace(id=run_2, outcome="stuck", behavior_profile="thorough"),
            ]
        ),
        _result(
            [
                SimpleNamespace(run_id=run_1, tick_number=225, player_x=-625.2, player_y=-134.4),
                SimpleNamespace(run_id=run_2, tick_number=190, player_x=-610.0, player_y=-120.0),
            ]
        ),
        _result(
            [
                SimpleNamespace(
                    run_id=run_1,
                    defect_type="ammo_starvation",
                    fingerprint="ammo_starvation:225",
                    title="Ammo starvation",
                    description="No ammo for more than 60 ticks.",
                ),
                SimpleNamespace(
                    run_id=run_2,
                    defect_type="ammo_starvation",
                    fingerprint="ammo_starvation:225",
                    title="Ammo starvation",
                    description="No ammo for more than 60 ticks.",
                ),
            ]
        ),
        _result(
            [
                SimpleNamespace(
                    run_id=run_1,
                    mcp_tool="move_to",
                    mcp_input={"object_id": 35},
                    mcp_output={
                        "action_summary": {
                            "stop_reason": "arrival_blocked",
                            "target_name": "ClipBox",
                        }
                    },
                    mcp_stop_reason="arrival_blocked",
                )
            ]
        ),
    ]
    service = RunMemoryService(db)
    memory = await service.build_cross_run_memory(wad_id, "MAP01")
    prompt = memory["prompt"]
    assert "Prior same-WAD/map runs considered: 2" in prompt
    assert "Last run: stuck at tick 225 near (-625.2, -134.4)." in prompt
    assert "move_to object 35 (ClipBox) -> blocked_by_collision" in prompt
    assert "1 previous run(s) had the same final outcome: stuck." in prompt
    assert "ammo starvation" in prompt.lower()


@pytest.mark.asyncio
async def test_build_spatial_memory_briefing_includes_counts_and_event_types() -> None:
    db = AsyncMock()
    db.execute.return_value = _rows(
        [
            SimpleNamespace(cell_x=14, cell_y=8, event_type="stuck", total_occurrences=3),
            SimpleNamespace(cell_x=22, cell_y=4, event_type="secret_found", total_occurrences=1),
            SimpleNamespace(cell_x=3, cell_y=6, event_type="ammo_starvation", total_occurrences=2),
        ]
    )
    service = RunMemoryService(db)
    briefing = await service.build_spatial_memory_briefing(uuid4(), "MAP01")
    assert "Stuck events" in briefing
    assert "cell (14,8) 3x" in briefing
    assert "Secrets found" in briefing
    assert "Resource starvation" in briefing
