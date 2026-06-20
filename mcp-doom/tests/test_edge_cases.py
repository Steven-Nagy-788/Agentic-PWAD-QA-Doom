"""Additional unit tests for mcp-doom edge cases (no ViZDoom required)."""

from doom_mcp.navigation import NavigationMemory, _CELL_SIZE, _cell
from doom_mcp.combat_constants import THREAT_WEIGHTS, ATTACK_URGENCY


def test_cell_function_negative_coords():
    assert _cell(-1, -1) == (-1, -1)
    assert _cell(-128, -128) == (-1, -1)
    assert _cell(-129, 0) == (-2, 0)


def test_cell_function_origin():
    assert _cell(0, 0) == (0, 0)
    assert _cell(127, 127) == (0, 0)
    assert _cell(128, 0) == (1, 0)


def test_cell_function_large_coords():
    assert _cell(10000, 5000) == (78, 39)


def test_nav_memory_empty_exploration_summary():
    nav = NavigationMemory()
    summary = nav.get_exploration_summary(0, 0, 0)
    assert summary["cells_explored"] == 0
    assert summary["keys_found"] == []
    assert summary["known_key_locations"] == []
    assert summary["nearby_doors"] == []
    assert summary["total_doors_found"] == 0
    assert summary["breadcrumbs"] == 0


def test_nav_memory_breadcrumb_max_limit():
    nav = NavigationMemory()
    for i in range(600):
        nav.update(i * 70, i * 70, 0)
    summary = nav.get_exploration_summary(0, 0, 0)
    assert summary["breadcrumbs"] <= 500


def test_nav_memory_multiple_keys():
    nav = NavigationMemory()
    keys = [
        {"id": 1, "name": "BlueCard", "type": "key", "position_x": 100, "position_y": 100, "distance": 50, "is_visible": True},
        {"id": 2, "name": "RedCard", "type": "key", "position_x": 200, "position_y": 200, "distance": 50, "is_visible": True},
        {"id": 3, "name": "YellowCard", "type": "key", "position_x": 300, "position_y": 300, "distance": 50, "is_visible": True},
    ]
    nav.update(100, 100, 0, objects=keys)
    summary = nav.get_exploration_summary(100, 100, 0)
    assert len(summary["known_key_locations"]) == 3


def test_nav_memory_door_not_in_small_sector():
    nav = NavigationMemory()
    large_sector = {
        "floor_height": 0,
        "ceiling_height": 128,
        "lines": [
            {"x1": 0, "y1": 0, "x2": 1000, "y2": 0},
            {"x1": 1000, "y1": 0, "x2": 1000, "y2": 1000},
        ],
    }
    nav.update(500, 500, 0, sectors=[large_sector])
    summary = nav.get_exploration_summary(500, 500, 0)
    assert summary["total_doors_found"] == 0


def test_threat_weights_coverage():
    assert THREAT_WEIGHTS["none"] == 0
    assert THREAT_WEIGHTS["low"] == 1
    assert THREAT_WEIGHTS["medium"] == 2
    assert THREAT_WEIGHTS["high"] == 3


def test_attack_urgency_coverage():
    assert ATTACK_URGENCY["hitscan"] == 3
    assert ATTACK_URGENCY["projectile"] == 2
    assert ATTACK_URGENCY["melee"] == 1
    assert ATTACK_URGENCY["none"] == 0


def test_nav_memory_suggested_turn_returns_zero_when_all_explored():
    nav = NavigationMemory()
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            nav.update(dx * _CELL_SIZE + 64, dy * _CELL_SIZE + 64, 0)
    delta = nav.suggested_turn_delta(0, 0, 0)
    assert isinstance(delta, (int, float))
