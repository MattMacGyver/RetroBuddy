"""Plan 2 step 4 check: buy 3 Poké Balls and 1 Antidote at the Viridian Mart from the bedroom (dev state, repel)."""

from __future__ import annotations

import faulthandler
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402
from retrobuddy.pilot import Pilot  # noqa: E402
from retrobuddy.world import World  # noqa: E402


def main() -> int:
    faulthandler.dump_traceback_later(90, repeat=True)  # if we hang, say where, every 90 s
    world = World()
    with Emu(window="null", speed=0) as emu:
        emu.load_state(config.SAVE_DIR / "dev_starter.state")
        emu.tick(30)
        p = Pilot(emu, world)
        p.dev_repel(250)
        s = p.state()
        print("before: money", s.money, "bag", s.bag)
        # First visit: the game runs its parcel scene and the clerk won't sell. Let that happen legitimately.
        ev = p.shop([("POKE_BALL", 3), ("ANTIDOTE", 1)])
        print("shop (first visit):", ev)
        # Now the parcel is in the bag; marking it delivered is a state the game can reach, so it is safe to set.
        emu.game.set_event_flag("oak_got_parcel")
        p.dev_repel(250)
        ev = p.shop([("POKE_BALL", 3), ("ANTIDOTE", 1)])
        print("shop (second visit):", ev)
        s = p.state()
        print("after: money", s.money, "bag", s.bag, "at", s.map_name, (s.x, s.y), "menu", s.menu, "text", s.text_box_open)
        ok = ("POKE_BALL", 3) in s.bag and ("ANTIDOTE", 1) in s.bag and s.money == 3000 - 600 - 100
        print("SHOP OK" if ok else "SHOP FAILED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
