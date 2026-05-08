from core.mahjong.hu_checker import can_hu, can_hu_qidui, can_hu_with_melds
from core.mahjong.player import Meld
from core.mahjong.tile import Tile


def tiles(values: list[tuple[str, int]]) -> list[Tile]:
    return [Tile(suit, rank) for suit, rank in values]


def test_can_hu_with_all_sequences() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 2),
            ("wan", 3),
            ("wan", 4),
            ("wan", 5),
            ("wan", 6),
            ("tong", 2),
            ("tong", 3),
            ("tong", 4),
            ("tiao", 7),
            ("tiao", 8),
            ("tiao", 9),
            ("wan", 9),
            ("wan", 9),
        ]
    )

    assert can_hu(hand)


def test_can_hu_with_triplets_and_sequences() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("tong", 2),
            ("tong", 3),
            ("tong", 4),
            ("tiao", 5),
            ("tiao", 5),
            ("tiao", 5),
            ("wan", 6),
            ("wan", 7),
            ("wan", 8),
            ("tong", 9),
            ("tong", 9),
        ]
    )

    assert can_hu(hand)


def test_can_hu_returns_false_for_non_winning_hand() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 4),
            ("wan", 5),
            ("wan", 7),
            ("tong", 1),
            ("tong", 3),
            ("tong", 4),
            ("tong", 6),
            ("tiao", 2),
            ("tiao", 5),
            ("tiao", 8),
            ("tiao", 9),
        ]
    )

    assert not can_hu(hand)


def test_can_hu_returns_false_when_tile_count_is_not_14() -> None:
    assert not can_hu(tiles([("wan", 1)] * 13))


def test_can_hu_with_multiple_possible_pairs() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 2),
            ("wan", 2),
            ("wan", 3),
            ("wan", 3),
            ("wan", 3),
            ("tong", 4),
            ("tong", 5),
            ("tong", 6),
            ("tiao", 9),
            ("tiao", 9),
        ]
    )

    assert can_hu(hand)


def test_can_hu_with_many_repeated_tiles() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 2),
            ("wan", 2),
            ("wan", 3),
            ("wan", 3),
            ("wan", 3),
            ("tong", 5),
            ("tong", 5),
            ("tong", 5),
            ("tiao", 9),
        ]
    )

    assert not can_hu(hand)


def test_can_hu_covers_all_three_suits() -> None:
    hand = tiles(
        [
            ("wan", 2),
            ("wan", 3),
            ("wan", 4),
            ("tong", 2),
            ("tong", 3),
            ("tong", 4),
            ("tiao", 2),
            ("tiao", 3),
            ("tiao", 4),
            ("wan", 7),
            ("wan", 8),
            ("wan", 9),
            ("tong", 1),
            ("tong", 1),
        ]
    )

    assert can_hu(hand)


def test_sequence_cannot_cross_suits() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("tong", 2),
            ("tiao", 3),
            ("wan", 4),
            ("tong", 5),
            ("tiao", 6),
            ("wan", 7),
            ("tong", 8),
            ("tiao", 9),
            ("wan", 1),
            ("tong", 1),
            ("tiao", 1),
            ("wan", 9),
            ("wan", 9),
        ]
    )

    assert not can_hu(hand)


def test_one_two_three_can_form_sequence() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 2),
            ("wan", 3),
            ("tong", 1),
            ("tong", 2),
            ("tong", 3),
            ("tiao", 1),
            ("tiao", 2),
            ("tiao", 3),
            ("wan", 5),
            ("wan", 6),
            ("wan", 7),
            ("tong", 9),
            ("tong", 9),
        ]
    )

    assert can_hu(hand)


def test_seven_eight_nine_can_form_sequence() -> None:
    hand = tiles(
        [
            ("wan", 7),
            ("wan", 8),
            ("wan", 9),
            ("tong", 7),
            ("tong", 8),
            ("tong", 9),
            ("tiao", 7),
            ("tiao", 8),
            ("tiao", 9),
            ("wan", 1),
            ("wan", 2),
            ("wan", 3),
            ("tiao", 5),
            ("tiao", 5),
        ]
    )

    assert can_hu(hand)


