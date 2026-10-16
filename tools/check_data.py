"""Step 4 check: the built data has the right shape, and Route 1 is walkable end to end."""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
maps = json.loads((ROOT / "data/maps.json").read_text())

errors = []

def expect(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        errors.append(msg)

pt = maps["PALLET_TOWN"]
expect(pt["id"] == 0 and (pt["width"], pt["height"]) == (20, 18), "Pallet Town is map 0, 20x18 tiles")
expect(len(pt["warps"]) == 3, f"Pallet Town has 3 warps (got {len(pt['warps'])})")
expect(pt["grid"][5][5] == ".", "Red's front door tile (5,5) is walkable")
expect({c["map"] for c in pt["connections"]} == {"ROUTE_1", "ROUTE_21"}, "Pallet Town connects to Route 1 and Route 21")

r2 = maps["REDS_HOUSE_2F"]
expect(r2["id"] == 38 and r2["grid"][6][3] == ".", "Red's bedroom is map 38 and the start tile (3,6) is walkable")
expect(r2["warps"] == [{"x": 7, "y": 1, "dest_map": "REDS_HOUSE_1F", "dest_warp": 2}], "bedroom stairs warp at (7,1)")

r1 = maps["REDS_HOUSE_1F"]
expect(any(n["sprite"] == "SPRITE_MOM" and (n["x"], n["y"]) == (5, 4) for n in r1["npcs"]), "Mom at (5,4) downstairs")

route1 = maps["ROUTE_1"]

def bfs(m: dict, start: tuple[int, int], goal_pred) -> int | None:
    W, H, g = m["width"], m["height"], m["grid"]
    ledge = {(l["x"], l["y"], l["dir"]) for l in m["ledges"]}
    blocked = {(b["x"], b["y"], b["dir"]) for b in m["blocked_edges"]}
    step = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
    seen = {start}
    q = deque([(start, 0)])
    while q:
        (x, y), d = q.popleft()
        if goal_pred(x, y):
            return d
        for name, (dx, dy) in step.items():
            if (x, y, name) in blocked:
                continue
            if (x, y, name) in ledge:
                nx, ny = x + 2 * dx, y + 2 * dy
            else:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < W and 0 <= ny < H) or g[ny][nx] in "#~":
                    continue
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append(((nx, ny), d + 1))
    return None

# Route 1: enter from Pallet Town at the bottom (x=10, last row), reach the top row.
bottom = next((x, route1["height"] - 1) for x in range(route1["width"]) if route1["grid"][-1][x] in ".,")
dist = bfs(route1, bottom, lambda x, y: y == 0 and route1["grid"][0][x] in ".,")
expect(dist is not None, f"Route 1 is walkable bottom to top (steps: {dist})")
# And it is NOT walkable top to bottom without using ledges the other way? (ledges are one-way: down)
expect(all(l["dir"] == "down" for l in route1["ledges"]), "all Route 1 ledges are one-way downward")

# Pallet Town: from Red's door to the Route 1 edge
dist2 = bfs(pt, (5, 5), lambda x, y: y == 0 and pt["grid"][0][x] in ".,")
expect(dist2 is not None, f"Pallet Town: Red's door to the north edge (steps: {dist2})")

print(f"\n{len(maps)} maps; maps.json {(ROOT / 'data/maps.json').stat().st_size // 1024} KB")
print("CHECK OK" if not errors else f"{len(errors)} FAILURES")
sys.exit(1 if errors else 0)
