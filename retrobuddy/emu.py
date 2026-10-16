"""PyBoy wrapper: the only module that talks to the emulator directly.

Everything above this (extractor, pilot) calls these methods and never touches
PyBoy itself, so swapping emulators later (mGBA for Gen 3) means replacing one file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pyboy import PyBoy

from . import config

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")


class Emu:
    """A running Game Boy with the ROM loaded.

    window: "null" = headless (no window, fastest), "SDL2" = visible window.
    speed:  0 = as fast as possible, 1 = real time, N = N× real time.
    """

    def __init__(self, rom: Path = config.RED_ROM, window: str = "null", speed: int = 0, scale: int = 3):
        if not rom.exists():
            raise FileNotFoundError(f"ROM not found: {rom}")
        self.rom = rom
        self.pyboy = PyBoy(str(rom), window=window, scale=scale, sound_emulated=False, log_level="WARNING")
        self.pyboy.set_emulation_speed(speed)

    # --- lifecycle -------------------------------------------------------

    @property
    def game(self):
        """PyBoy's built-in Pokémon Gen 1 wrapper (party, text tables, start_game, --dev helpers)."""
        return self.pyboy.game_wrapper

    def stop(self) -> None:
        self.pyboy.stop(save=False)

    def __enter__(self) -> "Emu":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # --- time ------------------------------------------------------------

    def tick(self, frames: int = 1, render: bool = False) -> bool:
        """Advance the emulator. Returns False if the emulator has stopped."""
        return self.pyboy.tick(frames, render)

    # --- input -----------------------------------------------------------

    def press(self, button: str, hold_frames: int = 1, settle_frames: int = 0) -> None:
        """Press a button for hold_frames, then optionally let settle_frames pass."""
        if button not in BUTTONS:
            raise ValueError(f"unknown button {button!r}; expected one of {BUTTONS}")
        self.pyboy.button(button, hold_frames)
        self.tick(hold_frames + 1)
        if settle_frames:
            self.tick(settle_frames)

    # --- memory ----------------------------------------------------------

    def read(self, addr: int) -> int:
        return self.pyboy.memory[addr]

    def read_u16_be(self, addr: int) -> int:
        """Big-endian 16-bit read (how pokered stores HP, stats, etc.)."""
        return (self.pyboy.memory[addr] << 8) | self.pyboy.memory[addr + 1]

    def read_block(self, addr: int, length: int) -> bytes:
        return bytes(self.pyboy.memory[addr : addr + length])

    def read_many(self, addrs: Iterable[int]) -> list[int]:
        return [self.pyboy.memory[a] for a in addrs]

    # --- save states -----------------------------------------------------

    def save_state(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            self.pyboy.save_state(f)

    def load_state(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"save state not found: {path} (run tools/make_savestate.py)")
        with open(path, "rb") as f:
            self.pyboy.load_state(f)
