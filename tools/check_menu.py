"""Plan 2 step 1 check: menu extraction, using the Start menu (no walking needed)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy import config  # noqa: E402
from retrobuddy.emu import Emu  # noqa: E402
from retrobuddy.extractor import extract, summary  # noqa: E402


def main() -> int:
    with Emu(window="null", speed=0) as emu:
        emu.load_state(config.SAVE_DIR / "dev_starter.state")
        emu.tick(30)
        print("menu before:", extract(emu).menu)
        emu.press("start", hold_frames=3, settle_frames=40)
        s = extract(emu)
        print("after START:", s.menu)
        print(summary(s))
        emu.press("down", hold_frames=3, settle_frames=15)
        emu.press("down", hold_frames=3, settle_frames=15)
        s = extract(emu)
        print("after 2x down: cursor", s.menu.cursor if s.menu else None, "->", s.menu.items[s.menu.cursor] if s.menu else None)
        emu.press("b", hold_frames=3, settle_frames=30)
        print("after B:", extract(emu).menu)
    print("MENU CHECK DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
