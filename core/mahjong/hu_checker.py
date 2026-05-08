from collections import Counter

from core.mahjong.player import Meld
from core.mahjong.tile import Tile


def can_hu(hand: list[Tile]) -> bool:
    return can_hu_standard(hand) or can_hu_qidui(hand)


def can_hu_with_melds(hand: list[Tile], melds: list[Meld]) -> bool:
    if not melds and can_hu_qidui(hand):
        return True
    return can_hu_standard_with_melds(hand, melds)


def can_hu_standard(hand: list[Tile]) -> bool:
    return can_hu_standard_with_melds(hand, [])


def can_hu_standard_with_melds(hand: list[Tile], melds: list[Meld]) -> bool:
    meld_count = len(melds)
    if meld_count > 4:
        return False
    expected_hand_count = 14 - meld_count * 3
    if len(hand) != expected_hand_count:
        return False
    if not _melds_are_valid(melds):
        return False

    counts = Counter([*hand, *(tile for meld in melds for tile in meld.tiles)])
    if any(count > 4 for count in counts.values()):
        return False

    hand_counts = Counter(hand)
    for pair_tile, count in hand_counts.items():
        if count < 2:
            continue

        remaining = hand_counts.copy()
        remaining[pair_tile] -= 2
        if remaining[pair_tile] == 0:
            del remaining[pair_tile]

        if _can_form_melds(remaining):
            return True

    return False


def can_hu_qidui(hand: list[Tile]) -> bool:
    if len(hand) != 14:
        return False
    counts = Counter(hand)
    if any(count > 4 for count in counts.values()):
        return False

    pair_count = 0
    for count in counts.values():
        if count == 2:
            pair_count += 1
        elif count == 4:
            pair_count += 2
        else:
            return False
    return pair_count == 7


def is_standard_hu(tiles: list[Tile]) -> bool:
    return can_hu_standard(tiles)


def _melds_are_valid(melds: list[Meld]) -> bool:
    valid_types = {"chi", "peng", "concealed_gang", "exposed_gang", "added_gang"}
    return all(meld.type in valid_types and len(meld.tiles) in {3, 4} for meld in melds)


def _can_form_melds(counts: Counter[Tile]) -> bool:
    if not counts:
        return True

    tile = min(counts)

    if counts[tile] >= 3:
        triplet_counts = counts.copy()
        _remove_tile(triplet_counts, tile, 3)
        if _can_form_melds(triplet_counts):
            return True

    if tile.rank <= 7:
        sequence_tiles = [
            tile,
            Tile(tile.suit, tile.rank + 1),
            Tile(tile.suit, tile.rank + 2),
        ]
    else:
        sequence_tiles = []

    if sequence_tiles and all(counts.get(sequence_tile, 0) > 0 for sequence_tile in sequence_tiles):
        sequence_counts = counts.copy()
        for sequence_tile in sequence_tiles:
            _remove_tile(sequence_counts, sequence_tile, 1)
        if _can_form_melds(sequence_counts):
            return True

    return False


def _remove_tile(counts: Counter[Tile], tile: Tile, amount: int) -> None:
    counts[tile] -= amount
    if counts[tile] == 0:
        del counts[tile]
