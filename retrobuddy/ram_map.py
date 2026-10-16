"""Pokémon Red (Gen 1) RAM addresses, each with its pret/pokered symbol name.

Sources: PyBoy's game_wrapper_pokemon_gen1_constants (imported, not copied) for what it
covers; the remaining symbols are from pokered's wram.asm as used by the open-source Red
bots. Every address here is verified empirically by tools/dump_state.py (step 3 check):
if a value doesn't track reality, the address is wrong for this ROM, not the game.
"""

from __future__ import annotations

from pyboy.plugins import game_wrapper_pokemon_gen1_constants as C

# --- lookup tables (from PyBoy) -------------------------------------------
MAP_ID_TO_NAME = {v: k for k, v in C.MAPS.items()}
SPECIES_NAMES = C.POKEMON_SPECIES_NAMES  # internal id -> name
MOVE_ID_TO_NAME = {v: k for k, v in C.POKEMON_MOVES.items()}
ITEM_ID_TO_NAME = {v: k for k, v in C.ITEMS.items()}
BADGE_BIT_TO_NAME = {v: k for k, v in C.BADGES.items()}
TEXT_DECODE = C.POKEMON_TEXT_DECODING  # byte -> str
TRAINER_CLASS_NAMES = C.TRAINER_CLASS_NAMES

# --- overworld ------------------------------------------------------------
wCurMap = 0xD35E
wYCoord = 0xD361
wXCoord = 0xD362
wCurMapHeight = 0xD368  # in blocks (1 block = 2x2 tiles)
wCurMapWidth = 0xD369
wNumWarps = 0xD3AE
wWarpEntries = 0xD3AF  # 4 bytes each: y, x, destination warp id, destination map
WARP_ENTRY_SIZE = 4
wNumSprites = 0xD4E1
# Sprite state: 16 sprites x 16 bytes, sprite 0 = player.
wSpriteStateData1 = 0xC100  # +0 picture id, +1 movement status, +9 facing (0 down, 4 up, 8 left, C right)
wSpriteStateData2 = 0xC200  # +4 map y + 4, +5 map x + 4
SPRITE_FACING = {0x0: "down", 0x4: "up", 0x8: "left", 0xC: "right"}
wWalkCounter = 0xCFC5  # non-zero while a step animation is in progress
wJoyIgnore = 0xCD6B  # non-zero while a script has taken the controls

# --- player ---------------------------------------------------------------
wPlayerName = C.PLAYER_NAME_ADDRESS
wPlayerMoney = C.PLAYER_MONEY_ADDRESS  # 3 bytes BCD
wObtainedBadges = C.OBTAINED_BADGES_ADDRESS
wNumBagItems = C.BAG_ITEM_COUNT_ADDRESS
wBagItems = C.BAG_ITEMS_ADDRESS  # pairs (item id, qty), terminated by 0xFF
wPartyCount = C.PARTY_COUNT_ADDRESS

# --- battle ---------------------------------------------------------------
wIsInBattle = 0xD057  # 0 none, 1 wild, 2 trainer, 0xFF lost
wCurOpponent = C.CURRENT_OPPONENT_ADDRESS  # species id (wild) or trainer class + 200
wEnemyMonSpecies = 0xCFE5
wEnemyMonHP = 0xCFE6  # 2 bytes
wEnemyMonLevel = 0xCFF3
wEnemyMonMaxHP = 0xCFF4  # 2 bytes
wBattleMonHP = 0xD015  # 2 bytes, the player's active mon
wBattleMonMaxHP = 0xD023  # 2 bytes
wPlayerMonNumber = 0xCC2F  # party index of the active mon

# --- screen ---------------------------------------------------------------
wTileMap = 0xC3A0  # 20 x 18 tile ids; text glyphs share ids with pokered's charmap
SCREEN_W, SCREEN_H = 20, 18
TEXT_BOX_ROWS = (14, 16)  # the two text lines inside a standard bottom text box
TEXT_BOX_TOP_ROW = 12
TILE_TEXT_ARROW = 0xEE  # blinking "▼" when text is waiting for A


def decode_text(raw: bytes | list[int]) -> str:
    out = []
    for b in raw:
        if b == 0x50:  # "@" terminator
            break
        ch = TEXT_DECODE.get(b)
        if ch is None or (ch.startswith("<") and ch.endswith(">")):
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)
