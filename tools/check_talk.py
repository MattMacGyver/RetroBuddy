"""Plan 2 step 2 check: talk_to + choose. Dev state -> Mom downstairs -> Viridian Center nurse -> say NO."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402
from retrobuddy.pilot import Pilot  # noqa: E402
from retrobuddy.world import Policy, World  # noqa: E402


def main() -> int:
    world = World()
    with Emu(window="null", speed=0) as emu:
        emu.load_state(config.SAVE_DIR / "dev_starter.state")
        emu.tick(30)
        p = Pilot(emu, world)
        p.dev_repel(250)  # test-only: no wild encounters on the way
        print("1 travel downstairs:", p.travel("reds house 1f"))
        ev = p.talk_to("mom")
        print("2 talk_to mom:", ev)
        print("   advance:", p.advance_text())
        print("   advance:", p.advance_text())
        p.dev_repel(250)
        print("3 travel to Viridian Pokecenter (avoid):", p.travel("Viridian Pokemon Center", Policy.avoid_encounters()))
        ev = p.talk_to("nurse")
        print("4 talk_to nurse:", ev)
        ev = p.advance_text()
        print("   advance:", ev)
        if ev.kind == "choice_pending":
            print("5 choose no:", p.choose("no"))
            print("   advance:", p.advance_text())
        s = p.state()
        print(f"end: {s.map_name} ({s.x},{s.y}) facing {s.facing}; party hp {[ (m.hp, m.max_hp) for m in s.party]}")
    print("TALK CHECK DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
