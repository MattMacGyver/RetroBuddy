"""Create saves/red_start.state: Pokémon Red just after the intro, standing in the bedroom.

Default: automatic intro (default names RED / BLUE), headless.
    python tools/make_savestate.py

Manual (Bible D23 — choose your own names): opens a window; play through the intro with
arrow keys, Z = A, X = B, Enter = Start; when you are standing in the bedroom, close the
window and the state is saved.
    python tools/make_savestate.py --manual

Why not PyBoy's own start_game(): it was written against Blue and asserts the letter "B"
on the first name screen; Red shows "R" there. The sequence below is the same with a
check that accepts either.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402

TILE_TEXT_ARROW = 238  # the blinking "▼" at the bottom-right of a text box
TILE_NEW_GAME = 141  # "N" of NEW GAME in the title menu
TILE_CONTINUE = 130  # "C" of CONTINUE (a save exists — we don't want that here)
TILES_NEW = (141, 132, 150)  # "N","E","W" of NEW NAME (pokered charmap: A=0x80)
TILES_NAME_Q = (141, 128, 140, 132, 230)  # "NAME?" on the letter-entry keyboard
W_CUR_MAP = 0xD35E
MAP_REDS_HOUSE_2F = 38  # the bedroom


def _title_menu(emu: Emu) -> None:
    pb = emu.pyboy
    pb.tick(120, False, False)
    for _ in range(8000):
        if pb.tilemap_window[2, 2] == TILE_NEW_GAME:
            print("  title menu: NEW GAME")
            pb.button("start")
            pb.tick(100, False, False)
            return
        if pb.tilemap_window[2, 2] == TILE_CONTINUE:
            raise RuntimeError("the ROM has a save (CONTINUE shown); delete the .sav/.ram next to the ROM")
        pb.button("start")
        pb.tick(10, False, False)
    raise RuntimeError("never reached the title menu")


def _find_text(pb, tiles, rows=range(0, 12)) -> tuple[int, int] | None:
    """Return (x, y) where the tile sequence starts, searching the window tilemap, or None."""
    for y in rows:
        row = [pb.tilemap_window[x, y] % 256 for x in range(20)]
        for x in range(20 - len(tiles) + 1):
            if tuple(row[x : x + len(tiles)]) == tuple(tiles):
                return x, y
    return None


def _dump(pb) -> str:
    return "\n".join(f"    row {y:2d}: " + " ".join(f"{pb.tilemap_window[x, y]:3d}" for x in range(20)) for y in range(18))


def run_intro(emu: Emu, max_steps: int = 4000) -> None:
    """State-driven: look at the screen, do the one thing it calls for, repeat until in the bedroom.

    Doesn't count text boxes (Red and Blue differ), so it survives timing drift.
    """
    pb = emu.pyboy
    _title_menu(emu)
    names_picked = 0
    in_bedroom_frames = 0
    for step in range(max_steps):
        if emu.read(W_CUR_MAP) == MAP_REDS_HOUSE_2F and names_picked == 2:
            if pb.tilemap_window[18, 16] == TILE_TEXT_ARROW:
                in_bedroom_frames = 0  # Oak is still talking; dismiss and keep waiting
                pb.button("a")
                pb.tick(20, False, False)
                continue
            in_bedroom_frames += 10
            if in_bedroom_frames >= 420:  # ~7 s with no text box: speech and shrink transition are done
                print(f"  in the bedroom with control after {step} steps")
                return
            pb.tick(10, False, False)
            continue
        if _find_text(pb, TILES_NAME_Q, rows=range(0, 3)) is not None:
            print(f"  keyboard appeared at step {step}; backing out with B")
            pb.button("b", 3)
            pb.tick(40, False, False)
            continue
        hit = _find_text(pb, TILES_NEW)
        if hit is not None and pb.tilemap_window[18, 16] != TILE_TEXT_ARROW:
            which = "player" if names_picked == 0 else "rival"
            print(f"  {which} name screen at step {step} (NEW NAME at {hit}); picking the first preset")
            pb.tick(30, False, False)  # let the menu become interactive
            pb.button("down", 3)
            pb.tick(15, False, False)
            pb.button("a", 3)
            pb.tick(40, False, False)
            names_picked += 1
            continue
        if pb.tilemap_window[18, 16] == TILE_TEXT_ARROW:
            pb.button("a")
            pb.tick(20, False, False)
            continue
        pb.tick(10, False, False)
    raise RuntimeError(f"intro did not finish; map={emu.read(W_CUR_MAP)} names={names_picked}\n{_dump(pb)}")


def automatic(out: Path) -> None:
    print(f"ROM: {config.RED_ROM}")
    with Emu(window="null", speed=0) as emu:
        print("Cartridge:", emu.pyboy.cartridge_title)
        print("Running the intro...")
        run_intro(emu)
        emu.tick(60)
        emu.save_state(out)
        print(f"Saved {out} ({out.stat().st_size} bytes)")


def manual(out: Path) -> None:
    print(f"ROM: {config.RED_ROM}")
    print("Play through the intro. Close the window once you are standing in the bedroom.")
    emu = Emu(window="SDL2", speed=1)
    try:
        while emu.tick(1, render=True):
            pass
    finally:
        emu.save_state(out)
        print(f"Saved {out} ({out.stat().st_size} bytes)")
        emu.stop()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true", help="play the intro yourself in a window")
    ap.add_argument("--out", type=Path, default=config.START_STATE)
    args = ap.parse_args()
    config.ensure_dirs()
    (manual if args.manual else automatic)(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
