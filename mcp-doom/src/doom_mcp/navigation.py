"""Spatial navigation memory for tracking explored areas, keys, and doors."""

import math


_CELL_SIZE = 128        # map units per grid cell
_BREADCRUMB_SPACING = 64.0  # min distance between breadcrumbs
_BREADCRUMB_MAX = 500       # max breadcrumbs per episode
_KEY_PICKUP_RANGE = 64.0    # max distance to credit a key pickup
_DOOR_HEIGHT_THRESHOLD = 8  # ceiling - floor < this = possible door
_DOOR_MAX_SECTOR_SIZE = 256  # sector bounding box diagonal < this = small sector
_DOOR_DEDUP_RANGE = 128.0   # doors within this range are merged


def _cell(x: float, y: float) -> tuple[int, int]:
    return (math.floor(x / _CELL_SIZE), math.floor(y / _CELL_SIZE))


class NavigationMemory:
    """Tracks spatial exploration state across tics within an episode."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._visited: set[tuple[int, int]] = set()
        self._breadcrumbs: list[tuple[float, float, float]] = []  # (x, y, angle)
        self._keys_found: list[dict] = []  # {"name", "x", "y"}
        self._key_objects: dict[int, dict] = {}  # id -> {"name", "x", "y"}
        self._doors: list[dict] = []  # {"x", "y", "state"}
        self._visited_sector_ids: set[int] = set()
        self._current_sector_id: int | None = None
        self._last_x: float | None = None
        self._last_y: float | None = None

    def update(
        self,
        px: float,
        py: float,
        pa: float,
        objects: list[dict] | None = None,
        sectors: list[dict] | None = None,
    ) -> None:
        """Update navigation memory with current state.

        Position-only update (objects=None, sectors=None) is lightweight
        for use inside compound action loops. Full update with objects
        does key tracking; with sectors does door detection.
        """
        # Cell tracking
        self._visited.add(_cell(px, py))

        # Breadcrumb trail
        if not self._breadcrumbs:
            self._breadcrumbs.append((px, py, pa))
        else:
            lx, ly, _ = self._breadcrumbs[-1]
            if math.hypot(px - lx, py - ly) >= _BREADCRUMB_SPACING:
                self._breadcrumbs.append((px, py, pa))
                if len(self._breadcrumbs) > _BREADCRUMB_MAX:
                    self._breadcrumbs = self._breadcrumbs[-_BREADCRUMB_MAX:]

        self._last_x = px
        self._last_y = py

        # Key tracking
        if objects is not None:
            self._update_keys(px, py, objects)

        # Door detection
        if sectors is not None:
            self._current_sector_id = _sector_at_position(px, py, sectors)
            if self._current_sector_id is not None:
                self._visited_sector_ids.add(self._current_sector_id)
            self._update_doors(sectors)

    def _update_keys(self, px: float, py: float, objects: list[dict]) -> None:
        """Track key objects and detect pickups."""
        current_key_ids: set[int] = set()
        for obj in objects:
            obj_type = obj.get("type", "")
            if obj_type == "key":
                oid = obj["id"]
                current_key_ids.add(oid)
                if oid not in self._key_objects:
                    self._key_objects[oid] = {
                        "name": obj["name"],
                        "x": obj.get("position_x", 0),
                        "y": obj.get("position_y", 0),
                    }

        # Detect pickups: key disappeared and player was close
        vanished = set(self._key_objects.keys()) - current_key_ids
        for oid in vanished:
            info = self._key_objects.pop(oid)
            kx, ky = info["x"], info["y"]
            if math.hypot(px - kx, py - ky) <= _KEY_PICKUP_RANGE:
                # Check not already recorded
                if not any(k["name"] == info["name"] for k in self._keys_found):
                    self._keys_found.append(info)

    def _update_doors(self, sectors: list[dict]) -> None:
        """Detect doors from sector geometry."""
        for sector in sectors:
            floor_h = sector.get("floor_height", 0)
            ceil_h = sector.get("ceiling_height", 0)
            gap = abs(ceil_h - floor_h)
            if gap >= _DOOR_HEIGHT_THRESHOLD:
                continue

            lines = sector.get("lines", [])
            if not lines:
                continue

            # Compute sector bounding box
            xs = []
            ys = []
            for line in lines:
                xs.extend([line["x1"], line["x2"]])
                ys.extend([line["y1"], line["y2"]])
            if not xs:
                continue
            diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
            if diag >= _DOOR_MAX_SECTOR_SIZE:
                continue

            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            state = "closed" if gap < 4 else "partially_open"

            # Deduplicate by proximity
            duplicate = False
            for door in self._doors:
                if math.hypot(cx - door["x"], cy - door["y"]) < _DOOR_DEDUP_RANGE:
                    door["state"] = state  # update state
                    duplicate = True
                    break
            if not duplicate:
                self._doors.append({"x": round(cx, 1), "y": round(cy, 1), "state": state})

    def get_exploration_summary(self, px: float, py: float, pa: float) -> dict:
        """Return navigation intelligence for the current position."""
        current_cell = _cell(px, py)
        cx, cy = current_cell

        # Check cardinal directions for unexplored cells
        directions = {
            "north": (cx, cy + 1),
            "south": (cx, cy - 1),
            "east": (cx + 1, cy),
            "west": (cx - 1, cy),
        }
        explored_dirs = []
        unexplored_dirs = []
        for name, cell in directions.items():
            if cell in self._visited:
                explored_dirs.append(name)
            else:
                unexplored_dirs.append(name)

        # Suggest direction: prefer unexplored, aligned with player facing
        suggested = None
        if unexplored_dirs:
            # Map directions to angles (Doom: 0=east, 90=north, 180=west, 270=south)
            dir_angles = {
                "east": 0.0,
                "north": 90.0,
                "south": 270.0,
                "west": 180.0,
            }
            best_dir = None
            best_diff = 360.0
            for d in unexplored_dirs:
                angle = dir_angles[d]
                diff = abs(pa - angle)
                if diff > 180:
                    diff = 360 - diff
                if diff < best_diff:
                    best_diff = diff
                    best_dir = d
            suggested = best_dir

        # Nearby doors
        nearby_doors = [
            d for d in self._doors
            if math.hypot(px - d["x"], py - d["y"]) < 512
        ]

        return {
            "cells_explored": len(self._visited),
            "breadcrumbs": len(self._breadcrumbs),
            "explored_directions": explored_dirs,
            "unexplored_directions": unexplored_dirs,
            "suggested_direction": suggested,
            "keys_found": list(self._keys_found),
            "known_key_locations": [
                {"id": oid, **info} for oid, info in self._key_objects.items()
            ],
            "nearby_doors": nearby_doors,
            "total_doors_found": len(self._doors),
            "current_sector_id": self._current_sector_id,
            "visited_sector_ids": sorted(self._visited_sector_ids),
            "explored_sectors": sorted(self._visited_sector_ids),
        }

    def suggested_turn_delta(self, px: float, py: float, pa: float, max_delta: float = 40.0) -> float:
        """Return a signed turn toward a nearby unexplored grid cell."""
        suggested = self.get_exploration_summary(px, py, pa).get("suggested_direction")
        target_angles = {
            "east": 0.0,
            "north": 90.0,
            "west": 180.0,
            "south": 270.0,
        }
        if suggested not in target_angles:
            return 0.0
        delta = (target_angles[suggested] - pa + 180.0) % 360.0 - 180.0
        return max(-max_delta, min(max_delta, delta))


def _sector_at_position(px: float, py: float, sectors: list[dict]) -> int | None:
    for index, sector in enumerate(sectors):
        sector_id = sector.get("id", index)
        lines = sector.get("lines") or []
        if _point_in_closed_lines(px, py, lines):
            try:
                return int(sector_id)
            except (TypeError, ValueError):
                return index
    return None


def _point_in_closed_lines(px: float, py: float, lines: list[dict]) -> bool:
    if not lines:
        return False
    inside = False
    for line in lines:
        try:
            x1 = float(line["x1"])
            y1 = float(line["y1"])
            x2 = float(line["x2"])
            y2 = float(line["y2"])
        except (KeyError, TypeError, ValueError):
            continue
        if _point_on_segment(px, py, x1, y1, x2, y2):
            return True
        crosses = (y1 > py) != (y2 > py)
        if not crosses:
            continue
        x_intersection = (x2 - x1) * (py - y1) / (y2 - y1) + x1
        if px < x_intersection:
            inside = not inside
    return inside


def _point_on_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
    if abs(cross) > 1e-6:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= 1e-6
