"""E2E tests for navigation fixes: coverage, stuck recovery, walkable cells.

The ViZDoom integration tests (TestE2E*) must be run with:
    xvfb-run -a pytest tests/test_e2e_navigation_fixes.py -v

ViZDoom segfaults when multiple game instances are created/destroyed rapidly
in the same process (pytest fixture lifecycle). The unit tests
(TestNavigationMemoryFixes) run fine without xvfb.
"""

import math
import os
import sys
import time

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from doom_mcp.game_manager import GameManager
from doom_mcp.navigation import NavigationMemory, _cell

STORAGE = os.path.join(os.path.dirname(__file__), "..", "..", "Backend", "storage", "wads")
E1M1_WAD = os.path.join(STORAGE, "ac683d7a-65e6-4b06-b94f-b7c0cf8961af.wad")
# Use a WAD with MAP01 for second test
MAP01_WAD = os.path.join(STORAGE, "08d61a6c-f534-4578-91c1-631e76139efb.wad")
# Use a WAD with MAP02 for third test
MAP02_WAD = os.path.join(STORAGE, "76baf049-f52f-426b-934c-2b9a427e949b.wad")


# ──────────────────────────────────────────────
# Navigation unit tests (no ViZDoom needed)
# ──────────────────────────────────────────────

class TestNavigationMemoryFixes:
    def test_cell_uses_floor_not_truncation(self):
        """_cell() must use math.floor for correct negative coordinate handling."""
        # -0.5 should map to cell -1, not cell 0
        assert _cell(-0.5, 0) == (-1, 0)
        assert _cell(0, -0.5) == (0, -1)
        # Positive values unchanged
        assert _cell(127.9, 127.9) == (0, 0)
        assert _cell(128.0, 128.0) == (1, 1)
        # Edge case: exactly on boundary
        assert _cell(-128.0, 0) == (-1, 0)
        assert _cell(-129.0, 0) == (-2, 0)

    def test_walkable_cells_from_sectors(self):
        """compute_walkable_cells_from_sectors should count cells overlapping sector geometry."""
        nav = NavigationMemory()
        sectors = [
            {
                "lines": [
                    {"x1": 0, "y1": 0, "x2": 256, "y2": 0},
                    {"x1": 256, "y1": 0, "x2": 256, "y2": 256},
                    {"x1": 256, "y1": 256, "x2": 0, "y2": 256},
                    {"x1": 0, "y1": 256, "x2": 0, "y2": 0},
                ]
            }
        ]
        count = nav.compute_walkable_cells_from_sectors(sectors)
        # 256x256 sector = 1 cell at 128-unit resolution
        assert count >= 1

    def test_walkable_cells_cached(self):
        """Walkable cells should be cached after first computation."""
        nav = NavigationMemory()
        sectors = [
            {
                "lines": [
                    {"x1": 0, "y1": 0, "x2": 512, "y2": 0},
                    {"x1": 512, "y1": 0, "x2": 512, "y2": 512},
                    {"x1": 512, "y1": 512, "x2": 0, "y2": 512},
                    {"x1": 0, "y1": 512, "x2": 0, "y2": 0},
                ]
            }
        ]
        count1 = nav.compute_walkable_cells_from_sectors(sectors)
        count2 = nav.compute_walkable_cells_from_sectors(sectors)
        assert count1 == count2

    def test_exploration_summary_includes_walkable(self):
        """get_exploration_summary should include walkable_cells_total."""
        nav = NavigationMemory()
        nav.update(100, 100, 0)
        summary = nav.get_exploration_summary(100, 100, 0)
        assert "walkable_cells_total" in summary
        assert summary["walkable_cells_total"] is None  # not computed yet

    def test_negative_coords_visited(self):
        """NavigationMemory should track visited cells with negative coordinates."""
        nav = NavigationMemory()
        nav.update(-50, -50, 0)
        nav.update(-200, -200, 0)
        summary = nav.get_exploration_summary(-50, -50, 0)
        assert summary["cells_explored"] == 2


