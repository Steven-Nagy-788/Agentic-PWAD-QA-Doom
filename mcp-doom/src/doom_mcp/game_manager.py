"""Core game manager wrapping ViZDoom's DoomGame."""

import base64
import contextlib
import math
import os
import shutil
import struct
import sys
import tempfile
import threading
from contextlib import contextmanager

import vizdoom as vzd
from fastmcp.exceptions import ToolError

from . import game_setup as _game_setup
from .actions import BUTTON_NAMES, names_to_action_list
from .executor import AutonomousExecutor, ExecutorState, Objective, ObjectiveType
from .game_setup import (
    list_wad_maps,
    next_map,
    wad_map_start_info,
    wad_map_player_one_start_count,
)
from .navigation import NavigationMemory
from .objects import get_object_info
from .scenarios import get_scenario_config_path
from .state import (
    extract_depth_as_stats,
    extract_game_variables,
    extract_objects,
    extract_sectors,
    screen_buffer_to_png,
)

_ACTIONABLE_TYPES = {"monster", "player", "hazard", "projectile", "key", "weapon"}
_ITEM_TYPES = {"item", "ammo"}
_PICKUP_TYPES = {"item", "ammo", "weapon", "key"}
_NEARBY_RANGE = 1500.0  # units - items/ammo within this range are included
_MONSTER_RANGE = 4000.0  # units - monsters within this range are included

# Compound action constants
_MAP_EXIT_REWARD = 100.0
_WALL_CLOSE = 15.0        # depth buffer units (0-255 scale) - imminent collision
_WALL_NEAR = 40.0         # depth buffer units - start turning
_STUCK_WINDOW = 20        # tics to check for stuck
_STUCK_THRESHOLD = 15.0   # map units - min spread to not be stuck
_ARRIVE_DISTANCE = 64.0   # map units - close enough for move_to
_ENEMY_ALERT_DIST = 800.0 # map units - enemy proximity alert
_AIM_TOLERANCE = 3.0      # degrees - close enough to fire

# Backward-compatible aliases for tests and external debugging snippets.
_next_map = next_map
_list_wad_maps = list_wad_maps
_wad_map_player_one_start_count = wad_map_player_one_start_count
_PREFLIGHT_TIMEOUT_SECONDS = _game_setup._PREFLIGHT_TIMEOUT_SECONDS


def assert_wad_loadable(
    base_wad_path: str,
    scenario_wad_path: str,
    map_name: str | None,
    screen_resolution: str,
) -> None:
    """Validate a WAD load while honoring the legacy game_manager timeout knob."""
    original_timeout = _game_setup._PREFLIGHT_TIMEOUT_SECONDS
    _game_setup._PREFLIGHT_TIMEOUT_SECONDS = _PREFLIGHT_TIMEOUT_SECONDS
    try:
        _game_setup.assert_wad_loadable(base_wad_path, scenario_wad_path, map_name, screen_resolution)
    finally:
        _game_setup._PREFLIGHT_TIMEOUT_SECONDS = original_timeout


def _filter_objects(objects: list[dict]) -> list[dict]:
    """Filter objects to only actionable ones and slim down fields."""
    filtered = []
    for obj in objects:
        obj_type = obj.get("type", "")
        dist = obj.get("distance", 9999)
        visible = obj.get("is_visible", False)

        include = False
        if visible:
            include = True
        elif obj_type in _ACTIONABLE_TYPES and dist <= _MONSTER_RANGE:
            include = True
        elif obj_type in _ITEM_TYPES and dist <= _NEARBY_RANGE:
            include = True

        if include:
            slim = {
                "id": obj["id"],
                "name": obj["name"],
                "distance": obj["distance"],
                "angle_to_aim": obj["angle_to_aim"],
                "type": obj["type"],
                "threat": obj["threat"],
                "is_visible": visible,
            }
            # Only add fields when they carry useful info
            if obj["threat"] != "none":
                slim["attack_type"] = obj["attack_type"]
                slim["typical_hp"] = obj["typical_hp"]
            if visible and "screen_x" in obj:
                slim["screen_x"] = obj["screen_x"]
                slim["screen_y"] = obj["screen_y"]
            filtered.append(slim)
    filtered.sort(key=lambda obj: (not obj.get("is_visible", False), obj.get("distance", 999999)))
    return filtered


# Delta buttons for precise aiming + binary buttons for movement/actions.
# TURN_LEFT_RIGHT_DELTA: positive = turn right (degrees, multiplied by tics)
# LOOK_UP_DOWN_DELTA: positive = look down (degrees, multiplied by tics)
DEFAULT_BUTTONS = [
    # Delta buttons for precise control (value = amount per tic)
    "TURN_LEFT_RIGHT_DELTA",
    "LOOK_UP_DOWN_DELTA",
    "MOVE_FORWARD_BACKWARD_DELTA",
    "MOVE_LEFT_RIGHT_DELTA",
    # Binary buttons
    "ATTACK",
    "USE",
    "SPEED",
    "SELECT_NEXT_WEAPON",
    "SELECT_PREV_WEAPON",
    "JUMP",
    "CROUCH",
]

DEFAULT_VARIABLES = [
    # Vitals
    "HEALTH",
    "ARMOR",
    "DEAD",
    "ON_GROUND",
    # Position & orientation
    "POSITION_X",
    "POSITION_Y",
    "POSITION_Z",
    "ANGLE",
    "PITCH",
    "VELOCITY_X",
    "VELOCITY_Y",
    "VELOCITY_Z",
    # Combat
    "ATTACK_READY",
    "SELECTED_WEAPON",
    "SELECTED_WEAPON_AMMO",
    "AMMO0",
    "AMMO1",
    "AMMO2",
    "AMMO3",
    "AMMO4",
    "AMMO5",
    "AMMO6",
    # Weapons inventory
    "WEAPON0",
    "WEAPON1",
    "WEAPON2",
    "WEAPON3",
    "WEAPON4",
    "WEAPON5",
    "WEAPON6",
    "WEAPON7",
    # Stats
    "KILLCOUNT",
    "ITEMCOUNT",
    "SECRETCOUNT",
    "FRAGCOUNT",
    "DEATHCOUNT",
    "HITCOUNT",
    "HITS_TAKEN",
    "DAMAGECOUNT",
    "DAMAGE_TAKEN",
]

# Delta buttons accept numeric values, not just 0/1
DELTA_BUTTONS = {
    "TURN_LEFT_RIGHT_DELTA",
    "LOOK_UP_DOWN_DELTA",
    "MOVE_FORWARD_BACKWARD_DELTA",
    "MOVE_LEFT_RIGHT_DELTA",
    "MOVE_UP_DOWN_DELTA",
}


