from core.mahjong.actions import start_game
from core.mahjong.fan import (
    calculate_fan_multiplier,
    detect_fans,
    is_menqing,
    is_pengpenghu,
    is_qidui,
    is_qidui_hand,
    is_qingyise,
)
from core.mahjong.player import Meld, PlayerState
from core.mahjong.tile import Tile

PLAYER_IDS = ["p1", "p2", "p3", "p4"]
PLAYER_NAMES = {"p1": "东风", "p2": "南风", "p3": "西风", "p4": "北风"}


def test_menqing_without_melds() -> None:
    assert is_menqing(PlayerState("p1", "东风"))


def test_menqing_allows_concealed_gang() -> None:
    player = PlayerState("p1", "东风", melds=[gang("concealed_gang", wan(1))])

    assert is_menqing(player)


def test_open_melds_break_menqing() -> None:
    for meld_type in ["chi", "peng", "exposed_gang", "added_gang"]:
        player = PlayerState("p1", "东风", melds=[gang(meld_type, wan(1))])

        assert not is_menqing(player)


def test_qingyise_with_hand_and_melds() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=[wan(1), wan(2), wan(3), wan(4)],
        melds=[gang("peng", wan(5))],
    )

    assert is_qingyise(player, wan(9))


def test_qingyise_checks_winning_tile() -> None:
    player = PlayerState("p1", "东风", hand=[wan(1), wan(2), wan(3)])

    assert not is_qingyise(player, tong(9))


def test_qingyise_rejects_mixed_suits() -> None:
    player = PlayerState("p1", "东风", hand=[wan(1), tong(1), wan(2)])

    assert not is_qingyise(player, wan(3))


def test_pengpenghu_with_triplets_and_pair() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=[
            wan(1),
            wan(1),
            wan(1),
            tong(2),
            tong(2),
            tong(2),
            wan(9),
            wan(9),
        ],
        melds=[gang("peng", wan(3)), gang("concealed_gang", tiao(4))],
    )

    assert is_pengpenghu(player, None)


def test_pengpenghu_rejects_chi() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=[wan(1), wan(1)],
        melds=[
            Meld(type="chi", tiles=[wan(2), wan(3), wan(4)]),
            gang("peng", wan(5)),
            gang("peng", tong(6)),
            gang("peng", tiao(7)),
        ],
    )

    assert not is_pengpenghu(player, None)


def test_pengpenghu_rejects_concealed_sequence_shape() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=[
            wan(1),
            wan(2),
            wan(3),
            wan(4),
            wan(4),
            wan(4),
            tong(2),
            tong(2),
            tong(2),
            tiao(7),
            tiao(7),
            tiao(7),
            wan(9),
            wan(9),
        ],
    )

    assert not is_pengpenghu(player, None)


def test_pengpenghu_uses_winning_tile_for_discard_win() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=[
            wan(1),
            wan(1),
            wan(1),
            tong(2),
            tong(2),
            tong(2),
            tiao(3),
            tiao(3),
            tiao(3),
            wan(4),
            wan(4),
            wan(4),
            wan(9),
        ],
    )

    assert is_pengpenghu(player, wan(9))


def test_fan_multiplier_stacks_multiplicatively() -> None:
    assert calculate_fan_multiplier([]) == 1
    assert calculate_fan_multiplier(["menqing"]) == 2
    assert calculate_fan_multiplier(["menqing", "qingyise"]) == 4
    assert calculate_fan_multiplier(["menqing", "qingyise", "pengpenghu"]) == 8
    assert calculate_fan_multiplier(["qidui"]) == 4
    assert calculate_fan_multiplier(["qidui", "qingyise"]) == 8


def test_detect_fans_does_not_add_self_draw_multiplier() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p1"].hand = [
        wan(1),
        wan(2),
        wan(3),
        wan(4),
        wan(5),
        wan(6),
        wan(7),
        wan(8),
        wan(9),
        wan(2),
        wan(3),
        wan(4),
        wan(9),
        wan(9),
    ]

    result = detect_fans(state, "p1", "self_draw", None)

    assert result.fans == ["menqing", "qingyise"]
    assert result.multiplier == 4


def test_qidui_hand_detection_standard_pairs() -> None:
    assert is_qidui_hand(qidui_wan_hand())


def test_qidui_hand_detection_allows_four_identical_tiles() -> None:
    assert is_qidui_hand(
        [
            wan(1),
            wan(1),
            wan(1),
            wan(1),
            wan(2),
            wan(2),
            wan(3),
            wan(3),
            wan(4),
            wan(4),
            wan(5),
            wan(5),
            wan(6),
            wan(6),
        ]
    )


def test_qidui_hand_detection_rejects_triplet() -> None:
    assert not is_qidui_hand(
        [
            wan(1),
            wan(1),
            wan(1),
            wan(2),
            wan(2),
            wan(3),
            wan(3),
            wan(4),
            wan(4),
            wan(5),
            wan(5),
            wan(6),
            wan(6),
            wan(7),
        ]
    )


def test_qidui_rejects_any_meld() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=qidui_wan_hand(),
        melds=[gang("concealed_gang", wan(8))],
    )

    assert not is_qidui(player, None)


def test_qidui_uses_winning_tile_for_discard_win() -> None:
    player = PlayerState(
        "p1",
        "东风",
        hand=qidui_wan_hand()[:-1],
    )

    assert is_qidui(player, wan(7))


def test_detect_fans_qidui_does_not_include_menqing_or_pengpenghu() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p1"].hand = [
        wan(1),
        wan(1),
        wan(2),
        wan(2),
        wan(3),
        wan(3),
        wan(4),
        wan(4),
        tong(5),
        tong(5),
        tong(6),
        tong(6),
        tong(7),
        tong(7),
    ]

    result = detect_fans(state, "p1", "self_draw", None)

    assert result.fans == ["qidui"]
    assert "menqing" not in result.fans
    assert "pengpenghu" not in result.fans
    assert result.multiplier == 4


def test_detect_fans_qidui_and_qingyise_stack() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p1"].hand = qidui_wan_hand()

    result = detect_fans(state, "p1", "self_draw", None)

    assert result.fans == ["qidui", "qingyise"]
    assert result.multiplier == 8


def gang(meld_type: str, tile: Tile) -> Meld:
    count = 4 if "gang" in meld_type else 3
    return Meld(type=meld_type, tiles=[tile] * count, concealed=meld_type == "concealed_gang")


def qidui_wan_hand() -> list[Tile]:
    return [
        wan(1),
        wan(1),
        wan(2),
        wan(2),
        wan(3),
        wan(3),
        wan(4),
        wan(4),
        wan(5),
        wan(5),
        wan(6),
        wan(6),
        wan(7),
        wan(7),
    ]


def wan(rank: int) -> Tile:
    return Tile("wan", rank)


def tong(rank: int) -> Tile:
    return Tile("tong", rank)


def tiao(rank: int) -> Tile:
    return Tile("tiao", rank)