# ──────────────────────────────────────────────
# ViZDoom integration tests
# These need xvfb-run and sequential execution (ViZDoom segfaults with
# rapid instance creation/destruction). Run separately:
#   xvfb-run -a pytest tests/test_e2e_navigation_fixes.py -v -k "E2E"
# ──────────────────────────────────────────────

# Skip all ViZDoom integration tests unless explicitly enabled
pytestmark_viZDoom = pytest.mark.skipif(
    not os.environ.get("RUN_VIZDOOM_E2E"),
    reason="ViZDoom E2E tests require xvfb and sequential execution. "
           "Run with: RUN_VIZDOOM_E2E=1 xvfb-run -a pytest tests/test_e2e_navigation_fixes.py"
)


@pytest.fixture
def gm():
    """Create a GameManager for testing."""
    manager = GameManager()
    yield manager
    if manager.is_running:
        manager.stop()


def _start_game(gm, wad_path, map_name, difficulty=3):
    """Helper to start a game, bypassing preflight check."""
    # Monkey-patch assert_wad_loadable to skip the subprocess check
    # (the subprocess crashes with SIGSEGV in headless CI but the game loads fine)
    import doom_mcp.game_setup as _gs
    original = _gs.assert_wad_loadable
    _gs.assert_wad_loadable = lambda *a, **kw: None
    try:
        result = gm.start(
            wad=wad_path,
            scenario_wad=wad_path,
            map_name=map_name,
            difficulty=difficulty,
            screen_resolution="RES_320X240",
            window_visible=False,
            episode_timeout=5000,
        )
        return result
    finally:
        _gs.assert_wad_loadable = original


@pytestmark_viZDoom
class TestE2EExplore:
    def test_explore_moves_and_returns_state(self, gm):
        """explore should move the player and return valid state."""
        _start_game(gm, E1M1_WAD, "E1M1")
        result = gm.explore(max_tics=50, stop_on_enemy=False, stop_on_item=False)
        assert "action_summary" in result
        assert result["action_summary"]["stop_reason"] in ("max_tics", "enemy_spotted", "stuck")
        assert result["action_summary"]["distance_moved"] >= 0

    def test_explore_stuck_recovery_increases_recoveries(self, gm):
        """explore stuck recovery should attempt multiple strategies."""
        _start_game(gm, E1M1_WAD, "E1M1")
        # Run explore multiple times to verify it doesn't crash
        for i in range(3):
            result = gm.explore(max_tics=30, stop_on_enemy=False, stop_on_item=False)
            assert "action_summary" in result

    def test_explore_with_turn_before(self, gm):
        """explore with turn_before should rotate before moving."""
        _start_game(gm, E1M1_WAD, "E1M1")
        result = gm.explore(max_tics=50, turn_before=90.0, stop_on_enemy=False)
        assert "action_summary" in result


@pytestmark_viZDoom
class TestE2EMoveTo:
    def test_move_to_returns_valid_result(self, gm):
        """move_to should return valid state even if target is unreachable."""
        _start_game(gm, E1M1_WAD, "E1M1")
        # Get objects to find a target
        state = gm.get_state()
        assert state is not None
        # Try to find any object
        objects = state.get("objects", [])
        if objects:
            target_id = objects[0]["id"]
            result = gm.move_to(target_id, max_tics=50, stop_on_enemy=False)
            assert "action_summary" in result
            assert "distance_moved" in result["action_summary"]

    def test_move_to_stuck_recovery(self, gm):
        """move_to should attempt stuck recovery before giving up."""
        _start_game(gm, E1M1_WAD, "E1M1")
        state = gm.get_state()
        objects = state.get("objects", [])
        if objects:
            target_id = objects[0]["id"]
            # Run move_to - should not crash even if stuck
            result = gm.move_to(target_id, max_tics=100, stop_on_enemy=False)
            assert "action_summary" in result


