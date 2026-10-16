"""The world as a graph, and A* over it.

Nodes are (map_const, x, y). Edges: the four steps within a map (subject to the walkability
grid, ledges and blocked edges), stepping onto a warp tile (which lands you in the destination
map), and walking off a map edge into a connected map. Costs come from a Policy, which is how
"avoid grass" vs "hunt in grass" is expressed: same search, different numbers.
"""

from __future__ import annotations

import heapq
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from . import config

STEP = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
Node = tuple[str, int, int]


@dataclass
class Policy:
    """Per-tile costs. 1 = neutral. Big numbers = avoid; <1 not allowed (A* needs non-negative, and we keep >= 1)."""

    grass: float = 1.0
    trainer_sight: float = 1.0  # tiles a stationary trainer can see
    warp: float = 1.0
    name: str = "neutral"

    @classmethod
    def avoid_encounters(cls) -> "Policy":
        return cls(grass=8.0, trainer_sight=12.0, name="avoid")

    @classmethod
    def fight(cls) -> "Policy":
        return cls(grass=1.0, trainer_sight=1.0, name="fight")

    @classmethod
    def hunt(cls) -> "Policy":
        return cls(grass=1.0, trainer_sight=12.0, name="hunt")


@dataclass
class MapData:
    const: str
    id: int
    name: str
    width: int
    height: int
    tileset: str
    grid: list[str]
    warps: list[dict]
    connections: list[dict]
    npcs: list[dict]
    ledges: set[tuple[int, int, str]]
    blocked: set[tuple[int, int, str]]
    sight: set[tuple[int, int]] = field(default_factory=set)  # tiles seen by stationary trainers

    def walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[y][x] in ".,"

    def is_grass(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[y][x] == ","

    def warp_at(self, x: int, y: int) -> dict | None:
        for w in self.warps:
            if w["x"] == x and w["y"] == y:
                return w
        return None


class World:
    def __init__(self, maps_path: Path = config.DATA_DIR / "maps.json"):
        raw = json.loads(Path(maps_path).read_text())
        self.maps: dict[str, MapData] = {}
        self.by_id: dict[int, MapData] = {}
        for const, d in raw.items():
            m = MapData(
                const=const, id=d["id"], name=d["name"], width=d["width"], height=d["height"], tileset=d["tileset"],
                grid=d["grid"], warps=[dict(w) for w in d["warps"]], connections=d["connections"], npcs=d["npcs"],
                ledges={(l["x"], l["y"], l["dir"]) for l in d["ledges"]},
                blocked={(b["x"], b["y"], b["dir"]) for b in d["blocked_edges"]},
            )
            self.maps[const] = m
            self.by_id[m.id] = m
        self._resolve_last_map_warps()
        self._compute_sight()

    # --- data fix-ups ---------------------------------------------------

    def _resolve_last_map_warps(self) -> None:
        """A building's LAST_MAP warps lead back to whichever outdoor map warps into it."""
        entrances: dict[str, list[tuple[str, dict]]] = {}
        for m in self.maps.values():
            for w in m.warps:
                if w["dest_map"]:
                    entrances.setdefault(w["dest_map"], []).append((m.const, w))
        for m in self.maps.values():
            for w in m.warps:
                if w["dest_map"] is None:
                    outside = entrances.get(m.const)
                    if outside:
                        src_map, src_warp = outside[0]
                        w["dest_map"], w["dest_x"], w["dest_y"] = src_map, src_warp["x"], src_warp["y"]
                        w["resolved_from"] = "LAST_MAP"
        for m in self.maps.values():
            for w in m.warps:
                if "dest_x" not in w and w["dest_map"] in self.maps:
                    dest = self.maps[w["dest_map"]]
                    k = w["dest_warp"]
                    if 0 <= k < len(dest.warps):
                        w["dest_x"], w["dest_y"] = dest.warps[k]["x"], dest.warps[k]["y"]

    def _compute_sight(self) -> None:
        facing_dir = {"DOWN": "down", "UP": "up", "LEFT": "left", "RIGHT": "right"}
        for m in self.maps.values():
            for n in m.npcs:
                if "trainer_class" not in n or n["movement"] != "STAY":
                    continue
                d = facing_dir.get(n["facing"])
                if not d:
                    continue
                dx, dy = STEP[d]
                for k in range(1, n.get("view_range", 4) + 1):
                    x, y = n["x"] + dx * k, n["y"] + dy * k
                    if not m.walkable(x, y):
                        break
                    m.sight.add((x, y))

    # --- names ------------------------------------------------------------

    def resolve_map(self, name: str) -> str | None:
        """'Viridian City' -> 'VIRIDIAN_CITY'; 'viridian pokemon center' -> 'VIRIDIAN_POKECENTER'."""
        q = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        q = q.replace("pokemon_center", "pokecenter").replace("poke_center", "pokecenter").replace("pokemart", "mart")
        if q.upper() in self.maps:
            return q.upper()
        words = set(q.split("_"))
        best, best_score = None, 0
        for const, m in self.maps.items():
            mw = set(m.name.split("_"))
            score = len(words & mw) * 10 - len(mw - words)
            if score > best_score:
                best, best_score = const, score
        return best

    # --- graph --------------------------------------------------------------

    def neighbors(self, node: Node, policy: Policy) -> Iterator[tuple[Node, float, str]]:
        """Yield (next_node, cost, direction_pressed)."""
        const, x, y = node
        m = self.maps[const]
        for d, (dx, dy) in STEP.items():
            if (x, y, d) in m.blocked:
                continue
            if (x, y, d) in m.ledges:
                nx, ny = x + 2 * dx, y + 2 * dy
                if m.walkable(nx, ny):
                    yield (const, nx, ny), 1.0, d
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < m.width and 0 <= ny < m.height:
                if not m.walkable(nx, ny):
                    continue
                w = m.warp_at(nx, ny)
                if w and w.get("dest_map") in self.maps and "dest_x" in w:
                    yield (w["dest_map"], w["dest_x"], w["dest_y"]), policy.warp, d
                    continue
                cost = 1.0
                if m.is_grass(nx, ny):
                    cost = max(cost, policy.grass)
                if (nx, ny) in m.sight:
                    cost = max(cost, policy.trainer_sight)
                yield (const, nx, ny), cost, d
            else:
                conn = self._connection_for(m, d)
                if conn is None:
                    continue
                target = self.maps[conn["map"]]
                off = conn["offset"]
                if d == "up":
                    tx, ty = x - 2 * off, target.height - 1
                elif d == "down":
                    tx, ty = x - 2 * off, 0
                elif d == "left":
                    tx, ty = target.width - 1, y - 2 * off
                else:
                    tx, ty = 0, y - 2 * off
                if target.walkable(tx, ty):
                    yield (target.const, tx, ty), 1.0, d

    @staticmethod
    def _connection_for(m: MapData, d: str) -> dict | None:
        want = {"up": "north", "down": "south", "left": "west", "right": "east"}[d]
        for c in m.connections:
            if c["dir"] == want:
                return c
        return None

    # --- search -----------------------------------------------------------

    def route(self, start: Node, goal: Callable[[Node], bool], policy: Policy, heuristic_map: str | None = None, max_nodes: int = 400_000) -> "Route | None":
        """A* (Dijkstra when the goal is in another map). goal(node) -> bool."""
        counter = 0
        open_heap: list[tuple[float, int, Node]] = [(0.0, counter, start)]
        came: dict[Node, tuple[Node, str]] = {}
        g: dict[Node, float] = {start: 0.0}
        closed: set[Node] = set()
        expanded = 0
        while open_heap:
            _, _, cur = heapq.heappop(open_heap)
            if cur in closed:
                continue
            closed.add(cur)
            expanded += 1
            if expanded > max_nodes:
                return None
            if goal(cur):
                return self._build_route(start, cur, came, g[cur], expanded)
            for nxt, cost, d in self.neighbors(cur, policy):
                ng = g[cur] + cost
                if ng < g.get(nxt, float("inf")):
                    g[nxt] = ng
                    came[nxt] = (cur, d)
                    counter += 1
                    heapq.heappush(open_heap, (ng, counter, nxt))
        return None

    def route_to_map(self, start: Node, dest_map: str, policy: Policy | None = None) -> "Route | None":
        policy = policy or Policy.fight()
        return self.route(start, lambda n: n[0] == dest_map, policy)

    def route_to_tile(self, start: Node, dest: Node, policy: Policy | None = None) -> "Route | None":
        policy = policy or Policy.fight()
        return self.route(start, lambda n: n == dest, policy)

    def _build_route(self, start: Node, end: Node, came: dict, cost: float, expanded: int) -> "Route":
        nodes, presses = [end], []
        cur = end
        while cur != start:
            prev, d = came[cur]
            presses.append(d)
            nodes.append(prev)
            cur = prev
        nodes.reverse()
        presses.reverse()
        return Route(nodes=nodes, presses=presses, cost=cost, expanded=expanded, world=self)


@dataclass
class Route:
    nodes: list[Node]
    presses: list[str]
    cost: float
    expanded: int
    world: World

    def maps(self) -> list[str]:
        out = []
        for n in self.nodes:
            if not out or out[-1] != n[0]:
                out.append(n[0])
        return out

    def summary(self) -> dict:
        grass = sum(1 for n in self.nodes if self.world.maps[n[0]].is_grass(n[1], n[2]))
        seen_by = set()
        for n in self.nodes:
            m = self.world.maps[n[0]]
            if (n[1], n[2]) in m.sight:
                for t in m.npcs:
                    if "trainer_class" in t:
                        seen_by.add((n[0], t["trainer_class"], t["x"], t["y"]))
        return {
            "steps": len(self.presses),
            "maps": [self.world.maps[c].name for c in self.maps()],
            "grass_tiles": grass,
            "trainers_in_sight": sorted(seen_by),
            "cost": self.cost,
        }
