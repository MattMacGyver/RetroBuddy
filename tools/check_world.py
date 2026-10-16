"""Step 5 check: route from Red's bedroom to the Viridian City Pokémon Center, and to Pewter City
under two policies. Runs with no ROM."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrobuddy.world import Policy, World  # noqa: E402


def show(label: str, r) -> None:
    if r is None:
        print(f"{label}: NO ROUTE")
        return
    s = r.summary()
    print(f"{label}: {s['steps']} steps, cost {s['cost']:.0f}, {s['grass_tiles']} grass tiles, {len(s['trainers_in_sight'])} trainer sightlines")
    print("   maps:", " -> ".join(s["maps"]))
    if s["trainers_in_sight"]:
        print("   seen by:", s["trainers_in_sight"][:6])


def main() -> int:
    t0 = time.time()
    w = World()
    print(f"loaded {len(w.maps)} maps in {time.time() - t0:.2f}s")
    print("resolve:", w.resolve_map("Viridian City"), w.resolve_map("viridian pokemon center"), w.resolve_map("Pewter City"), w.resolve_map("Oak's lab"))

    start = ("REDS_HOUSE_2F", 3, 6)
    t0 = time.time()
    r = w.route_to_map(start, "VIRIDIAN_POKECENTER")
    print(f"search took {time.time() - t0:.2f}s")
    show("bedroom -> Viridian Pokecenter", r)
    assert r is not None and r.maps()[:3] == ["REDS_HOUSE_2F", "REDS_HOUSE_1F", "PALLET_TOWN"], r and r.maps()
    assert r.maps()[-1] == "VIRIDIAN_POKECENTER"

    for pol in (Policy.fight(), Policy.avoid_encounters()):
        t0 = time.time()
        r = w.route_to_map(start, "PEWTER_CITY", pol)
        print(f"[{pol.name}] search took {time.time() - t0:.2f}s")
        show(f"bedroom -> Pewter City [{pol.name}]", r)
        assert r is not None and "VIRIDIAN_FOREST" in r.maps()

    print("WORLD OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
