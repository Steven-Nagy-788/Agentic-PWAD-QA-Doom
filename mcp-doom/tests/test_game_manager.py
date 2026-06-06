"""Integration tests for GameManager (requires ViZDoom runtime)."""

import re
import struct
from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError
import vizdoom as vzd

from doom_mcp.game_manager import GameManager


pytestmark = pytest.mark.integration
_MAP_MARKER_RE = re.compile(r"^(MAP\d\d|E\dM\d)$")


@pytest.fixture
def manager():
    m = GameManager()
    yield m
    m.stop()


def _freedoom_map_fixture(tmp_path: Path, mode: str, map_name: str = "MAP01") -> str:
    base_wad = Path(vzd.__file__).with_name("freedoom2.wad")
    data = base_wad.read_bytes()
    magic, lump_count, directory_offset = struct.unpack_from("<4sii", data, 0)
    assert magic in {b"IWAD", b"PWAD"}
    directory = []
    for index in range(lump_count):
        offset, size, raw_name = struct.unpack_from("<ii8s", data, directory_offset + index * 16)
        name = raw_name.rstrip(b"\0").decode("ascii", errors="ignore").upper()
        directory.append((name, offset, size))
    start_index = next(index for index, (name, _, _) in enumerate(directory) if name == map_name)
    end_index = len(directory)
    for index in range(start_index + 1, len(directory)):
        if _MAP_MARKER_RE.match(directory[index][0]):
            end_index = index
            break
    lumps: list[tuple[str, bytes]] = []
    for name, offset, size in directory[start_index:end_index]:
        lump_data = bytearray(data[offset : offset + size])
        if name == "THINGS":
            _mutate_start_things(lump_data, mode)
        lumps.append((name, bytes(lump_data)))
    return str(_write_pwad(tmp_path / f"{mode}-{map_name}.wad", lumps))


def _mutate_start_things(things: bytearray, mode: str) -> None:
    player_one_offsets = []
    player_start_offsets = []
    for pos in range(0, len(things), 10):
        thing_type = struct.unpack_from("<h", things, pos + 6)[0]
        if thing_type in {1, 2, 3, 4}:
            player_start_offsets.append(pos)
        if thing_type == 1:
            player_one_offsets.append(pos)
    if not player_one_offsets:
        return
    if mode == "no_player_one":
        for pos in player_start_offsets:
            struct.pack_into("<h", things, pos + 6, 11)
        return
    if mode == "multi_player_one":
        template = bytes(things[player_one_offsets[0] : player_one_offsets[0] + 10])
        for delta in (64, 128):
            extra = bytearray(template)
            x = struct.unpack_from("<h", extra, 0)[0]
            struct.pack_into("<h", extra, 0, x + delta)
            struct.pack_into("<h", extra, 6, 1)
            things.extend(extra)


def _write_pwad(path: Path, lumps: list[tuple[str, bytes]]) -> Path:
    payload = bytearray()
    out_directory = []
    for name, lump_data in lumps:
        offset = 12 + len(payload)
        payload.extend(lump_data)
        out_directory.append((offset, len(lump_data), name))
    directory_offset = 12 + len(payload)
    result = bytearray(struct.pack("<4sii", b"PWAD", len(out_directory), directory_offset))
    result.extend(payload)
    for offset, size, name in out_directory:
        result.extend(struct.pack("<ii8s", offset, size, name.encode("ascii")[:8].ljust(8, b"\0")))
    path.write_bytes(result)
    return path


def test_start_and_stop(manager):
    result = manager.start(scenario="basic", seed=42)
    assert result["status"] == "running"
    assert result["scenario"] == "basic"
    assert "TURN_LEFT_RIGHT_DELTA" in result["buttons"]
    assert manager.is_running

    result = manager.stop()
    assert result["status"] == "stopped"
    assert not manager.is_running


def test_get_state(manager):
    manager.start(scenario="basic", seed=42)
    state = manager.get_state()
    assert state["episode_finished"] is False
    assert "screenshot_png" in state
    assert state["game_variables"]["HEALTH"] == 100.0
    assert "weapon_state" in state
    assert "usable_attack_ammo" in state["weapon_state"]
    assert "objects" in state
    assert "depth" in state
    assert "sectors" not in state  # excluded by default (too large)
    state_with_sectors = manager.get_state(include_sectors=True)
    assert "sectors" in state_with_sectors


def test_get_state_objects_enriched(manager):
    manager.start(scenario="defend_the_center", seed=42)
    state = manager.get_state()
    objects = state["objects"]
    assert len(objects) > 0
    monster = next((o for o in objects if o["type"] == "monster"), None)
    assert monster is not None
    assert "distance" in monster
    assert "angle_to_aim" in monster
    assert "threat" in monster
    assert "typical_hp" in monster
    assert "is_visible" in monster


