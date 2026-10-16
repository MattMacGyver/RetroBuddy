"""RAM -> GameState. Pure reads; never presses a button."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import ram_map as R
from .emu import Emu


@dataclass
class Mon:
    slot: int
    species_id: int
    species: str
    nickname: str
    level: int
    hp: int
    max_hp: int
    status: int
    moves: list[str]
    pp: list[int]


@dataclass
class Battle:
    kind: str  # "wild" | "trainer" | "lost"
    enemy_species: str
    enemy_level: int
    enemy_hp: int
    enemy_max_hp: int
    active_slot: int
    active_hp: int
    active_max_hp: int


@dataclass
class Menu:
    cursor: int
    items: list[str]
    x: int
    y: int
    scroll: int = 0


@dataclass
class GameState:
    map_id: int
    map_name: str
    x: int
    y: int
    facing: str
    map_width_tiles: int
    map_height_tiles: int
    moving: bool
    script_control: bool
    player_name: str
    money: int
    badges: list[str]
    party: list[Mon]
    bag: list[tuple[str, int]]
    warps: list[dict[str, Any]]
    npcs: list[dict[str, Any]]
    text_box_open: bool
    text_waiting_for_a: bool
    text: str
    battle: Battle | None = None
    menu: Menu | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bcd(bs: bytes) -> int:
    n = 0
    for b in bs:
        n = n * 100 + (b >> 4) * 10 + (b & 0xF)
    return n


def read_party(emu: Emu) -> list[Mon]:
    out = []
    for i, p in enumerate(emu.game.party):
        out.append(
            Mon(
                slot=i,
                species_id=p["species"],
                species=R.SPECIES_NAMES.get(p["species"], f"#{p['species']}"),
                nickname=R.decode_text(p["nickname"]),
                level=p["level"],
                hp=p["hp"],
                max_hp=p["max_hp"],
                status=p["status"],
                moves=[R.MOVE_ID_TO_NAME.get(m, f"#{m}") for m in p["moves"] if m],
                pp=[pp for m, pp in zip(p["moves"], p["pp"]) if m],
            )
        )
    return out


def read_bag(emu: Emu) -> list[tuple[str, int]]:
    n = emu.read(R.wNumBagItems)
    raw = emu.read_block(R.wBagItems, 2 * min(n, 20))
    return [(R.ITEM_ID_TO_NAME.get(raw[i], f"#{raw[i]}"), raw[i + 1]) for i in range(0, len(raw), 2)]


def read_warps(emu: Emu) -> list[dict[str, Any]]:
    n = min(emu.read(R.wNumWarps), 32)
    raw = emu.read_block(R.wWarpEntries, n * R.WARP_ENTRY_SIZE)
    out = []
    for i in range(n):
        y, x, dest_warp, dest_map = raw[i * 4 : i * 4 + 4]
        name = "last_outdoor_map" if dest_map == 0xFF else R.MAP_ID_TO_NAME.get(dest_map, f"map#{dest_map}")
        out.append({"x": x, "y": y, "dest_map": dest_map, "dest_map_name": name, "dest_warp": dest_warp})
    return out


def read_npcs(emu: Emu) -> list[dict[str, Any]]:
    n = min(emu.read(R.wNumSprites), 15)
    out = []
    for s in range(1, n + 1):
        pic = emu.read(R.wSpriteStateData1 + s * 16)
        if pic == 0:
            continue
        y = emu.read(R.wSpriteStateData2 + s * 16 + 4) - 4
        x = emu.read(R.wSpriteStateData2 + s * 16 + 5) - 4
        out.append({"sprite": s, "picture_id": pic, "x": x, "y": y})
    return out


def read_text(emu: Emu) -> tuple[bool, bool, str]:
    tiles = emu.read_block(R.wTileMap, R.SCREEN_W * R.SCREEN_H)
    row = lambda r: tiles[r * R.SCREEN_W : (r + 1) * R.SCREEN_W]
    # A text box draws its top border on row 12 (0x79 corner / 0x7A edge).
    top = row(R.TEXT_BOX_TOP_ROW)
    box_open = top[0] == 0x79 and top[1] == 0x7A
    waiting = row(16)[18] == R.TILE_TEXT_ARROW
    lines = [R.decode_text(row(r)).strip() for r in R.TEXT_BOX_ROWS] if box_open else []
    return box_open, waiting, " / ".join(l for l in lines if l)


def read_menu(emu: Emu) -> Menu | None:
    """A menu is open when the game's cursor glyph sits where the menu variables say it should."""
    y0 = emu.read(R.wTopMenuItemY)
    x0 = emu.read(R.wTopMenuItemX)
    cur = emu.read(R.wCurrentMenuItem)
    mx = emu.read(R.wMaxMenuItem)
    if not (0 <= x0 < R.SCREEN_W and 0 <= y0 < R.SCREEN_H and cur <= mx <= 15):
        return None
    tiles = emu.read_block(R.wTileMap, R.SCREEN_W * R.SCREEN_H)
    cy = y0 + cur * R.MENU_ROW_SPACING
    if cy >= R.SCREEN_H or tiles[cy * R.SCREEN_W + x0] != R.TILE_CURSOR:
        return None
    items = []
    for i in range(mx + 1):
        ry = y0 + i * R.MENU_ROW_SPACING
        if ry >= R.SCREEN_H:
            break
        row = tiles[ry * R.SCREEN_W + x0 + 1 : (ry + 1) * R.SCREEN_W]
        label = R.decode_text(row).strip()
        # the label ends at the box's right border (0x7B) or a run of spaces
        label = label.split("  ")[0].strip()
        items.append(label)
    while items and not items[-1]:
        items.pop()
    if not items:
        return None
    return Menu(cursor=cur, items=items, x=x0, y=y0, scroll=emu.read(R.wListScrollOffset))


