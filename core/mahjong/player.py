from dataclasses import dataclass, field

from core.mahjong.tile import Tile


@dataclass(slots=True)
class Meld:
    type: str
    tiles: list[Tile]
    from_player_id: str | None = None
    claimed_tile: Tile | None = None
    concealed: bool = False


@dataclass(slots=True)
class PlayerState:
    player_id: str
    name: str
    hand: list[Tile] = field(default_factory=list)
    discard_pile: list[Tile] = field(default_factory=list)
    melds: list[Meld] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    is_dealer: bool = False
    auto_sort_hand: bool = True
