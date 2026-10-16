# RetroBuddy

A voice-first companion that plays classic Pokémon on your behalf, narrates it, and talks through the decisions with you. Personal project; self-hosted; bring your own ROM and API keys.

**This repository contains no ROMs, saves, sprites, maps, audio, or other Nintendo / Game Freak material**, and never will. It reads a ROM you dump from a cartridge you own, placed in `ROMs/` (gitignored).

## Status

Step 1 of the roadmap: text-only loop proof on Pokémon Red. See the App Bible and Build Log (private docs) for design and progress.

## Layout

```
ROMs/        your ROM(s) — gitignored
saves/       emulator save states — gitignored
data/        generated JSON (maps, warps, tile flags) built from pret/pokered by tools/build_data.py
retrobuddy/  the package: emu, extractor, world, pilot, companion, cli
tools/       one-off scripts: make_savestate.py, build_data.py
scripts/     Windows batch files that run checks and write to logs/
logs/        output of scripts — gitignored
.env         ANTHROPIC_API_KEY=... — gitignored
```

## Setup (Windows)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Put `Pokemon - Red Version.gb` in `ROMs/` and your key in `.env`.

## Architecture in one line

Extractor reads emulator RAM → Pilot (plain code) paths, presses buttons, raises events → Companion (LLM) holds goals, talks, issues pilot verbs. The model never presses a button.
