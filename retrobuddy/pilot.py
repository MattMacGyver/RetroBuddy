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
from .world import STEP, Node, Policy, Route, World

STEP_FRAMES_MAX = 40  # a Gen 1 step is 16 frames; give a turn + a step room
WARP_FRAMES_MAX = 180  # door fade in/out
NPC_WAIT_FRAMES = 40
NPC_WAIT_TRIES = 6
SCRIPT_WAIT_FRAMES = 180  # fades, door animations and battle exits lock input for a while
ROLE_SPRITES = {
    "nurse": "SPRITE_NURSE", "joy": "SPRITE_NURSE",
    "clerk": "SPRITE_CLERK", "shopkeeper": "SPRITE_CLERK", "cashier": "SPRITE_CLERK",
    "mom": "SPRITE_MOM", "mother": "SPRITE_MOM",
    "oak": "SPRITE_OAK", "professor": "SPRITE_OAK",
    "rival": "SPRITE_BLUE", "blue": "SPRITE_BLUE", "gary": "SPRITE_BLUE",
}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


class PilotTimeout(Exception):
    pass


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
    max_frames_per_verb: int = 60 * 60 * 5  # 5 minutes of game time; a verb that runs longer is stuck
    _verb_start_frame: int = -1
    _verb_name: str = ""

    def _begin_verb(self, name: str) -> bool:
        """Start a budget for the outermost verb. Nested verbs share the outer budget."""
        if self._verb_start_frame >= 0:
            return False
        self._verb_start_frame = self.emu.pyboy.frame_count
        self._verb_name = name
        return True

    def _end_verb(self, outer: bool) -> None:
        if outer:
            self._verb_start_frame = -1
            self._verb_name = ""

    def _check_budget(self) -> None:
        if self._verb_start_frame >= 0 and self.emu.pyboy.frame_count - self._verb_start_frame > self.max_frames_per_verb:
            raise PilotTimeout(f"{self._verb_name} exceeded {self.max_frames_per_verb} frames")

    # --- helpers -----------------------------------------------------------

    def state(self) -> GameState:
        self._check_budget()
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
            # Plan around where NPCs are right now (they wander; the follower retries/replans if they move).
            self.world.temp_blocked = {(start[0], n["x"], n["y"]) for n in s.npcs}
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

    # --- dev-only helpers (D22) ------------------------------------------------

    def dev_repel(self, steps: int = 250) -> None:
        """Pretend a Repel is active so test walks don't get wild encounters. Never used in real play."""
        self.emu.pyboy.memory[R.wRepelRemainingSteps] = steps

    # --- NPCs ---------------------------------------------------------------

    def find_npc(self, target: str) -> tuple[int, dict, tuple[int, int]] | None:
        """Resolve 'nurse' / 'mom' / 'SPRITE_CLERK' / '#2' to (sprite index, map npc record, current (x, y))."""
        s = self.state()
        m = self.world.by_id[s.map_id]
        t = target.strip().lower()
        want = ROLE_SPRITES.get(t)
        idx = None
        if t.startswith("#") and t[1:].isdigit():
            idx = int(t[1:])
        else:
            for i, n in enumerate(m.npcs, start=1):
                name = n["sprite"]
                if name == want or t.upper() in name:
                    idx = i
                    break
        if idx is None or idx > len(m.npcs):
            return None
        rec = m.npcs[idx - 1]
        live = next((n for n in s.npcs if n["sprite"] == idx), None)
        pos = (live["x"], live["y"]) if live else (rec["x"], rec["y"])
        return idx, rec, pos

    def talk_to(self, target: str, policy: Policy | None = None) -> Event:
        """Walk next to an NPC (or across a counter from them), face them, press A."""
        policy = policy or Policy.fight()
        found = self.find_npc(target)
        if not found:
            return Event("no_such_npc", f"nobody matching {target!r} on this map", self.state())
        idx, rec, (nx, ny) = found
        s = self.state()
        m = self.world.by_id[s.map_id]
        here = self.node(s)
        # Candidate standing tiles: adjacent, or two away across a counter tile.
        candidates: list[tuple[Node, str]] = []
        for d, (dx, dy) in STEP.items():
            x1, y1 = nx + dx, ny + dy
            if m.walkable(x1, y1):
                candidates.append(((m.const, x1, y1), OPPOSITE[d]))
            elif 0 <= x1 < m.width and 0 <= y1 < m.height and m.grid[y1][x1] == "c":
                x2, y2 = nx + 2 * dx, ny + 2 * dy
                if m.walkable(x2, y2):
                    candidates.append(((m.const, x2, y2), OPPOSITE[d]))
        if not candidates:
            return Event("blocked", f"no tile to stand on next to {rec['sprite']} at ({nx},{ny})", s)
        # Don't path through other NPCs.
        self.world.temp_blocked = {(m.const, n["x"], n["y"]) for n in s.npcs}
        best = None
        for node, face in candidates:
            if node == here:
                best, route = (node, face), None
                break
            r = self.world.route_to_tile(here, node, policy)
            if r is not None and (best is None or len(r.presses) < len(route.presses)):
                best, route = (node, face), r
        self.world.temp_blocked = set()
        if best is None:
            return Event("blocked", f"can't reach a tile next to {rec['sprite']}", s)
        node, face = best
        if route is not None:
            ev = self._follow(route)
            if ev is not None:
                return ev
        # Face the NPC: a tap toward an occupied tile turns without stepping.
        for _ in range(3):
            if self.state().facing == face:
                break
            self.emu.press(face, hold_frames=2, settle_frames=12)
        self.emu.press("a", hold_frames=3, settle_frames=10)
        for _ in range(90):
            s = self.state()
            if s.text_box_open or s.menu is not None:
                return Event("text_opened", s.text or (" | ".join(s.menu.items) if s.menu else ""), s)
            self.emu.tick(1)
        return Event("no_response", f"pressed A facing {rec['sprite']} but no text appeared", self.state())

    def choose(self, option: str | int) -> Event:
        """Pick an option in the open menu by label ('yes', 'buy', 'poke ball') or index."""
        s = self.state()
        if s.menu is None:
            return Event("no_menu", "no menu is open", s)
        items = s.menu.items
        if isinstance(option, int) or str(option).isdigit():
            target = int(option)
        else:
            o = str(option).strip().lower()
            synonyms = {"no": ("no", "cancel", "quit", "exit"), "yes": ("yes", "heal", "ok", "buy"), "cancel": ("cancel", "no", "quit", "exit")}
            wanted = synonyms.get(o, (o,))
            target = next((i for w in wanted for i, it in enumerate(items) if it.lower() == w), None)
            if target is None:
                target = next((i for i, it in enumerate(items) if o in it.lower() or it.lower().startswith(o[:3])), None)
        if target is None or not (0 <= target < len(items)):
            return Event("no_such_option", f"{option!r} not in {items}", s)
        for _ in range(12):
            s = self.state()
            if s.menu is None:
                return Event("menu_closed", "menu closed while moving the cursor", s)
            if s.menu.cursor == target:
                break
            self.emu.press("down" if s.menu.cursor < target else "up", hold_frames=2, settle_frames=10)
        self.emu.press("a", hold_frames=3, settle_frames=30)
        s = self.state()
        return Event("chosen", f"{items[target]} -> " + (s.text or (" | ".join(s.menu.items) if s.menu else "menu closed")), s)

    def wait(self, seconds: float = 3.0) -> Event:
        """Let the game run until it hands control back (or a text box / menu / battle appears), then report."""
        frames = int(seconds * 60)
        for _ in range(frames):
            s = self.state()
            if s.battle is not None:
                return Event("encounter_started", f"{s.battle.kind} {s.battle.enemy_species} L{s.battle.enemy_level}", s)
            if s.menu is not None:
                return Event("choice_pending", " | ".join(s.menu.items), s)
            if s.text_box_open and s.text_waiting_for_a:
                return Event("text_opened", s.text, s)
            if not s.script_control and not s.moving and not s.text_box_open:
                return Event("ready", "you have the controls", s)
            self.emu.tick(1)
        s = self.state()
        return Event("still_busy", "the game still has the controls" if s.script_control else "a scene is still playing", s)

    def nearest_map(self, needle: str, policy: Policy | None = None) -> tuple[str, Route | None] | None:
        """The reachable map whose name contains needle (e.g. 'POKECENTER'), by route length."""
        policy = policy or Policy.fight()
        s = self.state()
        here = self.node(s)
        if needle in here[0]:
            return here[0], None
        best: tuple[str, Route] | None = None
        for const in self.world.maps:
            if needle not in const:
                continue
            r = self.world.route_to_map(here, const, policy)
            if r is not None and (best is None or len(r.presses) < len(best[1].presses)):
                best = (const, r)
        return best

    def go_and_settle(self, const: str, policy: Policy) -> Event | None:
        """Travel to a map; if a scene plays on arrival, step through it. None = we're there with control."""
        ev = self.travel(const, policy)
        for _ in range(6):
            if ev.kind == "arrived":
                return None
            if ev.kind == "text_opened" and self.node()[0] == const:
                ev2 = self.advance_text()
                if ev2.kind == "choice_pending":
                    self.choose(0)
                    self.advance_text()
                self.wait_for_control()
                ev = Event("arrived", const, self.state()) if self.node()[0] == const else self.travel(const, policy)
                continue
            return ev
        return ev

    def heal_at_center(self, policy: Policy | None = None) -> Event:
        """Go to the nearest Pokémon Center, talk to the nurse, HEAL, verify every party member is at full HP."""
        policy = policy or Policy.avoid_encounters()
        target = self.nearest_map("POKECENTER", policy)
        if target is None:
            return Event("no_route", "no Pokémon Center reachable from here", self.state())
        const, route = target
        if route is not None:
            ev = self.go_and_settle(const, policy)
            if ev is not None:
                return ev
        ev = self.talk_to("nurse")
        if ev.kind != "text_opened":
            return ev
        ev = self.advance_text()
        if ev.kind != "choice_pending":
            return Event("heal_failed", f"expected the HEAL/CANCEL choice, got {ev}", ev.state)
        ev = self.choose("heal")
        if ev.kind != "chosen":
            return ev
        for _ in range(10):  # the jingle and "fighting fit" text
            ev = self.advance_text()
            if ev.kind in ("text_closed", "text_still_open"):
                break
            if ev.kind == "choice_pending":
                self.choose(0)
        self.wait_for_control()
        s = self.state()
        full = all(m.hp == m.max_hp and m.status == 0 for m in s.party)
        return Event("healed" if full else "heal_failed", ", ".join(f"{m.species} {m.hp}/{m.max_hp}" for m in s.party), s)

    def _menu_abs_index(self) -> int | None:
        s = self.state()
        if s.menu is None:
            return None
        return s.menu.cursor + s.menu.scroll

    def select_list_item(self, abs_index: int, max_moves: int = 40) -> Event:
        """Move through a scrolling list (shop/bag) to absolute index and press A."""
        for _ in range(max_moves):
            cur = self._menu_abs_index()
            if cur is None:
                return Event("menu_closed", "list closed while scrolling", self.state())
            if cur == abs_index:
                self.emu.press("a", hold_frames=3, settle_frames=30)
                return Event("chosen", f"list item {abs_index}", self.state())
            self.emu.press("down" if cur < abs_index else "up", hold_frames=2, settle_frames=10)
        return Event("blocked", f"could not reach list item {abs_index}", self.state())

    def set_quantity(self, qty: int, max_presses: int = 99) -> int:
        """In a quantity prompt, press up/down until wItemQuantity == qty. Returns the quantity reached."""
        for _ in range(max_presses):
            cur = self.emu.read(R.wItemQuantity)
            if cur == qty:
                return cur
            self.emu.press("up" if cur < qty else "down", hold_frames=2, settle_frames=6)
        return self.emu.read(R.wItemQuantity)

    def shop(self, wanted: list[tuple[str, int]], policy: Policy | None = None) -> Event:
        """Buy a list of (ITEM_NAME, qty) at the nearest Mart. Verifies the bag afterwards."""
        policy = policy or Policy.avoid_encounters()
        target = self.nearest_map("MART", policy)
        if target is None:
            return Event("no_route", "no Mart reachable from here", self.state())
        const, route = target
        m = self.world.maps[const]
        inventories = getattr(m, "mart", None) or []
        if not inventories:
            return Event("no_shop", f"{m.name} has no clerk inventory in the data", self.state())
        stock = inventories[0]
        prices = self.world.prices
        money_before = self.state().money
        receipt, problems = [], []
        if route is not None:
            ev = self.go_and_settle(const, policy)
            if ev is not None:
                return ev
        ev = None
        said: list[str] = []
        for attempt in range(2):  # the first talk may be a one-time script (e.g. Viridian's parcel)
            ev = self.talk_to("clerk")
            if ev.kind != "text_opened":
                return ev
            if ev.detail:
                said.append(ev.detail)
            ev = self.advance_text()
            if ev.kind == "choice_pending":
                break
            if ev.detail:
                said.append(ev.detail)
            self.wait_for_control()
        if ev is None or ev.kind != "choice_pending":
            return Event("shop_unavailable", "the clerk didn't open the shop; they said: " + (" / ".join(said) or "(nothing readable)"), self.state())
        ev = self.choose("buy")
        for _ in range(120):  # "Take your time." then the item list draws
            if self.state().menu is not None:
                break
            self.emu.tick(1)
        for name, qty in wanted:
            key = name.upper().replace(" ", "_").replace("É", "E")
            if key not in stock:
                problems.append(f"{key} not stocked here (stock: {', '.join(stock)})")
                continue
            price = prices.get(key, 0) * qty
            if price > self.state().money:
                problems.append(f"can't afford {qty}x {key} ({price})")
                continue
            s = self.state()
            if s.menu is None:
                return Event("shop_failed", "the buy list is not open", s)
            ev = self.select_list_item(stock.index(key))
            if ev.kind != "chosen":
                return ev
            got = self.set_quantity(qty)
            self.emu.press("a", hold_frames=3, settle_frames=30)  # confirm quantity -> "That will be ¥X. OK?"
            ev = self.advance_text()
            if ev.kind == "choice_pending":
                self.choose("yes")
            ev = self.advance_text()  # "Here you are! Thank you!" -> back to the list
            receipt.append(f"{got}x {key}")
            for _ in range(120):
                if self.state().menu is not None:
                    break
                self.emu.tick(1)
        # Back out: list -> BUY/SELL/QUIT -> QUIT -> "Thank you!"
        for _ in range(3):
            s = self.state()
            if s.menu is None and not s.text_box_open:
                break
            self.emu.press("b", hold_frames=3, settle_frames=30)
            s = self.state()
            if s.menu is not None and any(it.upper() == "QUIT" for it in s.menu.items):
                self.choose("quit")
                self.advance_text()
                break
        self.advance_text()
        self.wait_for_control()
        s = self.state()
        spent = money_before - s.money
        detail = f"bought {', '.join(receipt) or 'nothing'} for ${spent}; bag: {', '.join(f'{n}x{q}' for n, q in s.bag) or 'empty'}"
        if problems:
            detail += "; " + "; ".join(problems)
        return Event("bought" if receipt else "shop_failed", detail, s)

    def advance_text(self, max_presses: int = 30) -> Event:
        """Press A through dialogue until the box closes or a choice is pending (a menu is open)."""
        seen: list[str] = []
        for _ in range(max_presses):
            s = self.state()
            if s.menu is not None:
                return Event("choice_pending", " | ".join(s.menu.items), s)
            if not s.text_box_open:
                return Event("text_closed", " / ".join(seen), s)
            if s.battle:
                return Event("encounter_started", "", s)
            if s.text and s.text_waiting_for_a and (not seen or seen[-1] != s.text):
                seen.append(s.text)
            self.emu.press("a", hold_frames=2, settle_frames=20)
        return Event("text_still_open", self.state().text, self.state())


def _guarded(name: str):
    """Decorator: run a verb under the frame budget; a timeout becomes an Event instead of a hang."""
    def deco(fn):
        def wrapper(self: "Pilot", *a, **kw):
            outer = self._begin_verb(name)
            args = ", ".join([repr(x) for x in a] + [f"{k}={v!r}" for k, v in kw.items()])
            self.log(f"[pilot] {'' if outer else '  '}{name}({args[:80]})")
            try:
                ev = fn(self, *a, **kw)
                self.log(f"[pilot] {'' if outer else '  '}{name} -> {ev}")
                return ev
            except PilotTimeout as e:
                self.log(f"[pilot] TIMEOUT: {e}")
                for b in ("up", "down", "left", "right", "a", "b"):
                    self.emu.release(b)
                return Event("timeout", str(e), extract(self.emu))
            finally:
                self._end_verb(outer)
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return deco


for _name in ("travel", "talk_to", "choose", "advance_text", "heal_at_center", "shop", "select_list_item", "wait"):
    setattr(Pilot, _name, _guarded(_name)(getattr(Pilot, _name)))


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
