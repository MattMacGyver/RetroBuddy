"""Step 3 check: print the GameState from the start state, then move and print again.

Expected in the bedroom: reds_house_2f, x=3 y=6, facing changes when a new direction is
pressed once, position changes on the second press. Then walk to the stairs and go down:
map should change to reds_house_1f and warps/npcs should change with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402
from retrobuddy.extractor import extract, summary  # noqa: E402


def show(emu: Emu, title: str) -> None:
    print(f"--- {title} ---")
    print(summary(extract(emu)))
    print()


def main() -> int:
    with Emu(window="null", speed=0) as emu:
        emu.load_state(config.START_STATE)
        emu.tick(30)
        show(emu, "start state")

        emu.press("left", hold_frames=4, settle_frames=20)
        show(emu, "after ONE tap left (expect: facing left, same tile)")

        emu.press("left", hold_frames=10, settle_frames=24)
        show(emu, "after a second, longer press left (expect: x decreased)")

        # Walk toward the stairs: in Red's bedroom they are at the top-right (x=7, y=1).
        s = extract(emu)
        print(f"walking from ({s.x},{s.y}) toward the stairs warp...")
        for w in s.warps:
            print("  warp:", w)
        # crude walk: go up to y=1 then right to x=7 (no pathfinding yet; that's step 5)
        for _ in range(12):
            if extract(emu).y <= 1:
                break
            emu.press("up", hold_frames=12, settle_frames=24)
        for _ in range(12):
            if extract(emu).x >= 7:
                break
            emu.press("right", hold_frames=12, settle_frames=24)
        for _ in range(3):
            if extract(emu).map_id != 38:
                break
            emu.press("up", hold_frames=12, settle_frames=30)
        emu.tick(120)
        show(emu, "after stepping onto the stairs (expect: reds_house_1f, Mom as an npc)")
    print("DUMP OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
