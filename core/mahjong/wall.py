import random

from core.mahjong.tile import Suit, Tile


def create_wall(seed: int | None = None) -> list[Tile]:
    wall = [Tile(suit=suit, rank=rank) for suit in Suit for rank in range(1, 10) for _ in range(4)]
    random.Random(seed).shuffle(wall)
    return wall


def build_standard_wall() -> list[Tile]:
    return create_wall(seed=0)
