"""Paths and settings shared by every module. Nothing here touches the emulator."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ROM_DIR = ROOT / "ROMs"
SAVE_DIR = ROOT / "saves"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"

RED_ROM = ROM_DIR / "Pokemon - Red Version.gb"
START_STATE = SAVE_DIR / "red_start.state"

load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model routing (see App Bible D16). Names are checked at build time against docs.
TIER2_MODEL = os.environ.get("RETROBUDDY_TIER2_MODEL", "claude-sonnet-5-5")


def ensure_dirs() -> None:
    for d in (SAVE_DIR, DATA_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