def read_battle(emu: Emu) -> Battle | None:
    kind_code = emu.read(R.wIsInBattle)
    if kind_code == 0:
        return None
    kind = {1: "wild", 2: "trainer", 0xFF: "lost"}.get(kind_code, f"#{kind_code}")
    sp = emu.read(R.wEnemyMonSpecies)
    return Battle(
        kind=kind,
        enemy_species=R.SPECIES_NAMES.get(sp, f"#{sp}"),
        enemy_level=emu.read(R.wEnemyMonLevel),
        enemy_hp=emu.read_u16_be(R.wEnemyMonHP),
        enemy_max_hp=emu.read_u16_be(R.wEnemyMonMaxHP),
        active_slot=emu.read(R.wPlayerMonNumber),
        active_hp=emu.read_u16_be(R.wBattleMonHP),
        active_max_hp=emu.read_u16_be(R.wBattleMonMaxHP),
    )


def extract(emu: Emu) -> GameState:
    map_id = emu.read(R.wCurMap)
    badges_mask = emu.read(R.wObtainedBadges)
    box_open, waiting, text = read_text(emu)
    return GameState(
        map_id=map_id,
        map_name=R.MAP_ID_TO_NAME.get(map_id, f"map#{map_id}"),
        x=emu.read(R.wXCoord),
        y=emu.read(R.wYCoord),
        facing=R.SPRITE_FACING.get(emu.read(R.wSpriteStateData1 + 9), "?"),
        map_width_tiles=emu.read(R.wCurMapWidth) * 2,
        map_height_tiles=emu.read(R.wCurMapHeight) * 2,
        moving=emu.read(R.wWalkCounter) != 0,
        script_control=emu.read(R.wJoyIgnore) != 0,
        player_name=R.decode_text(emu.read_block(R.wPlayerName, 11)),
        money=_bcd(emu.read_block(R.wPlayerMoney, 3)),
        badges=[R.BADGE_BIT_TO_NAME[b] for b in range(8) if badges_mask & (1 << b)],
        party=read_party(emu),
        bag=read_bag(emu),
        warps=read_warps(emu),
        npcs=read_npcs(emu),
        text_box_open=box_open,
        text_waiting_for_a=waiting,
        text=text,
        battle=read_battle(emu),
        menu=read_menu(emu),
    )


def summary(s: GameState) -> str:
    """One-screen human summary, the shape the companion will eventually see."""
    lines = [
        f"{s.map_name} ({s.map_id}) at x={s.x} y={s.y} facing {s.facing}; map {s.map_width_tiles}x{s.map_height_tiles} tiles",
        f"player {s.player_name!r}  money ${s.money}  badges {s.badges or 'none'}",
        f"moving={s.moving} script_control={s.script_control} text_box={s.text_box_open} waiting_for_A={s.text_waiting_for_a}",
    ]
    if s.text:
        lines.append(f"text: {s.text}")
    lines.append("party: " + (", ".join(f"{m.species} L{m.level} {m.hp}/{m.max_hp} [{' '.join(m.moves)}]" for m in s.party) or "empty"))
    lines.append("bag: " + (", ".join(f"{n}x{q}" for n, q in s.bag) or "empty"))
    lines.append("warps: " + ", ".join(f"({w['x']},{w['y']})->{w['dest_map_name']}" for w in s.warps))
    lines.append("npcs: " + (", ".join(f"#{n['sprite']}@({n['x']},{n['y']})" for n in s.npcs) or "none"))
    if s.menu:
        m = s.menu
        lines.append("MENU open: " + " | ".join(f"{'>' if i == m.cursor else ' '}{it}" for i, it in enumerate(m.items)))
    if s.battle:
        b = s.battle
        lines.append(f"BATTLE {b.kind}: enemy {b.enemy_species} L{b.enemy_level} {b.enemy_hp}/{b.enemy_max_hp}; ours slot {b.active_slot} {b.active_hp}/{b.active_max_hp}")
    return "\n".join(lines)
