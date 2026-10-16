"""Step 2 check: load the start state, step 60 frames, print what RAM says.

The three addresses below are pokered symbols (wCurMap, wYCoord, wXCoord); step 3 builds the
full map. If they read 0 / 3 / 5-ish in Pallet Town's bedroom, the state and the addresses agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402

W_CUR_MAP = 0xD35E
W_Y_COORD = 0xD361
W_X_COORD = 0xD362


def main() -> int:
    with Emu(window="null", speed=0) as emu:
        emu.load_state(config.START_STATE)
        ok = emu.tick(60)
        print("ticked 60 frames:", ok)
        print("map id:", emu.read(W_CUR_MAP), " y:", emu.read(W_Y_COORD), " x:", emu.read(W_X_COORD))
        party = emu.game.party
        print("party size:", len(party))
        for p in party:
            print("  ", p["species"], "lvl", p["level"], "hp", p["hp"], "/", p["max_hp"])
        # Try each direction twice; report which ones actually move the player.
        for d in ("down", "left", "up", "right"):
            before = (emu.read(W_X_COORD), emu.read(W_Y_COORD))
            for _ in range(2):
                emu.press(d, hold_frames=10, settle_frames=20)
            after = (emu.read(W_X_COORD), emu.read(W_Y_COORD))
            print(f"  2x {d:5s}: {before} -> {after}  {'moved' if after != before else 'blocked/no-op'}")
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
