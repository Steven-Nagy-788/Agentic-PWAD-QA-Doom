from __future__ import annotations

from types import SimpleNamespace

import vizdoom as vzd

from doom_mcp.game_manager import GameManager


class FakeGame:
    def __init__(self, selected_weapon: int = 1) -> None:
        self.variables = {
            "SELECTED_WEAPON": selected_weapon,
            "SELECTED_WEAPON_AMMO": 0,
            **{f"WEAPON{i}": 0 for i in range(10)},
            **{f"AMMO{i}": 0 for i in range(10)},
        }
        self.actions: list[dict[str, float]] = []

    def get_game_variable(self, variable: vzd.GameVariable) -> int:
        return self.variables.get(variable.name, 0)

    def is_episode_finished(self) -> bool:
        return False


def test_slot_one_inventory_count_represents_fist_or_chainsaw() -> None:
    manager = GameManager()
    game = FakeGame()
    game.variables["WEAPON1"] = 2

    state = manager._weapon_state(game)
    slot_one = next(entry for entry in state["weapon_inventory"] if entry["slot"] == 1)

    assert slot_one["name"] == "fist_or_chainsaw"
    assert slot_one["owned_count"] == 2
    assert slot_one["owned"] is True
    assert slot_one["usable"] is True
    assert state["usable_melee_weapons"] == [1]


def test_select_weapon_one_uses_direct_slot_one_and_retries_without_slot_eight(monkeypatch) -> None:
    manager = GameManager()
    manager._buttons = [SimpleNamespace(name="SELECT_WEAPON1")]
    game = FakeGame(selected_weapon=2)

    monkeypatch.setattr(manager, "_build_action_list", lambda actions: actions)
    monkeypatch.setattr(manager, "_clear_action", lambda _game: None)

    def make_action(fake_game: FakeGame, actions: dict[str, float], _tics: int) -> None:
        fake_game.actions.append(actions)
        pulses = sum(1 for action in fake_game.actions if action.get("SELECT_WEAPON1"))
        if pulses == 2:
            fake_game.variables["SELECTED_WEAPON"] = 1

    monkeypatch.setattr(manager, "_make_action", make_action)

    selected, tics_used = manager._select_weapon_slot(game, 1, max_tics=20)

    assert selected is True
    assert tics_used >= 1
    assert sum(1 for action in game.actions if action.get("SELECT_WEAPON1")) >= 2
    assert all("SELECT_WEAPON8" not in action for action in game.actions)