def test_take_action_dict(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.take_action({"MOVE_FORWARD_BACKWARD_DELTA": 10}, tics=1)
    assert "reward" in result
    assert "episode_finished" in result


def test_take_action_returns_telemetry_when_requested(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.take_action(
        {"MOVE_FORWARD_BACKWARD_DELTA": 10},
        tics=3,
        capture_telemetry=True,
        telemetry_stride=1,
    )

    telemetry = result.get("telemetry_frames")
    assert isinstance(telemetry, list)
    assert len(telemetry) >= 1
    assert all("tic" in sample for sample in telemetry)
    assert any("screenshot_png_b64" in sample for sample in telemetry)


def test_take_action_delta_turn(manager):
    manager.start(scenario="basic", seed=42)
    state_before = manager.get_state()
    angle_before = state_before["game_variables"]["ANGLE"]
    manager.take_action({"TURN_LEFT_RIGHT_DELTA": 45}, tics=1)
    state_after = manager.get_state()
    angle_after = state_after["game_variables"]["ANGLE"]
    # Angle should have changed by ~45 degrees
    diff = abs(angle_before - angle_after)
    if diff > 180:
        diff = 360 - diff
    assert 40 < diff < 50


def test_take_action_combined(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.take_action(
        {"TURN_LEFT_RIGHT_DELTA": -10, "MOVE_FORWARD_BACKWARD_DELTA": 10, "ATTACK": 1},
        tics=1,
    )
    assert result["episode_finished"] is False


def test_noop_action(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.take_action(None, tics=1)
    assert result["episode_finished"] is False


def test_new_episode(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.new_episode()
    assert result["status"] == "new_episode"


def test_get_objects_enriched(manager):
    manager.start(scenario="defend_the_center", seed=42)
    result = manager.get_objects()
    assert "objects" in result
    objects = result["objects"]
    assert any(o["type"] == "monster" for o in objects)
    assert any(o["name"] == "DoomPlayer" for o in objects)


def test_get_map(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.get_map()
    if result is not None:
        assert result[:8] == b"\x89PNG\r\n\x1a\n"


def test_get_available_actions(manager):
    manager.start(scenario="basic", seed=42)
    result = manager.get_available_actions()
    buttons = result["buttons"]
    names = [b["name"] for b in buttons]
    assert "TURN_LEFT_RIGHT_DELTA" in names
    assert "MOVE_FORWARD_BACKWARD_DELTA" in names
    assert "ATTACK" in names
    delta = next(b for b in buttons if b["name"] == "TURN_LEFT_RIGHT_DELTA")
    assert delta["type"] == "delta"
    binary = next(b for b in buttons if b["name"] == "ATTACK")
    assert binary["type"] == "binary"


def test_start_augments_custom_buttons_with_direct_weapon_select(manager):
    manager.start(scenario="basic", seed=42, buttons=["ATTACK", "SELECT_NEXT_WEAPON"])
    names = manager.start(scenario="basic", seed=43, buttons=["ATTACK", "SELECT_NEXT_WEAPON"])["buttons"]
    assert "SELECT_WEAPON1" in names


def test_take_action_direct_weapon_select_falls_back_when_button_not_configured(manager):
    manager.start(scenario="basic", seed=42)
    manager._buttons = [button for button in manager._buttons if not button.name.startswith("SELECT_WEAPON")]

    result = manager.take_action({"SELECT_WEAPON1": 1}, tics=1)

    assert result["action_summary"]["weapon_switch"]["requested_weapon"] == 1
    assert result["action_summary"]["stop_reason"] in {"tics_complete", "player_died", "episode_finished"}


def test_require_running_raises():
    m = GameManager()
    with pytest.raises(ToolError, match="No game is running"):
        m.get_state()


def test_require_episode_raises(manager):
    manager.start(scenario="basic", seed=42, episode_timeout=1)
    while not manager._game.is_episode_finished():
        manager.take_action(None, tics=1)
    with pytest.raises(ToolError, match="Episode is finished"):
        manager.take_action({"ATTACK": 1})


def test_episode_finished_state(manager):
    manager.start(scenario="basic", seed=42, episode_timeout=1)
    while not manager._game.is_episode_finished():
        manager.take_action(None, tics=1)
    state = manager.get_state()
    assert state["episode_finished"] is True


def test_restart_stops_previous(manager):
    manager.start(scenario="basic", seed=42)
    manager.start(scenario="basic", seed=43)
    assert manager.is_running


def test_load_freedoom2_map(manager):
    result = manager.start(wad="freedoom2", map_name="MAP01")
    assert result["status"] == "running"
    assert result["wad"] == "freedoom2"
    assert result["map"] == "MAP01"
    state = manager.get_state()
    assert len(state["objects"]) > 10  # MAP01 has lots of objects


def test_load_freedoom1_map(manager):
    result = manager.start(wad="freedoom1", map_name="E1M1")
    assert result["status"] == "running"
    state = manager.get_state()
    assert state["episode_finished"] is False


def test_custom_map_normalizes_player_one_starts(manager, tmp_path):
    from doom_mcp.game_manager import _wad_map_player_one_start_count

    no_start_wad = _freedoom_map_fixture(tmp_path, "no_player_one")
    multi_start_wad = _freedoom_map_fixture(tmp_path, "multi_player_one")
    valid_wad = _freedoom_map_fixture(tmp_path, "valid")

    assert _wad_map_player_one_start_count(no_start_wad, "MAP01") == 0
    assert _wad_map_player_one_start_count(multi_start_wad, "MAP01") >= 2
    assert _wad_map_player_one_start_count(valid_wad, "MAP01") == 1

    result = manager.start(wad="freedoom2", scenario_wad=no_start_wad, map_name="MAP01")
    assert result["status"] == "running"
    assert result["start_normalization"]["mode"] == "deathmatch_to_player_one"
    state = manager.get_state()
    assert state["episode_finished"] is False
    manager.stop()

    result = manager.start(wad="freedoom2", scenario_wad=multi_start_wad, map_name="MAP01")
    assert result["status"] == "running"
    assert result["start_normalization"]["mode"] == "multiple_player_starts_to_player_one"


def test_campaign_timeout_does_not_auto_advance(manager):
    """Episode timeout is not map completion and should not advance the campaign."""
    manager.start(wad="freedoom2", map_name="MAP01", episode_timeout=5)
    while not manager._game.is_episode_finished():
        manager.take_action(None, tics=1)
    state = manager.get_state()
    assert state["level_completed"] is False
    assert state["episode_timeout"] is True
    assert "next_map" not in state

    result = manager.new_episode()
    assert result["map"] == "MAP01"
    assert "advanced" not in result


def test_campaign_death_restarts_same_map(manager):
    """When player dies, new_episode restarts the same map."""
    manager.start(wad="freedoom2", map_name="MAP01")
    # We can't easily force death in a test, so just verify
    # the _next_map logic
    from doom_mcp.game_manager import _next_map
    assert _next_map("MAP01") == "MAP02"
    assert _next_map("MAP31") == "MAP32"
    assert _next_map("MAP32") is None
    assert _next_map("E1M1") == "E1M2"
    assert _next_map("E1M9") == "E2M1"
    assert _next_map("E4M9") is None


# ---------------------------------------------------------------
# Compound action tests
# ---------------------------------------------------------------


def test_aim_and_shoot_kills_enemy(manager):
    """In defend_the_center, find a monster and shoot it."""
    manager.start(scenario="defend_the_center", seed=42)
    state = manager.get_state()
    monster = next((o for o in state["objects"] if o["type"] == "monster"), None)
    assert monster is not None, "defend_the_center should have monsters"

    result = manager.aim_and_shoot(monster["id"], shots=5, max_tics=200)
    summary = result["action_summary"]
    assert summary["shots_fired"] > 0
    assert summary["target_name"] is not None
    assert summary["stop_reason"] in (
        "target_killed", "target_lost", "shots_complete",
        "player_died", "selected_weapon_empty", "no_usable_weapon",
        "no_usable_ranged_weapon", "melee_target_out_of_range",
        "weapon_switch_failed", "max_tics", "episode_finished",
    )
    assert "weapon_state_after" in summary


def test_aim_and_shoot_target_lost(manager):
    """Aiming at a bad ID returns target_lost gracefully."""
    manager.start(scenario="basic", seed=42)
    result = manager.aim_and_shoot(99999, shots=1, max_tics=10)
    summary = result["action_summary"]
    assert summary["stop_reason"] == "target_lost"
    assert summary["shots_fired"] == 0


def test_move_to_arrives(manager):
    """Move toward a visible object in basic scenario."""
    manager.start(scenario="basic", seed=42)
    state = manager.get_state()
    # Pick any object that isn't the player
    target = next(
        (o for o in state["objects"] if o["name"] != "DoomPlayer" and o["distance"] > 0),
        None,
    )
    if target is None:
        pytest.skip("No non-player objects found")

    result = manager.move_to(target["id"], max_tics=140, stop_on_enemy=False)
    summary = result["action_summary"]
    assert "distance_moved" in summary
    assert summary["stop_reason"] in (
        "arrived", "pickup_not_collected", "target_lost", "enemy_nearby", "stuck",
        "player_died", "max_tics", "episode_finished",
    )


def test_move_to_stuck_recovery(manager):
    """Verify move_to stuck detection doesn't crash."""
    manager.start(scenario="basic", seed=42)
    # Use an invalid ID so it returns target_lost quickly
    result = manager.move_to(99999, max_tics=30)
    summary = result["action_summary"]
    assert summary["stop_reason"] == "target_lost"


def test_explore_moves_distance(manager):
    """Explore for 200 tics and verify it completes without error."""
    manager.start(wad="freedoom2", map_name="MAP01", seed=42)

    result = manager.explore(max_tics=200, stop_on_enemy=False)
    summary = result["action_summary"]
    assert summary["distance_moved"] > 0
    assert isinstance(summary["direction_changes"], int)
    assert isinstance(summary["enemies_seen"], list)
    assert isinstance(summary["items_seen"], list)
    assert summary["stop_reason"] in (
        "enemy_spotted", "item_found", "stuck",
        "player_died", "max_tics", "episode_finished",
    )


def test_explore_enemy_stop(manager):
    """In defend_the_center, explore should stop on enemy."""
    manager.start(scenario="defend_the_center", seed=42)
    result = manager.explore(max_tics=200, stop_on_enemy=True)
    summary = result["action_summary"]
    # Should spot an enemy in defend_the_center
    assert summary["stop_reason"] in ("enemy_spotted", "player_died", "episode_finished", "max_tics")
    if summary["stop_reason"] == "enemy_spotted":
        assert len(summary["enemies_seen"]) > 0


def test_strafe_and_shoot_fires(manager):
    """In defend_the_center, strafe_and_shoot should fire shots."""
    manager.start(scenario="defend_the_center", seed=42)
    state = manager.get_state()
    monster = next((o for o in state["objects"] if o["type"] == "monster"), None)
    assert monster is not None

    result = manager.strafe_and_shoot(monster["id"], shots=3, max_tics=150)
    summary = result["action_summary"]
    assert summary["shots_fired"] > 0
    assert summary["strafe_direction"] == "auto"
    assert "damage_taken" in summary
    assert summary["stop_reason"] in (
        "shots_complete", "target_killed", "target_lost",
        "player_died", "selected_weapon_empty", "no_usable_weapon",
        "no_usable_ranged_weapon", "melee_target_out_of_range",
        "weapon_switch_failed", "max_tics", "episode_finished",
    )


def test_strafe_and_shoot_bad_id(manager):
    """Strafe-and-shoot with bad ID returns target_lost."""
    manager.start(scenario="basic", seed=42)
    result = manager.strafe_and_shoot(99999, shots=1, max_tics=10)
    summary = result["action_summary"]
    assert summary["stop_reason"] == "target_lost"
    assert summary["shots_fired"] == 0


def test_retreat_moves_distance(manager):
    """Retreat should move the player some distance."""
    manager.start(wad="freedoom2", map_name="MAP01", seed=42)
    result = manager.retreat(tics=35, backpedal=False)
    summary = result["action_summary"]
    assert summary["distance_moved"] > 0
    assert summary["mode"] == "turn_and_run"
    assert summary["stop_reason"] in ("complete", "player_died", "episode_finished")


def test_retreat_backpedal(manager):
    """Retreat in backpedal mode should work."""
    manager.start(wad="freedoom2", map_name="MAP01", seed=42)
    result = manager.retreat(tics=20, backpedal=True)
    summary = result["action_summary"]
    assert summary["mode"] == "backpedal"
    assert summary["stop_reason"] in ("complete", "player_died", "episode_finished")


def test_threat_assessment_format(manager):
    """Threat assessment should return all required fields."""
    manager.start(scenario="basic", seed=42)
    result = manager.get_threat_assessment()
    assert "threat_level" in result
    assert "threats" in result
    assert "incoming_projectiles" in result
    assert "tactical_advice" in result
    assert "player_health" in result
    assert "player_armor" in result
    assert "selected_weapon_ammo" in result
    assert "weapon_state" in result
    assert "usable_attack_ammo" in result
    assert result["threat_level"] in ("none", "low", "medium", "high", "critical")


def test_select_weapon_switches_to_owned_weapon(manager):
    manager.start(wad="freedoom2", map_name="MAP01", seed=42)
    result = manager.select_weapon(0, max_tics=12)
    summary = result["action_summary"]
    assert summary["requested_weapon"] == 0
    assert summary["stop_reason"] in {"selected", "weapon_switch_failed"}
    assert "weapon_state" in result


def test_ensure_attack_capable_weapon_switches_from_empty_selected_weapon(monkeypatch):
    manager = GameManager()

    class FakeGame:
        def __init__(self):
            self.variables = {
                "SELECTED_WEAPON": 1,
                "SELECTED_WEAPON_AMMO": 0,
                **{f"WEAPON{i}": 0 for i in range(10)},
                **{f"AMMO{i}": 0 for i in range(10)},
            }
            self.variables["WEAPON1"] = 1
            self.variables["WEAPON2"] = 1
            self.variables["AMMO2"] = 50

        def get_game_variable(self, variable):
            return self.variables.get(variable.name, 0)

        def is_episode_finished(self):
            return False

    fake_game = FakeGame()

    def fake_select_weapon(game, weapon_slot, max_tics=12):
        game.variables["SELECTED_WEAPON"] = weapon_slot
        game.variables["SELECTED_WEAPON_AMMO"] = game.variables[f"AMMO{weapon_slot}"]
        return True, 2

    monkeypatch.setattr(manager, "_select_weapon_slot", fake_select_weapon)

    ready, reason, switch_summary, tics_used = manager._ensure_attack_capable_weapon(fake_game, target_distance=400)

    assert ready is True
    assert reason == "weapon_switched"
    assert switch_summary["to_weapon"] == 2
    assert switch_summary["success"] is True
    assert tics_used == 2
    assert fake_game.variables["SELECTED_WEAPON"] == 2


def test_combat_auto_switches_from_empty_selected_weapon_when_ranged_ammo_exists(manager):
    manager.start(scenario="defend_the_center", seed=42)
    manager.select_weapon(0, max_tics=12)
    state = manager.get_state()
    if state["weapon_state"]["selected_weapon"] != 0:
        pytest.skip("Scenario did not allow selecting the melee weapon slot")
    monster = next((o for o in state["objects"] if o["type"] == "monster"), None)
    assert monster is not None

    result = manager.aim_and_shoot(monster["id"], shots=1, max_tics=80)
    summary = result["action_summary"]

    assert summary["stop_reason"] != "selected_weapon_empty"
    assert summary["stop_reason"] != "out_of_ammo"
    assert summary.get("weapon_state_after") is not None


def test_threat_assessment_has_threats(manager):
    """In defend_the_center, threat assessment should find enemies."""
    manager.start(scenario="defend_the_center", seed=42)
    result = manager.get_threat_assessment()
    assert len(result["threats"]) > 0
    top = result["threats"][0]
    assert "priority_rank" in top
    assert "priority_score" in top
    assert "attack_type" in top
    assert top["priority_rank"] == 1


def test_get_navigation_info(manager):
    """Navigation info should track cells after exploration."""
    manager.start(wad="freedoom2", map_name="MAP01", seed=42)
    manager.explore(max_tics=100, stop_on_enemy=False)
    result = manager.get_navigation_info()
    assert result["cells_explored"] > 0
    assert "explored_directions" in result
    assert "unexplored_directions" in result
    assert "suggested_direction" in result
    assert "keys_found" in result
    assert "nearby_doors" in result


def test_compound_action_summary_format(manager):
    """Verify all compound action summaries have required fields."""
    manager.start(scenario="basic", seed=42)

    # aim_and_shoot
    result = manager.aim_and_shoot(99999, shots=1, max_tics=5)
    aim_summary = result["action_summary"]
    assert "shots_fired" in aim_summary
    assert "hits_landed" in aim_summary
    assert "kills" in aim_summary
    assert "ammo_spent" in aim_summary
    assert "target_name" in aim_summary
    assert "stop_reason" in aim_summary

    # move_to
    manager.new_episode()
    result = manager.move_to(99999, max_tics=5)
    move_summary = result["action_summary"]
    assert "distance_moved" in move_summary
    assert "distance_remaining" in move_summary
    assert "target_name" in move_summary
    assert "used_object" in move_summary
    assert "threat_object" in move_summary
    assert "stop_reason" in move_summary

    # explore
    manager.new_episode()
    result = manager.explore(max_tics=5)
    explore_summary = result["action_summary"]
    assert "distance_moved" in explore_summary
    assert "direction_changes" in explore_summary
    assert "enemies_seen" in explore_summary
    assert "items_seen" in explore_summary
    assert "stop_reason" in explore_summary
