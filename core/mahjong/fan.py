from collections import Counter
from dataclasses import dataclass

from core.mahjong.game_state import GameState
from core.mahjong.player import Meld, PlayerState
from core.mahjong.tile import Tile

FAN_MENQING = "menqing"
FAN_QINGYISE = "qingyise"
FAN_PENGPENGHU = "pengpenghu"
FAN_QIDUI = "qidui"

FAN_LABELS = {
    FAN_MENQING: "门前清",
    FAN_QINGYISE: "清一色",
    FAN_PENGPENGHU: "碰碰胡",
    FAN_QIDUI: "七小对",
}
FAN_MULTIPLIERS = {
    FAN_MENQING: 2,
    FAN_QINGYISE: 2,
    FAN_PENGPENGHU: 2,
    FAN_QIDUI: 4,
}

OPEN_MELD_TYPES = {"chi", "peng", "exposed_gang", "added_gang"}
TRIPLET_MELD_TYPES = {"peng", "concealed_gang", "exposed_gang", "added_gang"}


@dataclass(frozen=True, slots=True)
class FanResult:
    fans: list[str]
    multiplier: int


def detect_fans(
    state: GameState,
    player_id: str,
    win_type: str,
    winning_tile: Tile | None,
) -> FanResult:
    if player_id not in state.players:
        raise ValueError("玩家不存在")

    player = state.players[player_id]
    fans: list[str] = []
    qidui = is_qidui(player, winning_tile)
    if qidui:
        fans.append(FAN_QIDUI)
    elif is_menqing(player):
        fans.append(FAN_MENQING)

    if is_qingyise(player, winning_tile):
        fans.append(FAN_QINGYISE)
    if not qidui and is_pengpenghu(player, winning_tile):
        fans.append(FAN_PENGPENGHU)
    return FanResult(fans=fans, multiplier=calculate_fan_multiplier(fans))


def is_menqing(player: PlayerState) -> bool:
    return all(meld.type not in OPEN_MELD_TYPES for meld in player.melds)


def is_qingyise(player: PlayerState, winning_tile: Tile | None) -> bool:
    tiles = _owned_tiles(player, winning_tile)
    if not tiles:
        return False
    suits = {tile.suit for tile in tiles}
    return len(suits) == 1


def is_pengpenghu(player: PlayerState, winning_tile: Tile | None) -> bool:
    if is_qidui(player, winning_tile):
        return False
    if any(meld.type == "chi" for meld in player.melds):
        return False
    if any(not _is_triplet_like_meld(meld) for meld in player.melds):
        return False

    concealed_tiles = list(player.hand)
    if winning_tile is not None:
        concealed_tiles.append(winning_tile)

    required_triplet_count = 4 - len(player.melds)
    if required_triplet_count < 0:
        return False
    if len(concealed_tiles) != required_triplet_count * 3 + 2:
        return False

    pair_count = 0
    for count in Counter(concealed_tiles).values():
        remainder = count % 3
        if remainder == 0:
            continue
        if remainder == 2:
            pair_count += 1
            continue
        return False
    return pair_count == 1


def is_qidui(player: PlayerState, winning_tile: Tile | None) -> bool:
    if player.melds:
        return False
    return is_qidui_hand(_complete_concealed_hand(player, winning_tile))


def is_qidui_hand(hand: list[Tile]) -> bool:
    if len(hand) != 14:
        return False
    counts = Counter(hand)
    pair_count = 0
    for count in counts.values():
        if count == 2:
            pair_count += 1
        elif count == 4:
            pair_count += 2
        else:
            return False
    return pair_count == 7


def calculate_fan_multiplier(fans: list[str]) -> int:
    multiplier = 1
    for fan in fans:
        multiplier *= FAN_MULTIPLIERS.get(fan, 1)
    return multiplier


def fan_labels(fans: list[str]) -> list[str]:
    return [FAN_LABELS.get(fan, fan) for fan in fans]


def _owned_tiles(player: PlayerState, winning_tile: Tile | None) -> list[Tile]:
    tiles = list(player.hand)
    if winning_tile is not None:
        tiles.append(winning_tile)
    for meld in player.melds:
        tiles.extend(meld.tiles)
    return tiles


def _complete_concealed_hand(player: PlayerState, winning_tile: Tile | None) -> list[Tile]:
    tiles = list(player.hand)
    if winning_tile is not None:
        tiles.append(winning_tile)
    return tiles


def _is_triplet_like_meld(meld: Meld) -> bool:
    return (
        meld.type in TRIPLET_MELD_TYPES
        and len(meld.tiles) in {3, 4}
        and len(set(meld.tiles)) == 1
    )
