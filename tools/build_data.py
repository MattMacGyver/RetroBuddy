"""Build data/*.json from the pret/pokered decompilation.

    python tools/build_data.py            # clones pokered into data/pokered if missing, then builds
    python tools/build_data.py --no-clone # use an existing data/pokered

Outputs (derived facts, not game assets):
  data/maps.json      per map: id, size, tileset, walkability grid, grass/water, warps, connections,
                      NPCs (with trainer class), signs, ledges, blocked edges
  data/tilesets.json  per tileset: passable tile ids, grass tile, water flag

Coordinates: map "tiles" are the 2x2 8-px squares the player stands on; (x, y) as in RAM.
Walkability follows pokered exactly: the bottom-left 8-px tile of a square must be in the
tileset's passable list (home/overworld.asm CheckTilePassable + GetTileAndCoordsInFrontOfPlayer).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
POKERED = DATA / "pokered"
POKERED_URL = "https://github.com/pret/pokered"
POKERED_COMMIT = "af51989"  # pinned; bump deliberately

WATER_TILE = 0x14
DIRS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
FACING_NAMES = {"SPRITE_FACING_DOWN": "down", "SPRITE_FACING_UP": "up", "SPRITE_FACING_LEFT": "left", "SPRITE_FACING_RIGHT": "right"}


def num(tok: str) -> int:
    tok = tok.strip()
    if tok.startswith("$"):
        return int(tok[1:], 16)
    if tok.startswith("-"):
        return -int(tok[1:])
    return int(tok)


def args_of(line: str) -> list[str]:
    return [a.strip() for a in line.split(None, 1)[1].split(",")] if " " in line.strip() else []


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].rstrip()


# --- constants --------------------------------------------------------------

def parse_sprite_constants() -> dict[str, int]:
    out, i = {}, 0
    for line in (POKERED / "constants/sprite_constants.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("const_def"):
            i = 0
        elif line.startswith("const "):
            out[line.split()[1]] = i
            i += 1
    return out


def parse_marts(map_labels: dict[str, str]) -> dict[str, list[list[str]]]:
    """Map const -> list of clerk inventories (a map can have several clerks, e.g. Celadon floors)."""
    out: dict[str, list[list[str]]] = {}
    label = None
    for line in (POKERED / "data/items/marts.asm").read_text().splitlines():
        raw = line
        line = strip_comment(line).strip()
        m = re.match(r"(\w+?)(Clerk\d?|Clerk\dText|)(Text)?::", line)
        if line.endswith("::"):
            label = line[:-2]
            continue
        if line.startswith("script_mart") and label and "unreferenced" not in raw:
            base = re.sub(r"Clerk\d?Text$", "", label)
            const = map_labels.get(base)
            if const:
                out.setdefault(const, []).append(args_of(line))
    return out


def parse_prices() -> dict[str, int]:
    """Item name -> price (ItemPrices is in item-id order; TM prices separate)."""
    names = []
    for line in (POKERED / "constants/item_constants.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("const ") and not line.startswith("const_"):
            names.append(line.split()[1])
    prices = []
    for line in (POKERED / "data/items/prices.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("bcd3 "):
            prices.append(int(line.split()[1]))
    # item ids start at 1 (MASTER_BALL); the first const is NO_ITEM, so prices[i-1] is item i's price
    out = {names[i]: prices[i - 1] for i in range(1, min(len(names), len(prices) + 1))}
    tm = []
    for line in (POKERED / "data/items/tm_prices.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("nybble ") or line.startswith("db "):
            tm.extend(int(x) for x in re.findall(r"\d+", line))
    for i, p in enumerate(tm, start=1):
        out[f"TM_{i:02d}"] = p * 1000
    return out


def parse_map_constants() -> list[dict]:
    maps = []
    for line in (POKERED / "constants/map_constants.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("map_const "):
            const, w, h = args_of(line)
            maps.append({"const": const, "id": len(maps), "width_blocks": int(w), "height_blocks": int(h)})
    return maps


def parse_tileset_constants() -> list[str]:
    out = []
    for line in (POKERED / "constants/tileset_constants.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("const "):
            out.append(line.split()[1])
    return out


def parse_tileset_headers() -> list[dict]:
    """Order matches tileset_constants. name, grass tile."""
    out = []
    for line in (POKERED / "data/tilesets/tileset_headers.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("tileset "):
            a = args_of(line)
            counters = [num(t) for t in a[1:4] if num(t) >= 0]
            out.append({"name": a[0], "grass_tile": num(a[4]) if num(a[4]) >= 0 else None, "counter_tiles": counters})
    return out


def parse_collision() -> dict[str, list[int]]:
    """Label (e.g. 'Overworld') -> passable tile ids. Labels may share one list."""
    out: dict[str, list[int]] = {}
    pending: list[str] = []
    for line in (POKERED / "data/tilesets/collision_tile_ids.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        m = re.match(r"(\w+)_Coll::", line)
        if m:
            pending.append(m.group(1))
        elif line.startswith("coll_tiles"):
            tiles = [num(t) for t in args_of(line)] if "," in line or len(line.split()) > 1 else []
            for lab in pending:
                out[lab] = tiles
            pending = []
    return out


def parse_block_files() -> dict[str, str]:
    """Tileset name -> blockset file path (labels may share a file)."""
    out: dict[str, str] = {}
    pending: list[str] = []
    for line in (POKERED / "gfx/tilesets.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        m = re.match(r"(\w+)_Block::\s*(INCBIN\s+\"([^\"]+)\")?", line)
        if m:
            pending.append(m.group(1))
            if m.group(3):
                for lab in pending:
                    out[lab] = m.group(3)
                pending = []
    return out


def parse_water_tilesets() -> set[str]:
    out = set()
    for line in (POKERED / "data/tilesets/water_tilesets.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("db ") and line.split()[1] != "-1":
            out.add(line.split()[1])
    return out


def parse_ledges() -> list[dict]:
    out = []
    for line in (POKERED / "data/tilesets/ledge_tiles.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("db ") and "SPRITE_FACING" in line:
            a = args_of(line)
            out.append({"facing": FACING_NAMES[a[0]], "standing": num(a[1]), "ledge": num(a[2])})
    return out


def parse_pair_collisions() -> list[tuple[str, int, int]]:
    out = []
    section = None
    for line in (POKERED / "data/tilesets/pair_collision_tile_ids.asm").read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("TilePairCollisionsLand"):
            section = "land"
        elif line.startswith("TilePairCollisionsWater"):
            section = "water"
        elif section == "land" and line.startswith("db ") and "-1" not in line:
            a = args_of(line)
            out.append((a[0], num(a[1]), num(a[2])))
    return out


# --- maps -------------------------------------------------------------------

def parse_headers() -> dict[str, dict]:
    out = {}
    for f in sorted((POKERED / "data/maps/headers").glob("*.asm")):
        hdr: dict = {"connections": []}
        for line in f.read_text().splitlines():
            line = strip_comment(line).strip()
            if line.startswith("map_header "):
                label, const, tileset = args_of(line)[:3]
                hdr.update(label=label, const=const, tileset=tileset)
            elif line.startswith("connection "):
                d, label, const, off = args_of(line)
                hdr["connections"].append({"dir": d, "map": const, "offset": num(off)})
        if "const" in hdr:
            out[hdr["const"]] = hdr
    return out


def parse_objects(label: str) -> dict:
    f = POKERED / f"data/maps/objects/{label}.asm"
    out = {"border_block": None, "warps": [], "signs": [], "npcs": []}
    if not f.exists():
        return out
    for line in f.read_text().splitlines():
        line = strip_comment(line).strip()
        if line.startswith("db ") and out["border_block"] is None:
            out["border_block"] = num(line.split()[1])
        elif line.startswith("warp_event "):
            x, y, dest, wid = args_of(line)
            out["warps"].append({"x": int(x), "y": int(y), "dest_map": None if dest == "LAST_MAP" else dest, "dest_warp": int(wid) - 1})
        elif line.startswith("bg_event "):
            x, y, text = args_of(line)
            out["signs"].append({"x": int(x), "y": int(y), "text": text})
        elif line.startswith("object_event "):
            a = args_of(line)
            x, y, sprite, movement, facing_or_range, text = a[:6]
            npc = {"x": int(x), "y": int(y), "sprite": sprite, "movement": movement, "facing": facing_or_range, "text": text}
            if len(a) >= 8:
                npc["trainer_class"] = a[6]
                npc["trainer_team"] = int(a[7])
            elif len(a) == 7:
                npc["item"] = a[6]
            out["npcs"].append(npc)
    return out


def parse_trainers(label: str) -> list[dict]:
    """`trainer EVENT_FLAG, view_range, ...` lines in scripts/<Map>.asm, in trainer-NPC order."""
    f = POKERED / f"scripts/{label}.asm"
    out = []
    if f.exists():
        for line in f.read_text().splitlines():
            line = strip_comment(line).strip()
            if line.startswith("trainer "):
                a = args_of(line)
                out.append({"beaten_flag": a[0], "view_range": int(a[1])})
    return out


def build_tile_grid(blk: bytes, bst: bytes, wb: int, hb: int) -> list[list[int]]:
    """8-px tile grid (4*wb wide, 4*hb tall) from block ids and a blockset (16 tiles per block)."""
    grid = [[0] * (wb * 4) for _ in range(hb * 4)]
    for by in range(hb):
        for bx in range(wb):
            b = blk[by * wb + bx]
            tiles = bst[b * 16 : b * 16 + 16]
            for i, t in enumerate(tiles):
                grid[by * 4 + i // 4][bx * 4 + i % 4] = t
    return grid


def build_map(m: dict, hdr: dict, ts_names: list[str], ts_headers: list[dict], coll: dict, blocks: dict, water_ts: set, ledges: list, pairs: list) -> dict:
    wb, hb = m["width_blocks"], m["height_blocks"]
    label = hdr["label"]
    blk = (POKERED / f"maps/{label}.blk").read_bytes()
    obj = parse_objects(label)
    if len(blk) < wb * hb:  # UndergroundPathNorthSouth is 4x23 in the ROM; the game reads past it. Pad with the border block.
        blk = blk + bytes([obj["border_block"] or 0]) * (wb * hb - len(blk))
    assert len(blk) == wb * hb, f"{label}: blk {len(blk)} != {wb}x{hb}"
    ts_idx = ts_names.index(hdr["tileset"])
    ts_name = ts_headers[ts_idx]["name"]
    bst = (POKERED / blocks[ts_name]).read_bytes()
    passable = set(coll[ts_name])
    grass_tile = ts_headers[ts_idx]["grass_tile"]
    counter_tiles = set(ts_headers[ts_idx]["counter_tiles"])
    tiles = build_tile_grid(blk, bst, wb, hb)
    W, H = wb * 2, hb * 2

    def coll_tile(x: int, y: int) -> int:  # bottom-left 8px tile of square (x, y)
        return tiles[2 * y + 1][2 * x]

    rows = []
    for y in range(H):
        row = ""
        for x in range(W):
            t = coll_tile(x, y)
            if t == WATER_TILE and hdr["tileset"] in water_ts:
                row += "~"
            elif t in counter_tiles:
                row += "c"
            elif t not in passable:
                row += "#"
            elif grass_tile is not None and t == grass_tile:
                row += ","
            else:
                row += "."
        rows.append(row)

    ledge_edges, blocked_edges = [], []
    step = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
    for y in range(H):
        for x in range(W):
            here = coll_tile(x, y)
            for d, (dx, dy) in step.items():
                nx, ny = x + dx, y + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                ahead = coll_tile(nx, ny)
                for L in ledges:
                    if L["facing"] == d and L["standing"] == here and L["ledge"] == ahead:
                        ledge_edges.append({"x": x, "y": y, "dir": d})
                for ts, t1, t2 in pairs:
                    if ts == hdr["tileset"] and {here, ahead} == {t1, t2}:
                        blocked_edges.append({"x": x, "y": y, "dir": d})

    trainers = parse_trainers(label)
    ti = 0
    for npc in obj["npcs"]:
        if "trainer_class" in npc and ti < len(trainers):
            npc.update(trainers[ti])
            ti += 1
    return {
        "id": m["id"],
        "const": m["const"],
        "name": m["const"].lower(),
        "label": label,
        "width": W,
        "height": H,
        "tileset": hdr["tileset"],
        "border_block": obj["border_block"],
        "grid": rows,
        "warps": obj["warps"],
        "connections": hdr["connections"],
        "npcs": obj["npcs"],
        "signs": obj["signs"],
        "ledges": ledge_edges,
        "blocked_edges": blocked_edges,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-clone", action="store_true")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    if not POKERED.exists():
        if args.no_clone:
            print("data/pokered missing", file=sys.stderr)
            return 1
        subprocess.run(["git", "clone", "--depth", "50", POKERED_URL, str(POKERED)], check=True)
        subprocess.run(["git", "-C", str(POKERED), "checkout", POKERED_COMMIT], check=True)

    maps = parse_map_constants()
    ts_names = parse_tileset_constants()
    ts_headers = parse_tileset_headers()
    coll = parse_collision()
    blocks = parse_block_files()
    water_ts = parse_water_tilesets()
    ledges = parse_ledges()
    pairs = parse_pair_collisions()
    headers = parse_headers()

    out, skipped = {}, []
    for m in maps:
        hdr = headers.get(m["const"])
        if not hdr or not (POKERED / f"maps/{hdr['label']}.blk").exists():
            skipped.append(m["const"])
            continue
        out[m["const"]] = build_map(m, hdr, ts_names, ts_headers, coll, blocks, water_ts, ledges, pairs)

    map_labels = {h["label"]: const for const, h in headers.items()}
    marts = parse_marts(map_labels)
    for const, invs in marts.items():
        if const in out:
            out[const]["mart"] = invs
    (DATA / "maps.json").write_text(json.dumps(out, indent=0))
    (DATA / "prices.json").write_text(json.dumps(parse_prices(), indent=0))
    (DATA / "sprites.json").write_text(json.dumps(parse_sprite_constants(), indent=0))
    (DATA / "tilesets.json").write_text(json.dumps(
        {ts_names[i]: {"name": h["name"], "passable": coll[h["name"]], "grass_tile": h["grass_tile"], "counter_tiles": h["counter_tiles"], "water": ts_names[i] in water_ts} for i, h in enumerate(ts_headers)}, indent=1))
    print(f"maps: {len(out)} built, {len(skipped)} skipped (no header/blk): {skipped[:8]}{'...' if len(skipped) > 8 else ''}")
    print(f"pokered commit: {subprocess.run(['git', '-C', str(POKERED), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
