"""--dev (Bible D22): make a save state for testing that skips story gates.

    python tools/make_dev_state.py            # saves/dev_starter.state: start state + Charmander L5 + "got starter" flags

Uses PyBoy's Gen 1 wrapper to inject a party member and set event flags. This is a cheat;
it exists for testing the pilot and companion without replaying the opening every time.
Never used by the companion on its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402
from retrobuddy.extractor import extract, summary  # noqa: E402

STARTER_FLAGS = [
    "oak_appeared_in_pallet",
    "followed_oak_into_lab",
    "followed_oak_into_lab_2",
    "oak_asked_to_choose_mon",
    "got_starter",
    "battled_rival_in_oaks_lab",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=Path, default=config.START_STATE)
    ap.add_argument("--out", type=Path, default=config.SAVE_DIR / "dev_starter.state")
    ap.add_argument("--species", default="CHARMANDER")
    ap.add_argument("--level", type=int, default=5)
    args = ap.parse_args()
    with Emu(window="null", speed=0) as emu:
        emu.load_state(args.src)
        emu.tick(10)
        emu.game.add_pokemon(args.species, level=args.level, moves=["SCRATCH", "GROWL"], max_hp=20, stats={"attack": 11, "defense": 10, "speed": 13, "special": 11})
        for f in STARTER_FLAGS:
            emu.game.set_event_flag(f)
        emu.tick(10)
        print(summary(extract(emu)))
        emu.save_state(args.out)
        print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