def test_eight_nine_ten_does_not_exist() -> None:
    hand = tiles(
        [
            ("wan", 8),
            ("wan", 9),
            ("wan", 8),
            ("wan", 9),
            ("tong", 8),
            ("tong", 9),
            ("tong", 8),
            ("tong", 9),
            ("tiao", 8),
            ("tiao", 9),
            ("tiao", 8),
            ("tiao", 9),
            ("wan", 1),
            ("tong", 1),
        ]
    )

    assert not can_hu(hand)


def test_more_than_four_identical_tiles_is_invalid() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("tong", 2),
            ("tong", 3),
            ("tong", 4),
            ("tiao", 2),
            ("tiao", 3),
            ("tiao", 4),
            ("wan", 7),
            ("wan", 8),
            ("wan", 9),
        ]
    )

    assert not can_hu(hand)


def test_can_hu_with_existing_melds() -> None:
    melds = [
        Meld(
            type="chi",
            tiles=tiles([("wan", 1), ("wan", 2), ("wan", 3)]),
            from_player_id="p1",
            claimed_tile=Tile("wan", 3),
        )
    ]
    hand = tiles(
        [
            ("wan", 4),
            ("wan", 5),
            ("wan", 6),
            ("tong", 2),
            ("tong", 3),
            ("tong", 4),
            ("tiao", 7),
            ("tiao", 8),
            ("tiao", 9),
            ("wan", 9),
            ("wan", 9),
        ]
    )

    assert can_hu_with_melds(hand, melds)


def test_can_hu_with_melds_rejects_wrong_hand_count() -> None:
    melds = [Meld(type="peng", tiles=tiles([("wan", 1), ("wan", 1), ("wan", 1)]))]

    assert not can_hu_with_melds(tiles([("wan", 9), ("wan", 9)]), melds)


def test_can_hu_qidui_with_standard_seven_pairs() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 2),
            ("wan", 3),
            ("wan", 3),
            ("wan", 4),
            ("wan", 4),
            ("wan", 5),
            ("wan", 5),
            ("wan", 6),
            ("wan", 6),
            ("wan", 7),
            ("wan", 7),
        ]
    )

    assert can_hu_qidui(hand)
    assert can_hu(hand)


def test_can_hu_qidui_allows_four_identical_tiles_as_two_pairs() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 2),
            ("wan", 3),
            ("wan", 3),
            ("wan", 4),
            ("wan", 4),
            ("wan", 5),
            ("wan", 5),
            ("wan", 6),
            ("wan", 6),
        ]
    )

    assert can_hu_qidui(hand)
    assert can_hu(hand)


def test_can_hu_qidui_rejects_triplet_shape() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 2),
            ("wan", 3),
            ("wan", 3),
            ("wan", 4),
            ("wan", 4),
            ("wan", 5),
            ("wan", 5),
            ("wan", 6),
            ("wan", 6),
            ("wan", 7),
        ]
    )

    assert not can_hu_qidui(hand)


def test_can_hu_qidui_rejects_wrong_tile_count() -> None:
    assert not can_hu_qidui(tiles([("wan", 1), ("wan", 1)] * 6))


def test_can_hu_with_melds_does_not_allow_qidui_with_melds() -> None:
    hand = tiles(
        [
            ("wan", 1),
            ("wan", 1),
            ("wan", 2),
            ("wan", 2),
            ("wan", 3),
            ("wan", 3),
            ("wan", 4),
            ("wan", 4),
            ("wan", 5),
            ("wan", 5),
            ("wan", 6),
        ]
    )
    melds = [Meld(type="peng", tiles=tiles([("wan", 7), ("wan", 7), ("wan", 7)]))]

    assert not can_hu_with_melds(hand, melds)
