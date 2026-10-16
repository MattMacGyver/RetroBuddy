"""RetroBuddy — AI companion that plays classic Pokémon with you.

Layers:
  emu        PyBoy wrapper (ROM + save state, frames, buttons, memory)
  extractor  RAM -> GameState
  world      map graph, warp graph, A*
  pilot      verbs + watchers; the only thing that presses buttons
  companion  the model: goals, conversation, verb calls
  cli        text chat loop
"""

__version__ = "0.1.0"