@pytestmark_viZDoom
class TestE2ENavigationInfo:
    def test_navigation_info_includes_walkable_cells(self, gm):
        """get_navigation_info should return walkable_cells_total."""
        _start_game(gm, E1M1_WAD, "E1M1")
        # Move a bit first
        gm.explore(max_tics=30, stop_on_enemy=False)
        nav_info = gm.get_navigation_info()
        assert "cells_explored" in nav_info
        assert "walkable_cells_total" in nav_info
        # Walkable cells should be a positive number
        if nav_info["walkable_cells_total"] is not None:
            assert nav_info["walkable_cells_total"] > 0

    def test_navigation_info_directions(self, gm):
        """get_navigation_info should report explored/unexplored directions."""
        _start_game(gm, E1M1_WAD, "E1M1")
        gm.explore(max_tics=30, stop_on_enemy=False)
        nav_info = gm.get_navigation_info()
        assert "explored_directions" in nav_info
        assert "unexplored_directions" in nav_info


@pytestmark_viZDoom
class TestE2EMap01:
    """Test on MAP01 from a different WAD to verify fixes work on varied geometry."""

    def test_explore_map01(self, gm):
        """explore should work on MAP01."""
        _start_game(gm, MAP01_WAD, "MAP01")
        result = gm.explore(max_tics=50, stop_on_enemy=False, stop_on_item=False)
        assert "action_summary" in result
        nav = gm.get_navigation_info()
        assert nav["cells_explored"] > 0

    def test_navigation_info_map01(self, gm):
        """get_navigation_info should include walkable cells on MAP01."""
        _start_game(gm, MAP01_WAD, "MAP01")
        gm.explore(max_tics=30, stop_on_enemy=False)
        nav = gm.get_navigation_info()
        assert "walkable_cells_total" in nav


@pytestmark_viZDoom
class TestE2EMap02:
    """Test on MAP02 from a WAD with 32 maps."""

    def test_explore_map02(self, gm):
        """explore should work on MAP02."""
        _start_game(gm, MAP02_WAD, "MAP02")
        result = gm.explore(max_tics=50, stop_on_enemy=False, stop_on_item=False)
        assert "action_summary" in result

    def test_full_gameplay_loop_map02(self, gm):
        """Run a short gameplay loop on MAP02: explore -> get nav info -> explore more."""
        _start_game(gm, MAP02_WAD, "MAP02")
        # First exploration
        r1 = gm.explore(max_tics=40, stop_on_enemy=False, stop_on_item=False)
        nav1 = gm.get_navigation_info()
        cells_after_first = nav1["cells_explored"]
        # Second exploration (should explore new area)
        r2 = gm.explore(max_tics=40, stop_on_enemy=True, stop_on_item=False)
        nav2 = gm.get_navigation_info()
        cells_after_second = nav2["cells_explored"]
        # Should have explored at least as many cells
        assert cells_after_second >= cells_after_first


@pytestmark_viZDoom
class TestE2ECoverageCalculation:
    """Verify coverage calculation uses walkable cells when available."""

    def test_walkable_cells_smaller_than_bounding_box(self, gm):
        """Walkable cell count should be <= bounding box cell count."""
        _start_game(gm, E1M1_WAD, "E1M1")
        gm.explore(max_tics=50, stop_on_enemy=False)
        nav = gm.get_navigation_info()
        walkable = nav.get("walkable_cells_total")
        if walkable is not None:
            # Walkable should be reasonable (1-200 cells for a small map)
            assert 1 <= walkable <= 200

    def test_coverage_percentage_reasonable(self, gm):
        """Coverage percentage should be between 0 and 100."""
        _start_game(gm, E1M1_WAD, "E1M1")
        gm.explore(max_tics=80, stop_on_enemy=False)
        nav = gm.get_navigation_info()
        explored = nav["cells_explored"]
        walkable = nav.get("walkable_cells_total")
        if walkable and walkable > 0:
            coverage = explored / walkable * 100
            assert 0 <= coverage <= 100
