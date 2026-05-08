import pytest

from core.mahjong.actions import chi_tile, discard_tile, gang_tile, start_game
from core.mahjong.player import Meld
from core.mahjong.tile import Tile

PLAYER_IDS = ["p1", "p2", "p3", "p4"]
PLAYER_NAMES = {
    "p1": "东风",
    "p2": "南风",
    "p3": "西风",
    "p4": "北风",
}


def test_next_player_can_chi_last_discard() -> None:
    state = _state_with_discard(Tile("wan", 3), p2_hand=[Tile("wan", 1), Tile("wan", 2)])
    hand_count = len(state.players["p2"].hand)

    next_state = chi_tile(state, "p2", [Tile("wan", 1), Tile("wan", 2), Tile("wan", 3)])

    assert len(next_state.players["p2"].hand) == hand_count - 2
    assert next_state.current_player_id == "p2"
    assert next_state.current_turn_has_drawn
    assert next_state.last_discard is None
    assert next_state.players["p1"].discard_pile == []
    meld = next_state.players["p2"].melds[0]
    assert meld.type == "chi"
    assert meld.tiles == [Tile("wan", 1), Tile("wan", 2), Tile("wan", 3)]
    assert meld.from_player_id == "p1"
    assert meld.claimed_tile == Tile("wan", 3)


def test_non_next_player_cannot_chi() -> None:
    state = _state_with_discard(Tile("wan", 3), p3_hand=[Tile("wan", 1), Tile("wan", 2)])

    with pytest.raises(ValueError, match="下家"):
        chi_tile(state, "p3", [Tile("wan", 1), Tile("wan", 2), Tile("wan", 3)])


def test_chi_cannot_cross_suits() -> None:
    state = _state_with_discard(Tile("wan", 3), p2_hand=[Tile("wan", 2), Tile("tong", 4)])

    with pytest.raises(ValueError, match="同花色连续"):
        chi_tile(state, "p2", [Tile("wan", 2), Tile("wan", 3), Tile("tong", 4)])


def test_chi_requires_two_tiles_in_hand() -> None:
    state = _state_with_discard(Tile("wan", 3), p2_hand=[Tile("wan", 1)])

    with pytest.raises(ValueError, match="缺少吃牌所需"):
        chi_tile(state, "p2", [Tile("wan", 1), Tile("wan", 2), Tile("wan", 3)])


def test_concealed_gang_on_own_turn_succeeds_and_draws_supplement() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = Tile("wan", 1)
    state.players["p1"].hand = [tile, tile, tile, tile, *state.players["p1"].hand[:10]]
    hand_count = len(state.players["p1"].hand)
    wall_count = len(state.wall)

    next_state = gang_tile(state, "p1", "concealed_gang", tile)

    assert len(next_state.players["p1"].hand) == hand_count - 3
    assert len(next_state.wall) == wall_count - 1
    assert next_state.current_player_id == "p1"
    assert next_state.current_turn_has_drawn
    meld = next_state.players["p1"].melds[0]
    assert meld.type == "concealed_gang"
    assert meld.concealed
    assert next_state.action_log[-3]["gang_type"] == "concealed_gang"
    assert next_state.action_log[-2]["type"] == "score"
    assert "tile" not in next_state.action_log[-2]


def test_concealed_gang_requires_own_turn_and_four_tiles() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = Tile("wan", 1)
    state.players["p2"].hand = [tile, tile, tile, tile, *state.players["p2"].hand[:9]]

    with pytest.raises(ValueError, match="当前玩家"):
        gang_tile(state, "p2", "concealed_gang", tile)

    with pytest.raises(ValueError, match="四张相同"):
        gang_tile(state, "p1", "concealed_gang", tile)


def test_exposed_gang_claims_last_discard_and_draws_supplement() -> None:
    tile = Tile("wan", 1)
    state = _state_with_discard(tile, p2_hand=[tile, tile, tile])
    hand_count = len(state.players["p2"].hand)
    wall_count = len(state.wall)

    next_state = gang_tile(state, "p2", "exposed_gang", tile)

    assert len(next_state.players["p2"].hand) == hand_count - 2
    assert len(next_state.wall) == wall_count - 1
    assert next_state.players["p1"].discard_pile == []
    assert next_state.current_player_id == "p2"
    assert next_state.last_discard is None
    meld = next_state.players["p2"].melds[0]
    assert meld.type == "exposed_gang"
    assert meld.from_player_id == "p1"
    assert meld.claimed_tile == tile


def test_exposed_gang_requires_last_discard_and_three_tiles() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = Tile("wan", 1)

    with pytest.raises(ValueError, match="可响应的弃牌"):
        gang_tile(state, "p2", "exposed_gang", tile)

    pending_state = _state_with_discard(
        tile,
        p2_hand=[tile, tile, Tile("wan", 2), Tile("wan", 3), Tile("wan", 4)],
    )
    pending_state.players["p2"].hand = pending_state.players["p2"].hand[:5]
    with pytest.raises(ValueError, match="三张相同"):
        gang_tile(pending_state, "p2", "exposed_gang", tile)


def test_added_gang_upgrades_peng_and_draws_supplement() -> None:
    tile = Tile("wan", 1)
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p1"].melds = [
        Meld(type="peng", tiles=[tile, tile, tile], from_player_id="p2", claimed_tile=tile)
    ]
    state.players["p1"].hand = [tile, *state.players["p1"].hand[:13]]
    hand_count = len(state.players["p1"].hand)
    wall_count = len(state.wall)

    next_state = gang_tile(state, "p1", "added_gang", tile)

    assert len(next_state.players["p1"].hand) == hand_count
    assert len(next_state.wall) == wall_count - 1
    meld = next_state.players["p1"].melds[0]
    assert meld.type == "added_gang"
    assert meld.tiles == [tile, tile, tile, tile]


def test_added_gang_requires_peng_meld_and_own_turn() -> None:
    tile = Tile("wan", 1)
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p2"].melds = [
        Meld(type="peng", tiles=[tile, tile, tile], from_player_id="p1", claimed_tile=tile)
    ]
    state.players["p2"].hand = [tile, *state.players["p2"].hand[:12]]

    with pytest.raises(ValueError, match="当前玩家"):
        gang_tile(state, "p2", "added_gang", tile)

    with pytest.raises(ValueError, match="没有对应"):
        gang_tile(state, "p1", "added_gang", tile)


def test_gang_with_empty_wall_enters_draw_game() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = Tile("wan", 1)
    state.players["p1"].hand = [tile, tile, tile, tile, *state.players["p1"].hand[:10]]
    state.wall = []

    next_state = gang_tile(state, "p1", "concealed_gang", tile)

    assert next_state.phase == "draw_game"
    assert next_state.action_log[-1]["type"] == "supplement_draw"
    assert next_state.action_log[-1]["result"] == "wall_empty"


def _state_with_discard(
    discard: Tile,
    p2_hand: list[Tile] | None = None,
    p3_hand: list[Tile] | None = None,
):
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p1"].hand = [discard, *state.players["p1"].hand[:13]]
    if p2_hand is not None:
        state.players["p2"].hand = [*p2_hand, *state.players["p2"].hand[: 13 - len(p2_hand)]]
    if p3_hand is not None:
        state.players["p3"].hand = [*p3_hand, *state.players["p3"].hand[: 13 - len(p3_hand)]]
    return discard_tile(state, "p1", discard)
