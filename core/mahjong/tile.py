from dataclasses import dataclass
from enum import StrEnum


class Suit(StrEnum):
    WAN = "wan"
    TONG = "tong"
    TIAO = "tiao"


SUIT_TO_DISPLAY: dict[Suit, str] = {
    Suit.WAN: "万",
    Suit.TONG: "筒",
    Suit.TIAO: "条",
}

DISPLAY_TO_SUIT: dict[str, Suit] = {display: suit for suit, display in SUIT_TO_DISPLAY.items()}
SUIT_SORT_ORDER: dict[Suit, int] = {
    Suit.WAN: 0,
    Suit.TIAO: 1,
    Suit.TONG: 2,
}


@dataclass(frozen=True, order=True, slots=True)
class Tile:
    suit: Suit | str
    rank: int

    def __post_init__(self) -> None:
        try:
            suit = Suit(self.suit)
        except ValueError as exc:
            raise ValueError(f"不支持的牌花色：{self.suit}") from exc

        if not 1 <= self.rank <= 9:
            raise ValueError("牌点数必须在 1 到 9 之间")

        object.__setattr__(self, "suit", suit)

    def __str__(self) -> str:
        return tile_to_str(self)


def tile_to_str(tile: Tile) -> str:
    return f"{tile.rank}{SUIT_TO_DISPLAY[tile.suit]}"


def parse_tile(value: str) -> Tile:
    if len(value) != 2:
        raise ValueError("牌文本格式应类似“3万”")

    rank_text, suit_text = value[0], value[1]
    if not rank_text.isdigit():
        raise ValueError("牌点数必须是数字")

    suit = DISPLAY_TO_SUIT.get(suit_text)
    if suit is None:
        raise ValueError(f"不支持的牌花色显示：{suit_text}")

    return Tile(suit=suit, rank=int(rank_text))


def sort_tiles(tiles: list[Tile]) -> list[Tile]:
    return sorted(tiles, key=lambda tile: (SUIT_SORT_ORDER[tile.suit], tile.rank))
