"""The pilot: the only thing that presses buttons. Deterministic, interruptible, no model.

Verbs (step 1 scope): travel(destination, policy), advance_text().
Events it returns: arrived, encounter_started, text_opened, blocked, script_control, no_route.

Every press is verified against RAM: after pressing a direction the pilot watches x/y/map each
frame and decides the next press from what actually happened, never from what it assumed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from . import ram_map as R
from .emu import Emu
from .extractor import GameState, extract
from .world import Node, Policy, Route, World

STEP_FRAMES_MAX = 40  # a Gen 1 step is 16 frames; give a turn + a step room
WARP_FRAMES_MAX = 180  # door fade in/out
NPC_WAIT_FRAMES = 40
NPC_WAIT_TRIES = 6
SCRIPT_WAIT_FRAMES = 180  # fades, door animations and battle exits lock input for a while


@dataclass
class Event:
    kind: str
    detail: str = ""
    state: GameState | None = None

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}" if self.detail else self.kind


@dataclass
class Pilot:
    emu: Emu
    world: World
    log: Callable[[str], None] = print

    # --- helpers -----------------------------------------------------------

    def state(self) -> GameState:
        return extract(self.emu)

    def node(self, s: GameState | None = None) -> Node:
        s = s or self.state()
        return (self.world.by_id[s.map_id].const, s.x, s.y)

    def _interrupt(self, s: GameState) -> Event | None:
        if s.battle is not None:
            return Event("encounter_started", f"{s.battle.kind} {s.battle.enemy_species} L{s.battle.enemy_level}", s)
        if s.text_box_open:
            return Event("text_opened", s.text, s)
        return None

    def _settle(self, max_frames: int = 60) -> None:
        """Wait for a step animation to finish."""
        for _ in range(max_frames):
            if self.emu.read(R.wWalkCounter) == 0:
                return
            self.emu.tick(1)

    def wait_for_control(self, max_frames: int = SCRIPT_WAIT_FRAMES) -> bool:
        """Wait until the game gives the player the controls back (no script lock, no step in progress).

        Returns True if control is available, False if a script still holds it after max_frames.
        """
        quiet = 0
        for _ in range(max_frames):
            s = self.state()
            if s.battle is not None or s.text_box_open:
                return True  # those are events for the caller, not a lock
            if not s.script_control and not s.moving:
                quiet += 1
                if quiet >= 8:
                    return True
            else:
                quiet = 0
            self.emu.tick(1)
        return False

    # --- one press --------------------------------------------------------

    def step(self, direction: str, expect: Node) -> Event | None:
        """Hold a direction until the player's tile (or map) changes, or timeout.

        Returns None on success (we are at `expect`), else an Event describing what happened.
        """
        before = self.node()
        self.emu.hold(direction)
        try:
            for f in range(STEP_FRAMES_MAX):
                self.emu.tick(1)
                s = self.state()
                ev = self._interrupt(s)
                if ev:
                    return ev
                cur = self.node(s)
                if cur != before:
                    break
            else:
                return Event("blocked", f"no movement pressing {direction} at {before}")
        finally:
            self.emu.release(direction)
        self._settle()
        # A ledge jump moves two tiles; the position changes before the landing. Give it time to land.
        if abs(expect[1] - before[1]) + abs(expect[2] - before[2]) == 2 and expect[0] == before[0]:
            for _ in range(48):
                if self.node() == expect:
                    break
                self.emu.tick(1)
            self._settle()
        s = self.state()
        ev = self._interrupt(s)
        if ev:
            return ev
        cur = self.node(s)
        if cur == expect:
            return None
        # Warp or map edge: the map may still be transitioning. Wait for it.
        if cur[0] != expect[0] or before[0] != expect[0]:
            for _ in range(WARP_FRAMES_MAX):
                self.emu.tick(1)
                s = self.state()
                ev = self._interrupt(s)
                if ev:
                    return ev
                cur = self.node(s)
                if cur == expect:
                    self._settle()
                    return None
        return Event("off_route", f"pressed {direction} from {before}, expected {expect}, at {cur}")

    # --- verbs --------------------------------------------------------------

    def travel(self, destination: str, policy: Policy | None = None, max_replans: int = 20) -> Event:
        policy = policy or Policy.fight()
        dest = self.world.resolve_map(destination)
        if dest is None:
            return Event("no_route", f"unknown place {destination!r}")
        replans = 0
        self.world.temp_blocked.clear()
        while True:
            self.wait_for_control()
            s = self.state()
            ev = self._interrupt(s)
            if ev:
                return ev
            if s.script_control:
                return Event("script_control", "a script has the controls", s)
            start = self.node(s)
            if start[0] == dest:
                return Event("arrived", self.world.maps[dest].name, s)
            route = self.world.route_to_map(start, dest, policy)
            if route is None:
                return Event("no_route", f"no path from {start} to {dest}", s)
            self.log(f"[pilot] route {start} -> {dest}: {len(route.presses)} steps via {' > '.join(route.summary()['maps'])}")
            ev = self._follow(route)
            if ev is None:
                self.wait_for_control()
                s = self.state()
                return self._interrupt(s) or Event("arrived", self.world.maps[dest].name, s)
            if ev.kind in ("blocked", "off_route") and replans < max_replans:
                replans += 1
                self.log(f"[pilot] {ev}; replanning ({replans})")
                continue
            return ev

    def _follow(self, route: Route) -> Event | None:
        for i, (d, expect) in enumerate(zip(route.presses, route.nodes[1:])):
            cur = self.node()
            if cur != route.nodes[i]:
                return Event("off_route", f"at {cur}, route expected {route.nodes[i]}")
            ev = self.step(d, expect)
            if ev is None:
                continue
            if ev.kind == "blocked":
                # An NPC in the way? Wait for it to move, retry, then give up to the replanner.
                npc_here = self._npc_at(expect)
                for t in range(NPC_WAIT_TRIES if npc_here else 1):
                    self.emu.tick(NPC_WAIT_FRAMES)
                    ev2 = self.step(d, expect)
                    if ev2 is None:
                        break
                    if ev2.kind != "blocked":
                        return ev2
                else:
                    self.world.temp_blocked.add(expect)
                    return ev
                continue
            return ev
        return None

    def _npc_at(self, node: Node) -> bool:
        s = self.state()
        return any((n["x"], n["y"]) == (node[1], node[2]) for n in s.npcs)

    def advance_text(self, max_presses: int = 30) -> Event:
        """Press A through dialogue until the box closes or a choice is pending."""
        for _ in range(max_presses):
            s = self.state()
            if not s.text_box_open:
                return Event("text_closed", "", s)
            if s.battle:
                return Event("encounter_started", "", s)
            self.emu.press("a", hold_frames=2, settle_frames=20)
        return Event("text_still_open", self.state().text, self.state())


def main() -> int:
    import argparse

    from . import config

    ap = argparse.ArgumentParser(description="Walk somewhere. Example: python -m retrobuddy.pilot --to 'Viridian City'")
    ap.add_argument("--to", required=True)
    ap.add_argument("--policy", choices=["fight", "avoid", "hunt"], default="fight")
    ap.add_argument("--window", action="store_true", help="show the PyBoy window")
    ap.add_argument("--speed", type=int, default=1, help="emulation speed multiple (0 = unlimited)")
    ap.add_argument("--state", default=str(config.START_STATE))
    args = ap.parse_args()

    policy = {"fight": Policy.fight, "avoid": Policy.avoid_encounters, "hunt": Policy.hunt}[args.policy]()
    world = World()
    with Emu(window="SDL2" if args.window else "null", speed=args.speed) as emu:
        from pathlib import Path

        emu.load_state(Path(args.state))
        emu.tick(30)
        pilot = Pilot(emu, world)
        t0 = time.time()
        ev = pilot.travel(args.to, policy)
        s = ev.state or pilot.state()
        print(f"[pilot] result: {ev}  (in {time.time() - t0:.1f}s)")
        print(f"[pilot] now at {s.map_name} ({s.x},{s.y}) facing {s.facing}")
        if args.window:
            print("[pilot] leaving the window open for 10 s so you can look")
            for _ in range(600):
                if not emu.tick(1, render=True):
                    break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
