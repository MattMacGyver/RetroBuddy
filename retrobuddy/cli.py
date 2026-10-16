"""Text chat loop: type to the companion; the emulator window stays live while you aren't.

    python -m retrobuddy.cli [--state saves/dev_starter.state] [--speed 1] [--headless]

Threads: the main thread owns the emulator (ticks it, runs pilot verbs). A reader thread takes
typed lines. A turn thread talks to the model; when the model calls a tool, the verb is handed to
the main thread and the turn thread waits for the result. So the game never freezes for an API
call, and only one thread ever touches the emulator.

Commands: /quit, /state (print the raw state), /save <name> (save state to saves/<name>.state).
Emulator keys: arrows, A = A, S = B, Enter = Start, Backspace = Select. Avoid Z/X (snapshot
save/load), Space (turbo), Escape (quits the emulator).
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from . import config
from .companion import Companion
from .emu import Emu
from .extractor import extract, summary
from .pilot import Pilot
from .world import World

KEYS = "Emulator keys: arrows move, A = A button, S = B button, Enter = Start, Backspace = Select.  Do NOT press Z or X (snapshot save/load), Space (turbo) or Esc (quits)."


def _reader(q: "queue.Queue[str]") -> None:
    for line in sys.stdin:
        q.put(line.rstrip("\n"))
    q.put("/quit")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", type=Path, default=config.START_STATE)
    ap.add_argument("--speed", type=int, default=1)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    config.ensure_dirs()
    if not config.ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY missing: put it in .env", file=sys.stderr)
        return 2

    logf = open(config.LOG_DIR / "session.log", "a", encoding="utf-8")
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock:
            print(msg, flush=True)
            logf.write(msg + "\n")
            logf.flush()

    verb_q: "queue.Queue[tuple[Callable[[], Any], Future]]" = queue.Queue()

    def execute(fn: Callable[[], Any]) -> Any:
        """Called from the turn thread: run fn on the emulator thread and wait."""
        if threading.current_thread() is threading.main_thread():
            return fn()
        fut: Future = Future()
        verb_q.put((fn, fut))
        return fut.result()

    world = World()
    with Emu(window="null" if args.headless else "SDL2", speed=args.speed) as emu:
        emu.load_state(args.state)
        emu.tick(30)
        pilot = Pilot(emu, world, log=log)
        buddy = Companion(pilot, log=log, execute=execute)
        log(f"=== RetroBuddy session {time.strftime('%Y-%m-%d %H:%M')} model={buddy.model} state={args.state.name} ===")
        log(summary(extract(emu)))
        log("\n" + KEYS)
        log("Type to RetroBuddy. /quit (or /exit) to end, /state to dump state, /save <name> to save a state.\n")

        lines: "queue.Queue[str]" = queue.Queue()
        threading.Thread(target=_reader, args=(lines,), daemon=True).start()

        turn: threading.Thread | None = None
        pending_lines: list[str] = []
        last = extract(emu)
        quiet_after_battle = 0
        frames = 0
        running = True

        def start_turn(text: str, kind: str = "user") -> None:
            nonlocal turn
            turn = threading.Thread(target=buddy.turn, args=(text, kind), daemon=True)
            turn.start()

        while running:
            # 1. Verbs requested by the turn thread run here, on the emulator thread.
            try:
                fn, fut = verb_q.get_nowait()
            except queue.Empty:
                pass
            else:
                try:
                    fut.set_result(fn())
                except Exception as e:  # noqa: BLE001
                    fut.set_exception(e)
                continue

            # 2. Typed lines.
            try:
                line = lines.get_nowait()
            except queue.Empty:
                line = None
            if line is not None:
                cmd = line.strip()
                if cmd in ("/quit", "/exit", "/q"):
                    running = False
                    continue
                if cmd == "/state":
                    log(summary(extract(emu)))
                    continue
                if cmd.startswith("/save "):
                    p = config.SAVE_DIR / f"{cmd.split(None, 1)[1].strip()}.state"
                    emu.save_state(p)
                    log(f"saved {p}")
                    continue
                if cmd:
                    pending_lines.append(cmd)

            busy = turn is not None and turn.is_alive()
            if not busy and pending_lines:
                start_turn(pending_lines.pop(0))
                last = extract(emu)
                continue

            # 3. Keep the game running; watch for things worth telling the companion when idle.
            if not emu.tick(1):
                break
            frames += 1
            if busy or frames % 30:
                continue
            s = extract(emu)
            if last.battle and not s.battle:
                quiet_after_battle = 1
            elif quiet_after_battle:
                quiet_after_battle += 1
                if not s.script_control and not s.text_box_open and quiet_after_battle >= 4:  # ~2 s settled
                    quiet_after_battle = 0
                    start_turn("the battle Matt fought by hand just ended", kind="event")
            elif last.map_id != s.map_id and not s.battle and not s.script_control:
                start_turn(f"Matt walked from {last.map_name} to {s.map_name} by hand", kind="event")
            last = s

        if turn is not None and turn.is_alive():
            log("(waiting for the companion to finish its sentence)")
            while turn.is_alive():
                try:
                    fn, fut = verb_q.get(timeout=0.1)
                    fut.set_result(fn())
                except queue.Empty:
                    pass
    logf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
