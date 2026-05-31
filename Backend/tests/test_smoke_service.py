from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.smoke_service import SmokeService


@pytest.mark.asyncio
async def test_smoke_state_reads_normalized_player_values() -> None:
    client = AsyncMock()
    client.get_state = AsyncMock(
        return_value=(
            {
                "game_variables": {"HEALTH": 87, "AMMO0": 12},
                "weapon_state": {"usable_attack_ammo": 12},
            },
            b"png",
        )
    )

    stage = await SmokeService()._stage_get_state(client)

    assert stage["pass"] is True
    assert stage["detail"]["player_health"] == 87
    assert stage["detail"]["player_ammo"] == 12
