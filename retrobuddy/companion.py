"""The companion: holds goals and the conversation, sees the state, calls pilot verbs as tools.

It never presses a button. Everything it can do to the game is a tool here, and every tool
is a pilot verb.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from . import config
from .extractor import GameState, summary
from .pilot import Event, Pilot
from .world import Policy

PERSONA = """You are RetroBuddy, a knowledgeable, good-humored partner playing Pokémon Red with Matt.
Matt usually can't see the screen, so describe what's happening the way you would for someone who is
blind: where we are, who's around, what just happened, what's at stake. Keep it short — a few
sentences, not paragraphs. You have opinions and you share them, but decisions are Matt's.
You control the game only through the tools you're given; you cannot press buttons directly.
Battles are not yet in your tools: when a wild encounter stops a walk, say what jumped us and that
Matt has to fight it by hand for now. The emulator keyboard is: arrow keys to move, A = the A button,
S = the B button, Enter = Start, Backspace = Select. Never tell Matt to press Z or X (they save and
load emulator snapshots) or Space or Escape.
When a game script takes over (a text box opens on its own), tell Matt what the game is doing rather
than treating it as an error. If a walk fails because the game still has the controls, wait for Matt
to say the screen has settled instead of retrying the same tool repeatedly.
Discovery is Matt's: do not volunteer story objectives, where items are, or what the game wants next
(no "Oak's Parcel is at the Mart") unless he asks, or he has been stuck on the same thing for a while.
Answer direct questions directly. Your travel tool goes to places (towns, routes, buildings), not to
people or counters; there is no talk-to or heal tool yet.
Never invent game mechanics, levels, or move data; use only what the state tells you."""

TOOLS = [
    {
        "name": "travel",
        "description": "Walk to a named place (a town, route, or building, e.g. 'Viridian City', 'Oaks Lab', 'Viridian Pokemon Center'). The pilot plans the route and walks it. Returns the event that ended the walk: arrived, encounter_started, text_opened, blocked, or no_route.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Where to go, in plain words."},
                "policy": {"type": "string", "enum": ["fight", "avoid", "hunt"], "description": "fight = shortest path (default); avoid = route around grass and trainer sightlines where possible; hunt = prefer grass."},
            },
            "required": ["destination"],
        },
    },
    {
        "name": "advance_text",
        "description": "Press A through the dialogue currently on screen until the text box closes or a choice appears. Use when a text box is open.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


@dataclass
class Companion:
    pilot: Pilot
    model: str = config.TIER2_MODEL
    persona: str = PERSONA
    log: Callable[[str], None] = print
    history: list[dict[str, Any]] = field(default_factory=list)
    client: anthropic.Anthropic = field(default_factory=lambda: anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY))
    # Runs a pilot verb. The CLI replaces this with "run it on the emulator thread and wait" so the
    # model's API calls can happen off-thread without two threads touching the emulator.
    execute: Callable[[Callable[[], Any]], Any] = lambda fn: fn()

    # --- state the model sees ---------------------------------------------

    def _state_block(self) -> str:
        s = self.pilot.state()
        return "<game_state>\n" + summary(s) + "\n</game_state>"

    def _system(self) -> str:
        return self.persona + "\n\nThe current game state is given at the start of each user turn and after each tool call."

    # --- tools ---------------------------------------------------------------

    def _run_tool(self, name: str, args: dict) -> str:
        if name == "travel":
            pol = {"fight": Policy.fight, "avoid": Policy.avoid_encounters, "hunt": Policy.hunt}[args.get("policy", "fight")]()
            ev = self.execute(lambda: self.pilot.travel(args["destination"], pol))
        elif name == "advance_text":
            ev = self.execute(lambda: self.pilot.advance_text())
        else:
            return f"unknown tool {name}"
        self.log(f"[event] {ev}")
        return f"{ev}\n\n{self.execute(self._state_block)}"

    # --- a turn --------------------------------------------------------------

    def turn(self, text: str, kind: str = "user") -> str:
        """kind: 'user' for something Matt said, 'event' for something the game did."""
        state_block = self.execute(self._state_block)
        if kind == "event":
            content = f"[game event] {text}\n\n{state_block}"
        else:
            content = f"{state_block}\n\nMatt: {text}"
        self.history.append({"role": "user", "content": content})
        final_text = []
        for _ in range(8):  # tool-call rounds per turn
            resp = self.client.messages.create(
                model=self.model, max_tokens=600, system=self._system(), tools=TOOLS, messages=self.history
            )
            self.history.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            for b in resp.content:
                if b.type == "text" and b.text.strip():
                    final_text.append(b.text.strip())
                    self.log(f"\nRetroBuddy: {b.text.strip()}\n")
            if not tool_uses:
                break
            results = []
            for tu in tool_uses:
                self.log(f"[tool] {tu.name}({json.dumps(tu.input)})")
                out = self._run_tool(tu.name, tu.input)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
            self.history.append({"role": "user", "content": results})
        return "\n".join(final_text)
