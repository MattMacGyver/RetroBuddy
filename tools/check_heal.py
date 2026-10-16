"""Plan 2 step 3 check: heal_at_center from the bedroom with Charmander at 2 HP (dev-set)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyboy.plugins import game_wrapper_pokemon_gen1_constants as C  # noqa: E402

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402
from retrobuddy.pilot import Pilot  # noqa: E402
from retrobuddy.world import World  # noqa: E402


def main() -> int:
    world = World()
    with Emu(window="null", speed=0) as emu:
        emu.load_state(config.SAVE_DIR / "dev_starter.state")
        emu.tick(30)
        p = Pilot(emu, world)
        p.dev_repel(250)
        # dev: set slot 0 HP to 2 (big-endian u16 at party mon + 1)
        emu.pyboy.memory[C.PARTY_MONS_ADDRESS + 1] = 0
        emu.pyboy.memory[C.PARTY_MONS_ADDRESS + 2] = 2
        s = p.state()
        print("before:", [(m.species, m.hp, m.max_hp) for m in s.party])
        ev = p.heal_at_center()
        print("heal_at_center:", ev)
        s = p.state()
        print("after:", [(m.species, m.hp, m.max_hp) for m in s.party], "at", s.map_name, (s.x, s.y))
        print("HEAL OK" if ev.kind == "healed" else "HEAL FAILED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