class GameManager:
    """Manages a single ViZDoom game instance."""

    def __init__(self) -> None:
        self._game: vzd.DoomGame | None = None
        self._buttons: list[vzd.Button] = []
        self._variable_names: list[str] = []
        self._scenario_name: str = ""
        self._wad: str | None = None
        self._current_map: str | None = None
        self._async: bool = False
        self._recording_path: str | None = None
        self._runtime_wad_path: str | None = None
        self._nav_memory = NavigationMemory()
        self._game_lock = threading.Lock()
        self._executor: AutonomousExecutor | None = None
        self._telemetry_frames: list[dict] | None = None
        self._telemetry_stride = 1
        self._telemetry_tics = 0

    @property
    def is_running(self) -> bool:
        return self._game is not None

    def _require_running(self) -> vzd.DoomGame:
        if self._game is None:
            raise ToolError(
                "No game is running. Call start_game first."
            )
        return self._game

    def _require_episode(self) -> vzd.DoomGame:
        game = self._require_running()
        if game.is_episode_finished():
            raise ToolError(
                "Episode is finished. Call new_episode to start a new one."
            )
        return game

    @contextmanager
    def _with_executor_paused(self):
        """Context manager to pause executor for legacy tool execution."""
        if self._executor is not None:
            self._executor.pause()
        try:
            yield
        finally:
            if self._executor is not None:
                self._executor.resume()

    @contextmanager
    def _capture_telemetry(self, enabled: bool, stride: int = 4):
        previous_frames = self._telemetry_frames
        previous_stride = self._telemetry_stride
        previous_tics = self._telemetry_tics
        self._telemetry_frames = [] if enabled else None
        self._telemetry_stride = max(1, int(stride or 1))
        self._telemetry_tics = 0
        try:
            yield
        finally:
            self._telemetry_frames = previous_frames
            self._telemetry_stride = previous_stride
            self._telemetry_tics = previous_tics

    def _begin_telemetry(self, enabled: bool, stride: int = 4) -> None:
        self._telemetry_frames = [] if enabled else None
        self._telemetry_stride = max(1, int(stride or 1))
        self._telemetry_tics = 0

    def _attach_telemetry(self, result: dict) -> dict:
        if self._telemetry_frames is not None:
            if not self._telemetry_frames and self._game is not None:
                sample = self._telemetry_sample(self._game)
                if sample is not None:
                    self._telemetry_frames.append(sample)
            result["telemetry_frames"] = list(self._telemetry_frames)
        self._telemetry_frames = None
        self._telemetry_tics = 0
        return result

    @staticmethod
    def _resolve_wad_path(wad: str) -> str:
        """Resolve a WAD name or path to a full file path."""
        # Shorthand names for bundled WADs
        bundled = {
            "freedoom1": os.path.join(os.path.dirname(vzd.__file__), "freedoom1.wad"),
            "freedoom2": os.path.join(os.path.dirname(vzd.__file__), "freedoom2.wad"),
        }
        if wad.lower() in bundled:
            return bundled[wad.lower()]
        if os.path.isabs(wad) and os.path.exists(wad):
            return wad
        raise ToolError(
            f"WAD not found: {wad!r}. Use 'freedoom1', 'freedoom2', "
            f"or an absolute path to a .wad file."
        )

    def _prepare_single_player_wad(self, wad_path: str, map_name: str | None) -> str:
        """Return a WAD path with exactly one Player 1 start for this map."""
        if not map_name:
            return wad_path
        start_info = wad_map_start_info(wad_path, map_name)
        player_starts = start_info["player_starts"]
        player_one_starts = start_info["player_one"]
        deathmatch_starts = start_info["deathmatch"]
        if len(player_one_starts) == 1 and len(player_starts) == 1:
            return wad_path
        if not player_starts and not deathmatch_starts:
            raise ToolError(
                f"Map {map_name.upper()} in {wad_path!r} has no Player 1 or deathmatch starts. "
                "Single-player ViZDoom runs need a start position."
            )

        handle = tempfile.NamedTemporaryFile(
            prefix="doom_mcp_",
            suffix=f"_{map_name.upper()}.wad",
            delete=False,
        )
        handle.close()
        runtime_path = handle.name
        shutil.copy2(wad_path, runtime_path)

        with open(runtime_path, "r+b") as runtime_wad:
            chosen_start = player_one_starts[0] if player_one_starts else (
                player_starts[0] if player_starts else deathmatch_starts[0]
            )
            runtime_wad.seek(chosen_start + 6)
            runtime_wad.write(struct.pack("<h", 1))

            for start_offset in player_starts:
                if start_offset == chosen_start:
                    continue
                runtime_wad.seek(start_offset + 6)
                runtime_wad.write(struct.pack("<h", 11))

            if chosen_start in deathmatch_starts:
                runtime_wad.seek(chosen_start + 6)
                runtime_wad.write(struct.pack("<h", 1))

        self._runtime_wad_path = runtime_path
        return runtime_path

    def _get_player_pos(self, game: vzd.DoomGame) -> tuple[float, float, float]:
        """Get player position and angle for computing relative object info."""
        px = game.get_game_variable(vzd.GameVariable.POSITION_X)
        py = game.get_game_variable(vzd.GameVariable.POSITION_Y)
        pa = game.get_game_variable(vzd.GameVariable.ANGLE)
        return px, py, pa

    def _extract_full_state(
        self,
        game: vzd.DoomGame,
        include_sectors: bool = False,
        include_depth: bool = True,
    ) -> dict:
        """Extract complete game state: variables, objects, and optionally sectors/depth."""
        state = game.get_state()
        variables = extract_game_variables(game, self._variable_names)
        px, py, pa = self._get_player_pos(game)
        all_objects = extract_objects(state, player_x=px, player_y=py, player_angle=pa)
        # Filter to actionable objects to keep response size manageable
        objects = _filter_objects(all_objects)
        screenshot_png = screen_buffer_to_png(state.screen_buffer)

        # Update navigation memory with full object list
        self._nav_memory.update(px, py, pa, objects=all_objects)

        result = {
            "episode_finished": False,
            "tic": state.tic,
            "game_variables": variables,
            "objects": objects,
            "total_reward": game.get_total_reward(),
            "screenshot_png": screenshot_png,
        }

        if include_sectors:
            result["sectors"] = extract_sectors(state)
        if include_depth and state.depth_buffer is not None:
            result["depth"] = extract_depth_as_stats(state.depth_buffer)

        return result

    def _finished_state(self, game: vzd.DoomGame, reward: float | None = None) -> dict:
        """Return state dict for a finished episode."""
        dead = game.get_game_variable(vzd.GameVariable.DEAD)
        level_completed = self._level_completed(game)
        variables = extract_game_variables(game, self._variable_names)
        result = {
            "episode_finished": True,
            "dead": bool(dead),
            "player_dead": bool(dead),
            "level_completed": level_completed,
            "episode_timeout": (not bool(dead)) and not level_completed,
            "total_reward": game.get_total_reward(),
            "game_variables": variables,
        }
        if reward is not None:
            result["reward"] = reward
        if self._current_map:
            result["map"] = self._current_map
            nxt = next_map(self._current_map)
            if nxt and level_completed:
                result["next_map"] = nxt
                result["hint"] = "Level completed! Call new_episode() to advance to next map."
            elif dead:
                result["hint"] = "You died. Call new_episode() to retry this map."
            else:
                result["hint"] = "Episode ended before map completion, likely because the tick budget expired."
        return result

    def _level_completed(self, game: vzd.DoomGame) -> bool:
        dead = game.get_game_variable(vzd.GameVariable.DEAD)
        return (not bool(dead)) and game.get_total_reward() >= _MAP_EXIT_REWARD

    def start(
        self,
        scenario: str = "basic",
        wad: str | None = None,
        scenario_wad: str | None = None,
        map_name: str | None = None,
        difficulty: int = 3,
        buttons: list[str] | None = None,
        variables: list[str] | None = None,
        screen_resolution: str = "RES_320X240",
        episode_timeout: int | None = None,
        render_hud: bool = False,
        window_visible: bool = False,
        async_player: bool = False,
        ticrate: int | None = None,
        seed: int | None = None,
        recording_path: str | None = None,
    ) -> dict:
        """Start a new game with the given configuration.

        Use scenario for ViZDoom's built-in scenarios, or wad+map_name
        for full Doom campaign maps. If wad is provided, scenario is ignored.

        Available WADs bundled with ViZDoom:
            "freedoom1" - Freedoom Phase 1 (Doom 1 format, maps E1M1-E4M9)
            "freedoom2" - Freedoom Phase 2 (Doom 2 format, maps MAP01-MAP32)
            Or provide an absolute path to any .wad file.

        Args:
            async_player: Use ASYNC_PLAYER mode so the game runs in real-time
                in a separate thread. The window shows smooth continuous gameplay
                instead of freezing between agent actions. Between take_action
                calls the player stands idle but the world keeps running.
            ticrate: Game speed in tics/sec for async mode (default 35 = normal
                Doom speed). Only affects ASYNC_PLAYER mode.
        """
        if self._game is not None:
            self.stop()

        button_names = buttons or DEFAULT_BUTTONS
        variable_names = variables or DEFAULT_VARIABLES

        # Validate button names
        for name in button_names:
            if name.upper() not in BUTTON_NAMES:
                raise ToolError(f"Unknown button {name!r}. Valid: {sorted(BUTTON_NAMES.keys())}")

        # Validate variable names
        for name in variable_names:
            if not hasattr(vzd.GameVariable, name.upper()):
                raise ToolError(
                    f"Unknown game variable {name!r}. "
                    f"Valid: {sorted(vzd.GameVariable.__members__.keys())}"
                )

        # Validate screen resolution
        try:
            resolution = getattr(vzd.ScreenResolution, screen_resolution)
        except AttributeError:
            raise ToolError(
                f"Unknown resolution {screen_resolution!r}. "
                f"Valid: {sorted(vzd.ScreenResolution.__members__.keys())}"
            )

        game = vzd.DoomGame()

        if wad is not None or scenario_wad is not None:
            # Load IWAD
            base_iwad = wad if wad is not None else os.environ.get("DOOM_DEFAULT_IWAD", "freedoom1")
            base_path = self._resolve_wad_path(base_iwad)
            game.set_doom_game_path(base_path)

            # Load PWAD if provided
            if scenario_wad is not None:
                # Validate PWAD path
                if not os.path.isabs(scenario_wad) or not os.path.exists(scenario_wad):
                    raise ToolError(
                        f"PWAD not found: {scenario_wad!r}. Provide an absolute path to a .wad file."
                    )
                try:
                    scenario_wad = self._prepare_single_player_wad(scenario_wad, map_name)
                    assert_wad_loadable(base_path, scenario_wad, map_name, screen_resolution)
                except Exception:
                    if self._runtime_wad_path is not None:
                        with contextlib.suppress(OSError):
                            os.unlink(self._runtime_wad_path)
                        self._runtime_wad_path = None
                    raise
                game.add_game_args(f"-file {scenario_wad}")

            if map_name:
                game.set_doom_map(map_name)
        else:
            # Built-in scenario mode
            try:
                cfg_path = get_scenario_config_path(scenario)
            except ValueError as e:
                raise ToolError(str(e))
            game.load_config(cfg_path)

        # Universal settings (override anything from .cfg)
        game.set_screen_format(vzd.ScreenFormat.RGB24)
        game.set_screen_resolution(resolution)
        game.set_objects_info_enabled(True)
        game.set_labels_buffer_enabled(True)
        game.set_depth_buffer_enabled(True)
        game.set_sectors_info_enabled(True)
        game.set_automap_buffer_enabled(True)
        game.set_automap_mode(vzd.AutomapMode.OBJECTS_WITH_SIZE)
        game.set_automap_rotate(False)
        game.set_episode_start_time(14)
        game.set_window_visible(window_visible)
        if async_player:
            game.set_mode(vzd.Mode.ASYNC_PLAYER)
            if ticrate is not None:
                game.set_ticrate(ticrate)
        else:
            game.set_mode(vzd.Mode.PLAYER)
        game.set_doom_skill(difficulty)
        game.set_render_hud(render_hud)

        if seed is not None:
            game.set_seed(seed)

        if episode_timeout is not None:
            game.set_episode_timeout(episode_timeout)

        # Configure buttons
        game.clear_available_buttons()
        resolved_buttons = []
        for name in button_names:
            btn = BUTTON_NAMES[name.upper()]
            game.add_available_button(btn)
            resolved_buttons.append(btn)

        # Configure game variables
        game.clear_available_game_variables()
        resolved_variable_names = []
        for name in variable_names:
            upper = name.upper()
            var = getattr(vzd.GameVariable, upper)
            game.add_available_game_variable(var)
            resolved_variable_names.append(upper)

        # Set map exit reward so completing a level gives positive feedback
        if wad is not None:
            game.set_map_exit_reward(_MAP_EXIT_REWARD)

        # Redirect stdout to stderr during init to avoid breaking MCP protocol
        with contextlib.redirect_stdout(sys.stderr):
            game.init()

        self._recording_path = recording_path
        if recording_path:
            game.new_episode(recording_path)

        self._game = game
        self._buttons = resolved_buttons
        self._variable_names = resolved_variable_names
        self._scenario_name = scenario if wad is None else f"{wad}:{map_name or 'default'}"
        self._wad = wad
        self._current_map = map_name
        self._async = async_player
        self._nav_memory.reset()

        # Start executor for async mode
        if async_player:
            self._executor = AutonomousExecutor(
                game=game,
                buttons=resolved_buttons,
                variable_names=resolved_variable_names,
                nav_memory=self._nav_memory,
                game_lock=self._game_lock,
            )
            self._executor.start()

        result = {
            "status": "running",
            "buttons": [b.name for b in self._buttons],
            "variables": self._variable_names,
            "screen_resolution": screen_resolution,
        }
        if wad is not None:
            result["wad"] = wad
            result["map"] = map_name or "default"
        else:
            result["scenario"] = scenario
        return result

    def stop(self) -> dict:
        """Stop the current game."""
        if self._executor is not None:
            self._executor.stop()
            self._executor = None
        if self._game is not None:
            self._game.close()
            self._game = None
            self._buttons = []
            self._variable_names = []
            self._scenario_name = ""
            self._wad = None
            self._current_map = None
            self._async = False
            self._recording_path = None
        if self._runtime_wad_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(self._runtime_wad_path)
            self._runtime_wad_path = None
        return {"status": "stopped"}

    def list_wad_maps(self, wad_path: str) -> dict:
        """List supported Doom map markers in a WAD file."""
        return {"wad_path": os.path.abspath(os.path.expanduser(wad_path)), "maps": list_wad_maps(wad_path)}

    def new_episode(self, recording_path: str | None = None) -> dict:
        """Start a new episode. In campaign mode, auto-advances on level completion.

        If the player completed the level (not dead), advances to the next map.
        If the player died, restarts the same map.
        In scenario mode, just restarts the episode.
        """
        game = self._require_running()

        if self._executor is not None:
            self._executor.pause()

        advanced = False
        if self._current_map and self._level_completed(game):
            nxt = next_map(self._current_map)
            if nxt:
                game.set_doom_map(nxt)
                self._current_map = nxt
                advanced = True

        rec = recording_path or self._recording_path
        if rec:
            game.new_episode(rec)
            self._recording_path = rec
        else:
            game.new_episode()

        self._nav_memory.reset()
        if self._executor is not None:
            self._executor.reset()
            self._executor.resume()

        result = {"status": "new_episode"}
        if self._current_map:
            result["map"] = self._current_map
            if advanced:
                result["advanced"] = True
        else:
            result["scenario"] = self._scenario_name
        return result

    def get_state(
        self,
        include_sectors: bool = False,
        include_depth: bool = True,
    ) -> dict:
        """Get complete game state: variables, objects, screenshot, and optionally sectors/depth."""
        game = self._require_running()

        with self._game_lock:
            if game.is_episode_finished():
                return self._finished_state(game)

            return self._extract_full_state(game, include_sectors=include_sectors, include_depth=include_depth)

    def _build_action_list(self, actions: dict[str, float] | None = None) -> list[float]:
        """Convert an action dict to a ViZDoom action list. Skips unknown buttons silently."""
        action_list = [0.0] * len(self._buttons)
        if not actions:
            return action_list
        button_index = {b.name: i for i, b in enumerate(self._buttons)}
        for name, value in actions.items():
            upper = name.upper()
            if upper not in button_index:
                continue
            action_list[button_index[upper]] = float(value)
        return action_list

    def _make_action(self, game: vzd.DoomGame, action: list[float], tics: int = 1) -> float:
        """make_action wrapper for compound action loops.

        In ASYNC_PLAYER mode, make_action applies the PREVIOUS call's action
        to the current tic, not the action we're setting now. This causes a
        1-tic delay that makes feedback loops (like aiming) oscillate.

        Fix: after setting our action, do one extra noop tic to flush it,
        so the game state reflects our action before we read it again.
        """
        if self._async:
            game.make_action(action, 1)        # queue our action, apply prev
            for _ in range(tics - 1):
                if game.is_episode_finished():
                    break
                game.make_action(action, 1)    # keep applying for multi-tic
            if not game.is_episode_finished():
                noop = [0.0] * len(self._buttons)
                game.make_action(noop, 1)      # flush: applies our action
            reward = game.get_last_reward()
            self._record_telemetry_tick(game, max(1, tics))
            return reward
        reward = game.make_action(action, tics)
        self._record_telemetry_tick(game, max(1, tics))
        return reward

    def _record_telemetry_tick(self, game: vzd.DoomGame, tics: int = 1) -> None:
        if self._telemetry_frames is None:
            return
        self._telemetry_tics += max(1, tics)
        if self._telemetry_tics % self._telemetry_stride != 0 and not game.is_episode_finished():
            return
        sample = self._telemetry_sample(game)
        if sample is not None:
            self._telemetry_frames.append(sample)

    def _telemetry_sample(self, game: vzd.DoomGame) -> dict | None:
        state = game.get_state()
        variables = extract_game_variables(game, self._variable_names)
        sample = {
            "tic": getattr(state, "tic", None),
            "game_variables": variables,
            "episode_finished": game.is_episode_finished(),
            "level_completed": False,
            "map_exit": False,
        }
        if state is not None and state.screen_buffer is not None:
            sample["screenshot_png_b64"] = base64.b64encode(
                screen_buffer_to_png(state.screen_buffer)
            ).decode("ascii")
        return sample

    def take_action(
        self,
        actions: dict[str, float] | None = None,
        tics: int = 1,
        include_sectors: bool = False,
        include_depth: bool = True,
        capture_telemetry: bool = False,
        telemetry_stride: int = 1,
    ) -> dict:
        """Execute an action and return the full resulting state.

        Args:
            actions: Dict mapping button name to value.
                Binary buttons: 1 to press (e.g. {"MOVE_FORWARD": 1, "ATTACK": 1}).
                Delta buttons: degree value (e.g. {"TURN_LEFT_RIGHT_DELTA": -15.5}).
                    TURN_LEFT_RIGHT_DELTA: positive=right, negative=left.
                    LOOK_UP_DOWN_DELTA: positive=down, negative=up.
                Omitted buttons default to 0. None or {} is a no-op.
                NOTE: delta values are multiplied by tics. Use tics=1 for precise aim.
            tics: Number of game tics to hold the action (default 1).
        """
        game = self._require_episode()
        self._begin_telemetry(capture_telemetry, telemetry_stride)

        # Validate button names for the public API
        if actions:
            button_index = {b.name: i for i, b in enumerate(self._buttons)}
            for name in actions:
                upper = name.upper()
                if upper not in BUTTON_NAMES:
                    raise ToolError(
                        f"Unknown button {name!r}. "
                        f"Valid: {sorted(BUTTON_NAMES.keys())}"
                    )
                if upper not in button_index:
                    raise ToolError(
                        f"Button {name!r} is not configured. "
                        f"Configured: {sorted(button_index.keys())}"
                    )

        action_list = self._build_action_list(actions)

        with self._with_executor_paused():
            with self._game_lock:
                reward = 0.0
                tics_used = 0
                for _ in range(max(1, int(tics))):
                    if game.is_episode_finished() or self._is_dead(game):
                        break
                    reward += self._make_action(game, action_list, 1)
                    tics_used += 1
                self._clear_action(game)
                summary = {
                    "stop_reason": "player_died" if self._is_dead(game) else "episode_finished" if game.is_episode_finished() else "tics_complete",
                    "tics": tics_used,
                    "actions": actions or {},
                }

                if game.is_episode_finished():
                    result = self._finished_state(game, reward=reward)
                    result["action_summary"] = summary
                    return self._attach_telemetry(result)

                result = self._extract_full_state(game, include_sectors=include_sectors, include_depth=include_depth)
                result["reward"] = reward
                result["action_summary"] = summary
                return self._attach_telemetry(result)

    def get_objects(self) -> dict:
        """Get object and label info from the current state."""
        game = self._require_episode()
        with self._game_lock:
            state = game.get_state()
            px, py, pa = self._get_player_pos(game)
            return {
                "objects": extract_objects(state, player_x=px, player_y=py, player_angle=pa),
            }

    def get_map(self) -> bytes | None:
        """Get the automap buffer as PNG bytes."""
        game = self._require_episode()
        with self._game_lock:
            state = game.get_state()
            if state.automap_buffer is not None:
                return screen_buffer_to_png(state.automap_buffer)
            return None

    def get_available_actions(self) -> dict:
        """Return the configured buttons with usage info."""
        self._require_running()
        buttons = []
        for b in self._buttons:
            is_delta = b.name in DELTA_BUTTONS
            buttons.append({
                "name": b.name,
                "type": "delta" if is_delta else "binary",
                "description": (
                    "Numeric value in degrees (multiplied by tics)"
                    if is_delta else "1 to press, 0 to release"
                ),
            })
        return {
            "buttons": buttons,
            "usage": (
                "Pass a dict mapping button names to values. "
                "Example: take_action(actions={"
                '"TURN_LEFT_RIGHT_DELTA": -15, '
                '"MOVE_FORWARD": 1, '
                '"ATTACK": 1'
                "}, tics=1)"
            ),
            "delta_convention": {
                "TURN_LEFT_RIGHT_DELTA": "positive=right, negative=left (degrees)",
                "LOOK_UP_DOWN_DELTA": "positive=down, negative=up (degrees)",
                "MOVE_FORWARD_BACKWARD_DELTA": "positive=forward, negative=backward (speed units)",
                "MOVE_LEFT_RIGHT_DELTA": "positive=right, negative=left (speed units)",
            },
        }

    # ------------------------------------------------------------------
    # Compound action helpers
    # ------------------------------------------------------------------

    def _find_object_by_id(self, game: vzd.DoomGame, object_id: int) -> dict | None:
        """Find a specific object by numeric ID in the current state."""
        state = game.get_state()
        if state is None:
            return None
        px, py, pa = self._get_player_pos(game)
        for obj in extract_objects(state, player_x=px, player_y=py, player_angle=pa):
            if obj["id"] == object_id:
                return obj
        return None

    def _is_dead(self, game: vzd.DoomGame) -> bool:
        return bool(game.get_game_variable(vzd.GameVariable.DEAD))

    def _clear_action(self, game: vzd.DoomGame) -> None:
        """Set a no-op action so the render thread doesn't repeat the last action."""
        if self._async and not game.is_episode_finished():
            game.set_action(self._build_action_list())

    def _compound_result(
        self, game: vzd.DoomGame, summary: dict, stop_reason: str,
    ) -> dict:
        """Build a compound action result with state + summary."""
        summary["stop_reason"] = stop_reason
        self._clear_action(game)

        if game.is_episode_finished():
            result = self._finished_state(game)
            result["action_summary"] = summary
            return self._attach_telemetry(result)

        result = self._extract_full_state(game, include_depth=True)
        result["action_summary"] = summary
        return self._attach_telemetry(result)

    def _get_position(self, game: vzd.DoomGame) -> tuple[float, float]:
        x = game.get_game_variable(vzd.GameVariable.POSITION_X)
        y = game.get_game_variable(vzd.GameVariable.POSITION_Y)
        return x, y

    def _position_spread(self, history: list[tuple[float, float]]) -> float:
        """Compute bounding-box diagonal of position history (stuck detection)."""
        if len(history) < 2:
            return float("inf")
        xs = [p[0] for p in history]
        ys = [p[1] for p in history]
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys))

    # ------------------------------------------------------------------
    # Compound actions
    # ------------------------------------------------------------------

    def aim_and_shoot(
        self,
        object_id: int,
        shots: int = 3,
        max_tics: int = 100,
        capture_telemetry: bool = False,
        telemetry_stride: int = 4,
    ) -> dict:
        """Aim at an object and fire multiple shots. Runs a tight game loop internally.

        Args:
            object_id: Numeric ID of the target object (from objects list).
            shots: Number of shots to fire (default 3).
            max_tics: Maximum tics before giving up (default 100).

        Returns:
            Game state + action_summary with: shots_fired, hits_landed, kills,
            ammo_spent, target_name, stop_reason.
        """
        game = self._require_episode()
        self._begin_telemetry(capture_telemetry, telemetry_stride)

        summary = {
            "shots_fired": 0,
            "hits_landed": 0,
            "kills": 0,
            "ammo_spent": 0,
            "target_name": None,
        }
        tics_used = 0

        with self._with_executor_paused():
            with self._game_lock:
                initial_killcount = game.get_game_variable(vzd.GameVariable.KILLCOUNT)
                initial_hitcount = game.get_game_variable(vzd.GameVariable.HITCOUNT)
                initial_ammo = game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO)

                # Find initial target to get its name
                target = self._find_object_by_id(game, object_id)
                if target is not None:
                    summary["target_name"] = target["name"]

                while tics_used < max_tics and summary["shots_fired"] < shots:
                    if game.is_episode_finished() or self._is_dead(game):
                        summary["kills"] = int(game.get_game_variable(vzd.GameVariable.KILLCOUNT) - initial_killcount)
                        summary["hits_landed"] = int(game.get_game_variable(vzd.GameVariable.HITCOUNT) - initial_hitcount)
                        summary["ammo_spent"] = int(initial_ammo - game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO))
                        reason = "player_died" if self._is_dead(game) else "episode_finished"
                        return self._compound_result(game, summary, reason)

                    # Find target
                    target = self._find_object_by_id(game, object_id)
                    if target is None:
                        # Target gone - check if we killed it
                        kills = int(game.get_game_variable(vzd.GameVariable.KILLCOUNT) - initial_killcount)
                        summary["kills"] = kills
                        summary["hits_landed"] = int(game.get_game_variable(vzd.GameVariable.HITCOUNT) - initial_hitcount)
                        summary["ammo_spent"] = int(initial_ammo - game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO))
                        reason = "target_killed" if kills > 0 else "target_lost"
                        return self._compound_result(game, summary, reason)
                    if not target.get("is_visible"):
                        summary["kills"] = int(game.get_game_variable(vzd.GameVariable.KILLCOUNT) - initial_killcount)
                        summary["hits_landed"] = int(game.get_game_variable(vzd.GameVariable.HITCOUNT) - initial_hitcount)
                        summary["ammo_spent"] = int(initial_ammo - game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO))
                        return self._compound_result(game, summary, "target_not_visible")

                    angle = target["angle_to_aim"]

                    # Check ammo
                    current_ammo = game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO)
                    if current_ammo <= 0:
                        summary["kills"] = int(game.get_game_variable(vzd.GameVariable.KILLCOUNT) - initial_killcount)
                        summary["hits_landed"] = int(game.get_game_variable(vzd.GameVariable.HITCOUNT) - initial_hitcount)
                        summary["ammo_spent"] = int(initial_ammo - current_ammo)
                        return self._compound_result(game, summary, "out_of_ammo")

                    # Clamp turn to avoid overshooting
                    clamped = max(-45.0, min(45.0, angle))

                    if abs(angle) > _AIM_TOLERANCE:
                        # Turn to face target
                        action = self._build_action_list({"TURN_LEFT_RIGHT_DELTA": clamped})
                        self._make_action(game, action, 1)
                        tics_used += 1
                    elif not game.get_game_variable(vzd.GameVariable.ATTACK_READY):
                        # Wait for weapon to be ready
                        self._make_action(game, self._build_action_list(), 1)
                        tics_used += 1
                    else:
                        # Fire! Include small re-aim
                        action = self._build_action_list({
                            "ATTACK": 1,
                            "TURN_LEFT_RIGHT_DELTA": angle,
                        })
                        self._make_action(game, action, 1)
                        tics_used += 1
                        summary["shots_fired"] += 1

                        # Wait for weapon cooldown (up to 4 tics)
                        for _ in range(4):
                            if game.is_episode_finished():
                                break
                            if game.get_game_variable(vzd.GameVariable.ATTACK_READY):
                                break
                            self._make_action(game, self._build_action_list(), 1)
                            tics_used += 1

                summary["kills"] = int(game.get_game_variable(vzd.GameVariable.KILLCOUNT) - initial_killcount)
                summary["hits_landed"] = int(game.get_game_variable(vzd.GameVariable.HITCOUNT) - initial_hitcount)
                summary["ammo_spent"] = int(initial_ammo - game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO))

                reason = "shots_complete" if summary["shots_fired"] >= shots else "max_tics"
                return self._compound_result(game, summary, reason)

    def move_to(
        self,
        object_id: int,
        max_tics: int = 140,
        use: bool = False,
        stop_on_enemy: bool = True,
        capture_telemetry: bool = False,
        telemetry_stride: int = 4,
    ) -> dict:
        """Move toward an object by ID. Runs a tight game loop internally.

        Args:
            object_id: Numeric ID of the target object.
            max_tics: Maximum tics before giving up (default 140).
            use: Press USE when arriving (for switches/doors). Default false.
            stop_on_enemy: Stop if a monster is spotted nearby. Default true.

        Returns:
            Game state + action_summary with: distance_moved, distance_remaining,
            target_name, used_object, threat_object, stop_reason.
        """
        game = self._require_episode()
        self._begin_telemetry(capture_telemetry, telemetry_stride)

        summary = {
            "distance_moved": 0.0,
            "distance_remaining": None,
            "target_name": None,
            "target_type": None,
            "collected": False,
            "used_object": False,
            "threat_object": None,
        }

        with self._with_executor_paused():
            with self._game_lock:
                start_x, start_y = self._get_position(game)
                position_history: list[tuple[float, float]] = []
                stuck_recoveries = 0
                tics_used = 0

                # Get initial target info
                target = self._find_object_by_id(game, object_id)
                if target is not None:
                    summary["target_name"] = target["name"]
                    summary["target_type"] = target.get("type")

                while tics_used < max_tics:
                    if game.is_episode_finished() or self._is_dead(game):
                        cx, cy = self._get_position(game)
                        summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                        reason = "player_died" if self._is_dead(game) else "episode_finished"
                        return self._compound_result(game, summary, reason)

                    # Track position for stuck detection + nav memory
                    pos = self._get_position(game)
                    position_history.append(pos)
                    if len(position_history) > _STUCK_WINDOW:
                        position_history.pop(0)
                    pa = game.get_game_variable(vzd.GameVariable.ANGLE)
                    self._nav_memory.update(pos[0], pos[1], pa)

                    # Find target
                    target = self._find_object_by_id(game, object_id)
                    if target is None:
                        cx, cy = self._get_position(game)
                        summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                        if summary.get("target_type") in _PICKUP_TYPES:
                            summary["collected"] = True
                            return self._compound_result(game, summary, "arrived")
                        return self._compound_result(game, summary, "target_lost")

                    distance = target["distance"]
                    angle = target["angle_to_aim"]
                    summary["target_type"] = target.get("type") or summary.get("target_type")
                    summary["distance_remaining"] = round(distance, 1)

                    # Arrived?
                    if distance < _ARRIVE_DISTANCE:
                        cx, cy = self._get_position(game)
                        summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                        if summary.get("target_type") in _PICKUP_TYPES:
                            for _ in range(8):
                                if game.is_episode_finished() or self._is_dead(game):
                                    break
                                current = self._find_object_by_id(game, object_id)
                                if current is None:
                                    summary["collected"] = True
                                    return self._compound_result(game, summary, "arrived")
                                angle = max(-20.0, min(20.0, float(current.get("angle_to_aim") or 0.0)))
                                action = self._build_action_list({
                                    "TURN_LEFT_RIGHT_DELTA": angle,
                                    "MOVE_FORWARD_BACKWARD_DELTA": 18,
                                })
                                self._make_action(game, action, 1)
                                tics_used += 1
                            current = self._find_object_by_id(game, object_id)
                            if current is None:
                                summary["collected"] = True
                                return self._compound_result(game, summary, "arrived")
                            summary["distance_remaining"] = round(float(current.get("distance") or distance), 1)
                            return self._compound_result(game, summary, "pickup_not_collected")
                        if use:
                            action = self._build_action_list({"USE": 1})
                            self._make_action(game, action, 1)
                            tics_used += 1
                            summary["used_object"] = True
                        return self._compound_result(game, summary, "arrived")

                    # Enemy scan
                    if stop_on_enemy:
                        state = game.get_state()
                        if state is not None:
                            px, py, pa = self._get_player_pos(game)
                            all_objs = extract_objects(state, player_x=px, player_y=py, player_angle=pa)

                            for obj in all_objs:
                                if obj["id"] == object_id:
                                    continue
                                info = get_object_info(obj["name"])
                                if info["type"] == "monster" and obj["distance"] < _ENEMY_ALERT_DIST and obj["is_visible"]:
                                    cx, cy = self._get_position(game)
                                    summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                                    summary["threat_object"] = {
                                        "id": obj["id"],
                                        "name": obj["name"],
                                        "distance": obj["distance"],
                                        "angle_to_aim": obj["angle_to_aim"],
                                    }
                                    return self._compound_result(game, summary, "enemy_nearby")

                    # Stuck detection
                    if len(position_history) >= _STUCK_WINDOW:
                        spread = self._position_spread(position_history)
                        if spread < _STUCK_THRESHOLD:
                            stuck_recoveries += 1
                            if stuck_recoveries > 3:
                                cx, cy = self._get_position(game)
                                summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                                return self._compound_result(game, summary, "stuck")
                            # Strafe + turn recovery - alternate directions
                            strafe_dir = 20.0 if stuck_recoveries % 2 == 1 else -20.0
                            turn_amount = 25.0 if stuck_recoveries % 2 == 1 else -25.0
                            for _ in range(3):
                                if game.is_episode_finished():
                                    break
                                action = self._build_action_list({
                                    "MOVE_LEFT_RIGHT_DELTA": strafe_dir,
                                    "TURN_LEFT_RIGHT_DELTA": turn_amount,
                                })
                                self._make_action(game, action, 1)
                                tics_used += 1
                            # Push forward after strafe
                            for _ in range(4):
                                if game.is_episode_finished():
                                    break
                                action = self._build_action_list({
                                    "MOVE_FORWARD_BACKWARD_DELTA": 25,
                                })
                                self._make_action(game, action, 1)
                                tics_used += 1
                            position_history.clear()
                            continue

                    # Movement - clamp turn speed to avoid wild spinning
                    clamped_angle = max(-30.0, min(30.0, angle))
                    if abs(angle) > 15:
                        # Large angle - turn only (no forward into walls)
                        action = self._build_action_list({"TURN_LEFT_RIGHT_DELTA": clamped_angle})
                    else:
                        # Small angle - turn + forward
                        action = self._build_action_list({
                            "TURN_LEFT_RIGHT_DELTA": clamped_angle,
                            "MOVE_FORWARD_BACKWARD_DELTA": 25,
                        })
                    self._make_action(game, action, 1)
                    tics_used += 1

                cx, cy = self._get_position(game)
                summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                return self._compound_result(game, summary, "max_tics")

    def explore(
        self,
        max_tics: int = 200,
        stop_on_enemy: bool = True,
        stop_on_item: bool = False,
        capture_telemetry: bool = False,
        telemetry_stride: int = 4,
    ) -> dict:
        """Explore the environment autonomously. Walks forward, avoids walls, scans for enemies/items.

        Args:
            max_tics: Maximum tics to explore (default 200).
            stop_on_enemy: Stop when a visible monster is spotted nearby. Default true.
            stop_on_item: Stop when a new item/ammo is spotted. Default false.

        Returns:
            Game state + action_summary with: distance_moved, direction_changes,
            enemies_seen, items_seen, stop_reason.
        """
        game = self._require_episode()
        self._begin_telemetry(capture_telemetry, telemetry_stride)

        summary = {
            "distance_moved": 0.0,
            "direction_changes": 0,
            "enemies_seen": [],
            "items_seen": [],
        }
        seen_enemy_ids: set[int] = set()
        seen_item_ids: set[int] = set()

        with self._with_executor_paused():
            with self._game_lock:
                start_x, start_y = self._get_position(game)
                position_history: list[tuple[float, float]] = []
                stuck_recoveries = 0
                tics_used = 0
                turn_bias = 0.0

                while tics_used < max_tics:
                    if game.is_episode_finished() or self._is_dead(game):
                        cx, cy = self._get_position(game)
                        summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                        reason = "player_died" if self._is_dead(game) else "episode_finished"
                        return self._compound_result(game, summary, reason)

                    # Track position for stuck detection + nav memory
                    pos = self._get_position(game)
                    position_history.append(pos)
                    if len(position_history) > _STUCK_WINDOW:
                        position_history.pop(0)
                    pa = game.get_game_variable(vzd.GameVariable.ANGLE)
                    self._nav_memory.update(pos[0], pos[1], pa)

                    state = game.get_state()
                    if state is None:
                        cx, cy = self._get_position(game)
                        summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                        return self._compound_result(game, summary, "episode_finished")

                    # Object scanning
                    px, py, pa = self._get_player_pos(game)
                    all_objs = extract_objects(state, player_x=px, player_y=py, player_angle=pa)
                    from .objects import get_object_info

                    for obj in all_objs:
                        info = get_object_info(obj["name"])
                        if info["type"] == "monster" and obj["is_visible"] and obj["distance"] < _ENEMY_ALERT_DIST:
                            if obj["id"] not in seen_enemy_ids:
                                seen_enemy_ids.add(obj["id"])
                                enemy_info = {
                                    "id": obj["id"],
                                    "name": obj["name"],
                                    "distance": obj["distance"],
                                    "angle_to_aim": obj["angle_to_aim"],
                                }
                                summary["enemies_seen"].append(enemy_info)
                                if stop_on_enemy:
                                    cx, cy = self._get_position(game)
                                    summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                                    return self._compound_result(game, summary, "enemy_spotted")

                        if info["type"] in _ITEM_TYPES and obj["is_visible"]:
                            if obj["id"] not in seen_item_ids:
                                seen_item_ids.add(obj["id"])
                                item_info = {
                                    "id": obj["id"],
                                    "name": obj["name"],
                                    "distance": obj["distance"],
                                }
                                summary["items_seen"].append(item_info)
                                if stop_on_item:
                                    cx, cy = self._get_position(game)
                                    summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                                    return self._compound_result(game, summary, "item_found")

                    # Stuck detection
                    if len(position_history) >= _STUCK_WINDOW:
                        spread = self._position_spread(position_history)
                        if spread < _STUCK_THRESHOLD:
                            stuck_recoveries += 1
                            if stuck_recoveries > 3:
                                cx, cy = self._get_position(game)
                                summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                                return self._compound_result(game, summary, "stuck")
                            # Recovery: turn ~90 degrees then push forward
                            turn_dir = 30.0 if stuck_recoveries % 2 == 1 else -30.0
                            for _ in range(3):
                                if game.is_episode_finished():
                                    break
                                action = self._build_action_list({"TURN_LEFT_RIGHT_DELTA": turn_dir})
                                self._make_action(game, action, 1)
                                tics_used += 1
                            # Push forward after turning
                            for _ in range(5):
                                if game.is_episode_finished():
                                    break
                                action = self._build_action_list({"MOVE_FORWARD_BACKWARD_DELTA": 25})
                                self._make_action(game, action, 1)
                                tics_used += 1
                            summary["direction_changes"] += 1
                            turn_bias = 0.0
                            position_history.clear()
                            continue

                    # Depth-based navigation with hysteresis to prevent oscillation
                    depth = state.depth_buffer
                    actions: dict[str, float] = {}

                    if depth is not None:
                        h, w = depth.shape
                        band_h = max(h // 6, 1)
                        mid = h // 2
                        band = depth[mid - band_h:mid + band_h, :]
                        third = w // 3
                        left_score = float(band[:, :third].mean())
                        center_score = float(band[:, third:2*third].mean())
                        right_score = float(band[:, 2*third:].mean())

                        if center_score < _WALL_CLOSE:
                            if abs(left_score - right_score) > 3:
                                turn_bias = -25.0 if left_score > right_score else 25.0
                            elif turn_bias == 0.0:
                                turn_bias = -25.0 if left_score >= right_score else 25.0
                            actions["TURN_LEFT_RIGHT_DELTA"] = turn_bias
                            summary["direction_changes"] += 1
                        elif center_score < _WALL_NEAR:
                            if abs(left_score - right_score) > 3:
                                turn_bias = -10.0 if left_score > right_score else 10.0
                            elif turn_bias == 0.0:
                                turn_bias = -10.0 if left_score >= right_score else 10.0
                            actions["TURN_LEFT_RIGHT_DELTA"] = turn_bias
                            actions["MOVE_FORWARD_BACKWARD_DELTA"] = 15
                        else:
                            turn_bias *= 0.5
                            if abs(turn_bias) < 1.0:
                                turn_bias = 0.0
                            actions["TURN_LEFT_RIGHT_DELTA"] = turn_bias
                            actions["MOVE_FORWARD_BACKWARD_DELTA"] = 25
                    else:
                        actions["MOVE_FORWARD_BACKWARD_DELTA"] = 25

                    action_list = self._build_action_list(actions)
                    self._make_action(game, action_list, 1)
                    tics_used += 1

                cx, cy = self._get_position(game)
                summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                return self._compound_result(game, summary, "max_tics")

    def retreat(
        self,
        tics: int = 35,
        backpedal: bool = False,
        capture_telemetry: bool = False,
        telemetry_stride: int = 4,
    ) -> dict:
        """Turn and run or backpedal away from current facing direction.

        Args:
            tics: Total game tics for the retreat (default 35).
            backpedal: If True, move backward while keeping current facing.
                If False (default), turn 180 degrees then sprint forward.

        Returns:
            Game state + action_summary with: distance_moved, mode, stop_reason.
        """
        game = self._require_episode()
        self._begin_telemetry(capture_telemetry, telemetry_stride)

        mode = "backpedal" if backpedal else "turn_and_run"
        summary = {"distance_moved": 0.0, "mode": mode}

        with self._with_executor_paused():
            with self._game_lock:
                start_x, start_y = self._get_position(game)
                tics_used = 0

                if backpedal:
                    while tics_used < tics:
                        if game.is_episode_finished() or self._is_dead(game):
                            cx, cy = self._get_position(game)
                            summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                            reason = "player_died" if self._is_dead(game) else "episode_finished"
                            return self._compound_result(game, summary, reason)
                        action = self._build_action_list({
                            "MOVE_FORWARD_BACKWARD_DELTA": -25,
                            "SPEED": 1,
                        })
                        self._make_action(game, action, 1)
                        tics_used += 1
                        pos = self._get_position(game)
                        pa = game.get_game_variable(vzd.GameVariable.ANGLE)
                        self._nav_memory.update(pos[0], pos[1], pa)
                else:
                    # Turn 180 degrees (~6 tics at 30 deg/tic)
                    for _ in range(6):
                        if tics_used >= tics or game.is_episode_finished():
                            break
                        action = self._build_action_list({"TURN_LEFT_RIGHT_DELTA": 30})
                        self._make_action(game, action, 1)
                        tics_used += 1

                    # Sprint forward
                    while tics_used < tics:
                        if game.is_episode_finished() or self._is_dead(game):
                            cx, cy = self._get_position(game)
                            summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                            reason = "player_died" if self._is_dead(game) else "episode_finished"
                            return self._compound_result(game, summary, reason)
                        action = self._build_action_list({
                            "MOVE_FORWARD_BACKWARD_DELTA": 25,
                            "SPEED": 1,
                        })
                        self._make_action(game, action, 1)
                        tics_used += 1
                        pos = self._get_position(game)
                        pa = game.get_game_variable(vzd.GameVariable.ANGLE)
                        self._nav_memory.update(pos[0], pos[1], pa)

                cx, cy = self._get_position(game)
                summary["distance_moved"] = round(math.hypot(cx - start_x, cy - start_y), 1)
                return self._compound_result(game, summary, "complete")

    def strafe_and_shoot(
        self,
        object_id: int,
        direction: str = "auto",
        shots: int = 5,
        max_tics: int = 100,
        capture_telemetry: bool = False,
        telemetry_stride: int = 4,
    ) -> dict:
        """Strafe laterally while firing at a target. Useful against hitscan enemies.

        Args:
            object_id: Numeric ID of the target (from objects list).
            direction: Strafe direction - "left", "right", or "auto" (alternates).
            shots: Number of shots to fire (default 5).
            max_tics: Maximum tics before giving up (default 100).

        Returns:
            Game state + action_summary with: shots_fired, hits_landed, kills,
            ammo_spent, target_name, strafe_direction, damage_taken, stop_reason.
        """
        game = self._require_episode()
        self._begin_telemetry(capture_telemetry, telemetry_stride)

        summary = {
            "shots_fired": 0,
            "hits_landed": 0,
            "kills": 0,
            "ammo_spent": 0,
            "target_name": None,
            "strafe_direction": direction,
            "damage_taken": 0,
        }
        tics_used = 0
        strafe_sign = -1.0  # start left

        with self._with_executor_paused():
            with self._game_lock:
                initial_killcount = game.get_game_variable(vzd.GameVariable.KILLCOUNT)
                initial_hitcount = game.get_game_variable(vzd.GameVariable.HITCOUNT)
                initial_ammo = game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO)
                initial_damage_taken = game.get_game_variable(vzd.GameVariable.DAMAGE_TAKEN)

                target = self._find_object_by_id(game, object_id)
                if target is not None:
                    summary["target_name"] = target["name"]

                while tics_used < max_tics and summary["shots_fired"] < shots:
                    if game.is_episode_finished() or self._is_dead(game):
                        self._update_combat_summary(game, summary, initial_killcount, initial_hitcount, initial_ammo)
                        summary["damage_taken"] = int(game.get_game_variable(vzd.GameVariable.DAMAGE_TAKEN) - initial_damage_taken)
                        reason = "player_died" if self._is_dead(game) else "episode_finished"
                        return self._compound_result(game, summary, reason)

                    target = self._find_object_by_id(game, object_id)
                    if target is None:
                        self._update_combat_summary(game, summary, initial_killcount, initial_hitcount, initial_ammo)
                        summary["damage_taken"] = int(game.get_game_variable(vzd.GameVariable.DAMAGE_TAKEN) - initial_damage_taken)
                        kills = summary["kills"]
                        reason = "target_killed" if kills > 0 else "target_lost"
                        return self._compound_result(game, summary, reason)
                    if not target.get("is_visible"):
                        self._update_combat_summary(game, summary, initial_killcount, initial_hitcount, initial_ammo)
                        summary["damage_taken"] = int(game.get_game_variable(vzd.GameVariable.DAMAGE_TAKEN) - initial_damage_taken)
                        return self._compound_result(game, summary, "target_not_visible")

                    angle = target["angle_to_aim"]

                    current_ammo = game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO)
                    if current_ammo <= 0:
                        self._update_combat_summary(game, summary, initial_killcount, initial_hitcount, initial_ammo)
                        summary["damage_taken"] = int(game.get_game_variable(vzd.GameVariable.DAMAGE_TAKEN) - initial_damage_taken)
                        return self._compound_result(game, summary, "out_of_ammo")

                    # Auto-alternate strafe direction every ~15 tics
                    if direction == "auto" and tics_used % 15 == 0 and tics_used > 0:
                        strafe_sign *= -1
                    elif direction == "right":
                        strafe_sign = 1.0
                    elif direction == "left":
                        strafe_sign = -1.0

                    strafe_delta = strafe_sign * 20.0

                    if abs(angle) <= _AIM_TOLERANCE and game.get_game_variable(vzd.GameVariable.ATTACK_READY):
                        # On target + ready - fire + strafe
                        action = self._build_action_list({
                            "TURN_LEFT_RIGHT_DELTA": angle,
                            "MOVE_LEFT_RIGHT_DELTA": strafe_delta,
                            "ATTACK": 1,
                        })
                        self._make_action(game, action, 1)
                        tics_used += 1
                        summary["shots_fired"] += 1
                    elif game.get_game_variable(vzd.GameVariable.ATTACK_READY):
                        # Large angle but weapon ready - aim + strafe + fire
                        action = self._build_action_list({
                            "TURN_LEFT_RIGHT_DELTA": angle,
                            "MOVE_LEFT_RIGHT_DELTA": strafe_delta,
                            "ATTACK": 1,
                        })
                        self._make_action(game, action, 1)
                        tics_used += 1
                        summary["shots_fired"] += 1
                    else:
                        # Weapon cooldown - strafe + aim only
                        action = self._build_action_list({
                            "TURN_LEFT_RIGHT_DELTA": angle,
                            "MOVE_LEFT_RIGHT_DELTA": strafe_delta,
                        })
                        self._make_action(game, action, 1)
                        tics_used += 1

                self._update_combat_summary(game, summary, initial_killcount, initial_hitcount, initial_ammo)
                summary["damage_taken"] = int(game.get_game_variable(vzd.GameVariable.DAMAGE_TAKEN) - initial_damage_taken)
                reason = "shots_complete" if summary["shots_fired"] >= shots else "max_tics"
                return self._compound_result(game, summary, reason)

    def _update_combat_summary(
        self, game: vzd.DoomGame, summary: dict,
        initial_killcount: float, initial_hitcount: float, initial_ammo: float,
    ) -> None:
        """Update kills/hits/ammo in a combat summary dict."""
        summary["kills"] = int(game.get_game_variable(vzd.GameVariable.KILLCOUNT) - initial_killcount)
        summary["hits_landed"] = int(game.get_game_variable(vzd.GameVariable.HITCOUNT) - initial_hitcount)
        summary["ammo_spent"] = int(initial_ammo - game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO))

    # ------------------------------------------------------------------
    # Threat assessment (no tics consumed)
    # ------------------------------------------------------------------

    _THREAT_WEIGHTS = {"none": 0, "low": 1, "medium": 2, "high": 3}
    _ATTACK_URGENCY = {"hitscan": 3, "projectile": 2, "melee": 1, "none": 0}

    def get_threat_assessment(self) -> dict:
        """Analyze all visible threats and return prioritized tactical info.

        No game tics are consumed. Uses current game state only.

        Returns:
            threat_level, threats (sorted by priority), incoming_projectiles,
            tactical_advice, player_health, player_armor, selected_weapon_ammo.
        """
        game = self._require_episode()

        with self._game_lock:
            state = game.get_state()
            if state is None:
                return {"threat_level": "none", "threats": [], "incoming_projectiles": [],
                        "tactical_advice": [], "player_health": 0, "player_armor": 0,
                        "selected_weapon_ammo": 0}

            px, py, pa = self._get_player_pos(game)
            all_objects = extract_objects(state, player_x=px, player_y=py, player_angle=pa)
            health = game.get_game_variable(vzd.GameVariable.HEALTH)
            armor = game.get_game_variable(vzd.GameVariable.ARMOR)
            ammo = game.get_game_variable(vzd.GameVariable.SELECTED_WEAPON_AMMO)

        threats = []
        projectiles = []
        advice = []

        for obj in all_objects:
            info = get_object_info(obj["name"])

            if info["type"] == "projectile" and obj["is_visible"]:
                projectiles.append({
                    "name": obj["name"],
                    "distance": round(obj["distance"], 1),
                    "angle_to_aim": round(obj["angle_to_aim"], 1),
                })
                continue

            if info["type"] != "monster":
                continue
            if obj["distance"] > _MONSTER_RANGE:
                continue

            dist = max(obj["distance"], 1.0)
            threat_w = self._THREAT_WEIGHTS.get(info["threat"], 0)
            attack_u = self._ATTACK_URGENCY.get(info["attack"], 0)
            proximity = 1000.0 / dist
            visibility_bonus = 5.0 if obj["is_visible"] else 0.0

            score = threat_w * 10 + attack_u * 5 + proximity + visibility_bonus

            # Archvile always top priority
            if obj["name"] == "Archvile":
                score += 100

            threats.append({
                "id": obj["id"],
                "name": obj["name"],
                "distance": round(dist, 1),
                "angle_to_aim": round(obj["angle_to_aim"], 1),
                "attack_type": info["attack"],
                "threat": info["threat"],
                "is_visible": obj["is_visible"],
                "priority_score": round(score, 1),
            })

        # Sort by priority score descending
        threats.sort(key=lambda t: t["priority_score"], reverse=True)

        # Assign ranks
        for i, t in enumerate(threats):
            t["priority_rank"] = i + 1

        # Overall threat level
        if not threats:
            level = "none"
        else:
            top_score = threats[0]["priority_score"]
            if top_score >= 50:
                level = "critical"
            elif top_score >= 30:
                level = "high"
            elif top_score >= 15:
                level = "medium"
            else:
                level = "low"

        # Tactical advice
        if threats:
            top = threats[0]
            if top["attack_type"] == "hitscan":
                advice.append(f"PRIORITY: Kill {top['name']} - hitscan (can't dodge)")
            elif top["name"] == "Archvile":
                advice.append(f"PRIORITY: Kill {top['name']} - resurrects dead enemies")
            else:
                advice.append(f"PRIORITY: {top['name']} at {top['distance']} units")

        if health <= 25:
            advice.append("CRITICAL: Low health - retreat or find medikit")
        elif health <= 50:
            advice.append("Low health - consider retreating")

        if ammo <= 0:
            advice.append("NO AMMO - switch weapon or retreat")

        if projectiles:
            advice.append(f"DODGE: {len(projectiles)} incoming projectile(s)")

        hitscan_count = sum(1 for t in threats if t["attack_type"] == "hitscan" and t["is_visible"])
        if hitscan_count > 1:
            advice.append(f"WARNING: {hitscan_count} hitscan enemies - use strafe_and_shoot")

        return {
            "threat_level": level,
            "threats": threats,
            "incoming_projectiles": projectiles,
            "tactical_advice": advice,
            "player_health": health,
            "player_armor": armor,
            "selected_weapon_ammo": ammo,
        }

    # ------------------------------------------------------------------
    # Navigation info (no tics consumed)
    # ------------------------------------------------------------------

    def get_navigation_info(self) -> dict:
        """Get spatial navigation intelligence from the navigation memory.

        No game tics are consumed. Returns exploration progress, directions,
        key locations, and nearby doors.
        """
        game = self._require_episode()

        with self._game_lock:
            state = game.get_state()
            if state is None:
                return {"cells_explored": 0}

            px, py, pa = self._get_player_pos(game)
            all_objects = extract_objects(state, player_x=px, player_y=py, player_angle=pa)
            sectors = extract_sectors(state)

            self._nav_memory.update(px, py, pa, objects=all_objects, sectors=sectors)
            return self._nav_memory.get_exploration_summary(px, py, pa)

    # ------------------------------------------------------------------
    # Director API (for autonomous executor)
    # ------------------------------------------------------------------

    def get_situation_report(self) -> dict:
        """Get a compact situation report for the LLM director.

        Returns screenshot + executor state, recent events, game variables,
        nearby threats/items, and exploration progress.
        """
        game = self._require_running()

        with self._game_lock:
            if game.is_episode_finished():
                result = self._finished_state(game)
                if self._executor is not None:
                    result["executor_state"] = self._executor.state.value
                    result["events"] = self._executor.get_recent_events()
                    result["objectives"] = self._executor.get_objectives()
                    result["strategy"] = self._executor.get_strategy()
                    result["executor_progress"] = self._executor.get_progress()
                return result

            state = game.get_state()
            if state is None:
                return {"episode_finished": True}

            variables = extract_game_variables(game, self._variable_names)
            px, py, pa = self._get_player_pos(game)
            all_objects = extract_objects(state, player_x=px, player_y=py, player_angle=pa)
            objects = _filter_objects(all_objects)
            screenshot_png = screen_buffer_to_png(state.screen_buffer)
            nav_summary = self._nav_memory.get_exploration_summary(px, py, pa)

        result = {
            "episode_finished": False,
            "tic": state.tic,
            "game_variables": variables,
            "objects": objects,
            "exploration": nav_summary,
            "screenshot_png": screenshot_png,
        }

        if self._executor is not None:
            result["executor_state"] = self._executor.state.value
            result["objectives"] = self._executor.get_objectives()
            result["strategy"] = self._executor.get_strategy()
            result["events"] = self._executor.get_recent_events()
            result["executor_progress"] = self._executor.get_progress()

        return result

    def set_objective(
        self,
        objective_type: str,
        params: dict | None = None,
        priority: int = 0,
        timeout_tics: int = 0,
        replace: bool = False,
    ) -> dict:
        """Push an objective to the executor's queue.

        Args:
            objective_type: One of: explore, kill, move_to_pos, move_to_obj,
                collect, use_object, retreat, hold_position.
            params: Parameters for the objective (e.g. {"x": 100, "y": 200}
                for move_to_pos, {"object_id": 5} for move_to_obj).
            priority: Higher priority objectives are executed first.
            timeout_tics: Auto-fail after this many tics (0 = no timeout).
            replace: Clear the current queue before adding this objective.
        """
        if self._executor is None:
            raise ToolError(
                "Executor not running. Start game with async_player=True."
            )

        try:
            obj_type = ObjectiveType(objective_type)
        except ValueError:
            valid = [t.value for t in ObjectiveType]
            raise ToolError(f"Unknown objective type {objective_type!r}. Valid: {valid}")

        objective = Objective(
            type=obj_type,
            params=params or {},
            priority=priority,
            timeout_tics=timeout_tics,
        )
        self._executor.push_objective(objective, replace=replace)

        return {
            "status": "objective_set",
            "objective": {
                "type": obj_type.value,
                "params": objective.params,
                "priority": priority,
                "timeout_tics": timeout_tics,
            },
            "replace": replace,
            "queue": self._executor.get_objectives(),
        }

    def set_strategy(self, **kwargs) -> dict:
        """Update the executor's strategy parameters.

        Valid parameters:
            aggression: 0.0-1.0 (0=passive, 1=aggressive)
            health_retreat_threshold: HP to trigger retreat
            health_collect_threshold: HP to seek health items
            ammo_switch_threshold: ammo count to trigger weapon switch
            engage_range: max distance to engage enemies
            collect_range: max distance to collect items
            prefer_cover: try to use cover in combat
        """
        if self._executor is None:
            raise ToolError(
                "Executor not running. Start game with async_player=True."
            )

        self._executor.set_strategy(**kwargs)
        return {
            "status": "strategy_updated",
            "strategy": self._executor.get_strategy(),
        }

    def get_map_knowledge(self) -> dict:
        """Get the executor's accumulated map knowledge.

        Returns exploration data for strategic planning.
        """
        game = self._require_running()

        with self._game_lock:
            if game.is_episode_finished():
                return {"cells_explored": 0, "episode_finished": True}

            px, py, pa = self._get_player_pos(game)
            nav_summary = self._nav_memory.get_exploration_summary(px, py, pa)

        result = {
            "position": {"x": round(px, 1), "y": round(py, 1), "angle": round(pa, 1)},
            **nav_summary,
        }

        if self._executor is not None:
            result["executor_state"] = self._executor.state.value
            result["objectives"] = self._executor.get_objectives()

        return result
