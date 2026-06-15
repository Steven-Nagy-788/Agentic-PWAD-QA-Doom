"""Spatial navigation memory for tracking explored areas, keys, and doors."""

import heapq
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
            "walkable_cells_total": None,
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

    def compute_walkable_cells_from_sectors(self, sectors: list[dict] | None = None) -> int:
        """Estimate total walkable cells from sector geometry.

        Uses sector bounding box area divided by cell size to estimate
        how many grid cells the map contains.
        """
        if sectors is None:
            return 0
        return compute_walkable_cells_from_sectors(sectors)


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


# ── MapGraph: sector connectivity for softlock detection ──────────────────────


class MapGraph:
    """Topological graph of sector connectivity for reachability analysis.

    Nodes are sectors. Edges connect sectors that share a linedef.
    Edges are tagged with properties (door, key-locked, teleporter).
    Supports BFS reachability queries and exit-reachability checks.
    """

    def __init__(self) -> None:
        self._sectors: dict[int, dict] = {}
        self._adjacency: dict[int, set[int]] = {}
        self._edge_info: dict[tuple[int, int], dict] = {}
        self._exit_sector: int | None = None
        self._spawn_sector: int | None = None

    def build(self, sectors: list[dict]) -> None:
        """Build the graph from ViZDoom sector geometry."""
        self._sectors.clear()
        self._adjacency.clear()
        self._edge_info.clear()
        self._exit_sector = None
        self._spawn_sector = None

        # Index sectors by ID
        for i, sector in enumerate(sectors):
            sid = sector.get("id", i)
            self._sectors[sid] = sector
            self._adjacency[sid] = set()

        # Build adjacency from shared linedefs
        # Two sectors are adjacent if they share a linedef (wall segment)
        linedef_sectors: dict[tuple[int, int], list[int]] = {}
        for i, sector in enumerate(sectors):
            sid = sector.get("id", i)
            for line in sector.get("lines", []):
                x1 = int(line.get("x1", 0))
                y1 = int(line.get("y1", 0))
                x2 = int(line.get("x2", 0))
                y2 = int(line.get("y2", 0))
                # Normalize the key
                key = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
                linedef_sectors.setdefault(key, []).append(sid)

        # Connect sectors that share linedefs
        for key, sids in linedef_sectors.items():
            unique_sids = list(set(sids))
            for a in range(len(unique_sids)):
                for b in range(a + 1, len(unique_sids)):
                    sa, sb = unique_sids[a], unique_sids[b]
                    self._adjacency[sa].add(sb)
                    self._adjacency[sb].add(sa)

    def set_exit_sector(self, sector_id: int) -> None:
        self._exit_sector = sector_id

    def set_spawn_sector(self, sector_id: int) -> None:
        self._spawn_sector = sector_id

    def reachable_sectors(self, start: int) -> set[int]:
        """BFS from start sector, returns set of reachable sector IDs."""
        if start not in self._adjacency:
            return set()
        visited = {start}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for neighbor in self._adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def is_exit_reachable(self, from_sector: int | None = None) -> bool:
        """Check if the exit sector is reachable from the given or spawn sector."""
        start = from_sector or self._spawn_sector
        if start is None or self._exit_sector is None:
            return True  # Unknown — assume reachable
        reachable = self.reachable_sectors(start)
        return self._exit_sector in reachable

    def sink_nodes(self) -> list[int]:
        """Find sectors with no path to the exit (potential softlock sinks)."""
        if self._exit_sector is None:
            return []
        # Reverse BFS from exit
        reverse_adj: dict[int, set[int]] = {sid: set() for sid in self._adjacency}
        for a, neighbors in self._adjacency.items():
            for b in neighbors:
                reverse_adj[b].add(a)

        can_reach_exit: set[int] = set()
        queue = [self._exit_sector]
        can_reach_exit.add(self._exit_sector)
        while queue:
            current = queue.pop(0)
            for predecessor in reverse_adj.get(current, set()):
                if predecessor not in can_reach_exit:
                    can_reach_exit.add(predecessor)
                    queue.append(predecessor)

        return [sid for sid in self._adjacency if sid not in can_reach_exit]

    def summary(self) -> dict:
        """Return a summary of the graph for the LLM."""
        sinks = self.sink_nodes()
        reachable_from_spawn = (
            self.reachable_sectors(self._spawn_sector) if self._spawn_sector else set()
        )
        return {
            "total_sectors": len(self._sectors),
            "total_edges": sum(len(n) for n in self._adjacency.values()) // 2,
            "exit_sector": self._exit_sector,
            "spawn_sector": self._spawn_sector,
            "exit_reachable_from_spawn": self.is_exit_reachable(),
            "reachable_from_spawn_count": len(reachable_from_spawn),
            "sink_sectors": sinks,
            "sink_count": len(sinks),
        }

    def shortest_path(self, start: int, goal: int) -> list[int] | None:
        """A* shortest path from start to goal sector. Returns list of sector IDs or None."""
        if start not in self._adjacency or goal not in self._adjacency:
            return None
        if start == goal:
            return [start]

        # Heuristic: straight-line distance between sector centroids
        def _centroid(sector_id: int) -> tuple[float, float]:
            sector = self._sectors.get(sector_id, {})
            lines = sector.get("lines", [])
            if not lines:
                return (0.0, 0.0)
            xs = []
            ys = []
            for line in lines:
                xs.extend([line.get("x1", 0), line.get("x2", 0)])
                ys.extend([line.get("y1", 0), line.get("y2", 0)])
            return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else (0.0, 0.0)

        centroids = {sid: _centroid(sid) for sid in self._adjacency}

        def heuristic(a: int, b: int) -> float:
            ax, ay = centroids[a]
            bx, by = centroids[b]
            return math.hypot(ax - bx, ay - by)

        # A* algorithm
        open_set: list[tuple[float, int]] = [(heuristic(start, goal), start)]
        came_from: dict[int, int] = {}
        g_score: dict[int, float] = {start: 0.0}

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == goal:
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                return list(reversed(path))

            for neighbor in self._adjacency.get(current, set()):
                tentative_g = g_score[current] + 1.0  # Unweighted edges
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score, neighbor))

        return None  # No path found

    def path_to_exit(self, from_sector: int | None = None) -> list[int] | None:
        """Find shortest path from given (or spawn) sector to exit."""
        start = from_sector or self._spawn_sector
        if start is None or self._exit_sector is None:
            return None
        return self.shortest_path(start, self._exit_sector)


def compute_walkable_cells_from_sectors(sectors: list[dict]) -> int:
    """Estimate total walkable cells from sector geometry.

    Uses sector bounding box area divided by cell size to estimate
    how many grid cells the map contains.
    """
    total_area = 0.0
    for sector in sectors:
        lines = sector.get("lines", [])
        if not lines:
            continue
        xs = []
        ys = []
        for line in lines:
            xs.extend([line.get("x1", 0), line.get("x2", 0)])
            ys.extend([line.get("y1", 0), line.get("y2", 0)])
        if not xs:
            continue
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        total_area += width * height

    cell_area = _CELL_SIZE * _CELL_SIZE
    if cell_area <= 0:
        return 0
    return max(1, int(total_area / cell_area))


def build_map_graph(sectors: list[dict]) -> MapGraph:
    """Build a MapGraph from ViZDoom sector geometry."""
    graph = MapGraph()
    graph.build(sectors)
    return graph
