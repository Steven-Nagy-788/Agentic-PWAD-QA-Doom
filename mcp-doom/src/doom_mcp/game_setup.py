"""WAD setup and validation helpers for :mod:`doom_mcp.game_manager`."""

from __future__ import annotations

import os
import re
import struct
import subprocess
import sys

from fastmcp.exceptions import ToolError


_DOOM2_MAPS = [f"MAP{i:02d}" for i in range(1, 33)]
_DOOM1_MAPS = [f"E{e}M{m}" for e in range(1, 5) for m in range(1, 10)]
_MAP_MARKER_RE = re.compile(r"^(?:MAP\d{2}|E\dM\d)$", re.IGNORECASE)
_PREFLIGHT_TIMEOUT_SECONDS = 15.0


def next_map(current: str) -> str | None:
    """Return the next map in progression, or None if at the end."""
    for map_list in (_DOOM2_MAPS, _DOOM1_MAPS):
        if current.upper() in map_list:
            idx = map_list.index(current.upper())
            if idx + 1 < len(map_list):
                return map_list[idx + 1]
            return None
    return None


def wad_map_start_info(wad_path: str, map_name: str) -> dict:
    """Return start thing positions for a Doom-format WAD map."""
    target = map_name.upper()
    with open(wad_path, "rb") as wad_file:
        header = wad_file.read(12)
        if len(header) != 12:
            raise ToolError(f"Invalid WAD header in {wad_path!r}")
        magic, lump_count, directory_offset = struct.unpack("<4sii", header)
        if magic not in {b"IWAD", b"PWAD"} or lump_count < 0 or directory_offset < 0:
            raise ToolError(f"Invalid WAD header in {wad_path!r}")

        wad_file.seek(directory_offset)
        directory = []
        for _ in range(lump_count):
            entry = wad_file.read(16)
            if len(entry) != 16:
                raise ToolError(f"Invalid WAD directory in {wad_path!r}")
            offset, size, raw_name = struct.unpack("<ii8s", entry)
            name = raw_name.rstrip(b"\0").decode("ascii", errors="ignore").upper()
            directory.append((name, offset, size))

        for index, (name, _, _) in enumerate(directory):
            if name != target:
                continue
            if index + 1 >= len(directory) or directory[index + 1][0] != "THINGS":
                return {"player_starts": [], "player_one": [], "deathmatch": []}
            _, things_offset, things_size = directory[index + 1]
            if things_size < 10 or things_size % 10 != 0:
                return {"player_starts": [], "player_one": [], "deathmatch": []}
            wad_file.seek(things_offset)
            things = wad_file.read(things_size)
            player_starts = []
            player_one = []
            deathmatch = []
            for pos in range(0, len(things), 10):
                _, _, _, thing_type, _ = struct.unpack_from("<hhhhh", things, pos)
                if thing_type in {1, 2, 3, 4}:
                    player_starts.append(things_offset + pos)
                if thing_type == 1:
                    player_one.append(things_offset + pos)
                elif thing_type == 11:
                    deathmatch.append(things_offset + pos)
            return {
                "player_starts": player_starts,
                "player_one": player_one,
                "deathmatch": deathmatch,
            }

    raise ToolError(f"Map {target} not found in WAD {wad_path!r}")


def list_wad_maps(wad_path: str) -> list[str]:
    path = os.path.abspath(os.path.expanduser(wad_path))
    if not os.path.exists(path):
        raise ToolError(f"WAD not found: {wad_path!r}")
    maps: list[str] = []
    with open(path, "rb") as wad_file:
        header = wad_file.read(12)
        if len(header) != 12:
            raise ToolError(f"Invalid WAD header in {wad_path!r}")
        magic, lump_count, directory_offset = struct.unpack("<4sii", header)
        if magic not in {b"IWAD", b"PWAD"} or lump_count < 0 or directory_offset < 0:
            raise ToolError(f"Invalid WAD header in {wad_path!r}")

        wad_file.seek(directory_offset)
        directory = []
        for _ in range(lump_count):
            entry = wad_file.read(16)
            if len(entry) != 16:
                raise ToolError(f"Invalid WAD directory in {wad_path!r}")
            _, _, raw_name = struct.unpack("<ii8s", entry)
            directory.append(
                raw_name.rstrip(b"\0").decode("ascii", errors="ignore").upper()
            )

    for index, name in enumerate(directory[:-1]):
        if _MAP_MARKER_RE.match(name) and directory[index + 1] == "THINGS":
            maps.append(name)
    return sorted(dict.fromkeys(maps))


def wad_map_player_one_start_count(wad_path: str, map_name: str) -> int:
    """Return the number of Player 1 start things in a Doom-format WAD map."""
    return len(wad_map_start_info(wad_path, map_name)["player_one"])


def assert_wad_loadable(
    base_wad_path: str,
    scenario_wad_path: str,
    map_name: str | None,
    screen_resolution: str,
) -> None:
    """Run ViZDoom init in a child process so bad maps cannot kill the server."""
    if not map_name:
        return
    script = """
import contextlib
import sys
import vizdoom as vzd

base_wad, scenario_wad, map_name, screen_resolution = sys.argv[1:5]
game = vzd.DoomGame()
game.set_doom_game_path(base_wad)
game.add_game_args(f"-file {scenario_wad}")
game.set_doom_map(map_name)
game.set_screen_format(vzd.ScreenFormat.RGB24)
game.set_screen_resolution(getattr(vzd.ScreenResolution, screen_resolution))
game.set_objects_info_enabled(True)
game.set_labels_buffer_enabled(True)
game.set_depth_buffer_enabled(True)
game.set_sectors_info_enabled(True)
game.set_automap_buffer_enabled(True)
game.set_automap_mode(vzd.AutomapMode.OBJECTS_WITH_SIZE)
game.set_automap_rotate(False)
game.set_episode_start_time(14)
game.set_window_visible(False)
game.set_mode(vzd.Mode.PLAYER)
game.set_doom_skill(3)
game.set_render_hud(False)
with contextlib.redirect_stdout(sys.stderr):
    game.init()
game.close()
"""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                base_wad_path,
                scenario_wad_path,
                map_name,
                screen_resolution,
            ],
            capture_output=True,
            text=True,
            timeout=_PREFLIGHT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_tail = ""
        if exc.stderr:
            stderr_tail = (exc.stderr.strip() or "")[-300:]
        if exc.stdout:
            stderr_tail = (stderr_tail + " " + exc.stdout.strip()[-200:]).strip()
        if any(
            kw in (stderr_tail or "").lower()
            for kw in (
                "wad",
                "map",
                "lump",
                "texture",
                "patch",
                "not found",
                "error",
                "traceback",
            )
        ):
            raise ToolError(
                f"PWAD_CRASH: Map {map_name.upper()} could not be loaded by ViZDoom "
                f"(preflight timed out after {exc.timeout:g}s). Stderr: {stderr_tail[:200]}"
            ) from exc
        raise ToolError(
            f"INFRA_TIMEOUT: Map {map_name.upper()} could not be loaded safely by ViZDoom "
            f"(preflight timed out after {exc.timeout:g}s). "
            f"No WAD-specific error detected. Stderr: {stderr_tail[:200]}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if len(detail) > 500:
            detail = detail[-500:]
        raise ToolError(
            f"Map {map_name.upper()} could not be loaded safely by ViZDoom "
            f"(preflight exit code {result.returncode}). {detail}"
        )
