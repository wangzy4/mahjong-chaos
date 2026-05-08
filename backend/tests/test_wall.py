from collections import Counter

from core.mahjong.tile import Suit, Tile, parse_tile, sort_tiles, tile_to_str
from core.mahjong.wall import create_wall


def test_create_wall_has_108_tiles() -> None:
    wall = create_wall(seed=1)

    assert len(wall) == 108


def test_create_wall_has_four_of_each_suited_tile() -> None:
    wall = create_wall(seed=1)
    counts = Counter(wall)

    for suit in Suit:
        for rank in range(1, 10):
            assert counts[Tile(suit=suit, rank=rank)] == 4


def test_create_wall_with_same_seed_is_reproducible() -> None:
    assert create_wall(seed=42) == create_wall(seed=42)


def test_create_wall_with_different_seed_is_likely_different() -> None:
    assert create_wall(seed=1) != create_wall(seed=2)


def test_tile_to_str_and_parse_tile() -> None:
    tile = Tile("wan", 3)

    assert tile_to_str(tile) == "3万"
    assert str(tile) == "3万"
    assert parse_tile("3万") == tile
    assert parse_tile("5筒") == Tile("tong", 5)
    assert parse_tile("7条") == Tile("tiao", 7)


def test_sort_tiles_orders_wan_tiao_tong_then_rank() -> None:
    unsorted_tiles = [
        Tile("tong", 1),
        Tile("wan", 9),
        Tile("tiao", 2),
        Tile("wan", 1),
        Tile("tong", 3),
        Tile("tiao", 1),
    ]

    assert [tile_to_str(tile) for tile in sort_tiles(unsorted_tiles)] == [
        "1万",
        "9万",
        "1条",
        "2条",
        "1筒",
        "3筒",
    ]
