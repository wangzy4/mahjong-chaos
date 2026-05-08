import pytest

from core.mahjong.actions import (
    discard_tile,
    draw_tile,
    pass_peng,
    peng_tile,
    start_game,
)
from core.mahjong.tile import Tile, sort_tiles

PLAYER_IDS = ["p1", "p2", "p3", "p4"]
PLAYER_NAMES = {
    "p1": "东风",
    "p2": "南风",
    "p3": "西风",
    "p4": "北风",
}


def test_start_game_deals_correct_tile_counts() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)

    assert state.phase == "playing"
    assert state.dealer_id == "p1"
    assert state.current_player_id == "p1"
    assert state.current_turn_has_drawn
    assert len(state.players["p1"].hand) == 14
    assert len(state.players["p2"].hand) == 13
    assert len(state.players["p3"].hand) == 13
    assert len(state.players["p4"].hand) == 13
    assert len(state.wall) == 55
    assert state.action_log[0]["type"] == "start_game"
    assert "hands" not in state.action_log[0]


def test_start_game_sorts_hands_by_default() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)

    assert state.players["p1"].auto_sort_hand
    assert state.players["p1"].hand == sort_tiles(state.players["p1"].hand)


def test_start_game_supports_two_to_four_players() -> None:
    state = start_game("room-1", PLAYER_IDS[:2], PLAYER_NAMES, seed=1)

    assert state.player_order == ["p1", "p2"]
    assert len(state.players["p1"].hand) == 14
    assert len(state.players["p2"].hand) == 13


def test_start_game_requires_at_least_two_players() -> None:
    with pytest.raises(ValueError, match="2 到 4 名玩家"):
        start_game("room-1", PLAYER_IDS[:1], PLAYER_NAMES, seed=1)


def test_current_player_cannot_draw_again_before_discarding() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)

    with pytest.raises(ValueError, match="必须先出牌"):
        draw_tile(state, "p1")


def test_discard_tile_enters_pending_peng_phase() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = state.players["p1"].hand[0]
    p1_hand_count = len(state.players["p1"].hand)
    p2_hand_count = len(state.players["p2"].hand)
    wall_count = len(state.wall)

    next_state = discard_tile(state, "p1", tile)

    assert len(next_state.players["p1"].hand) == p1_hand_count - 1
    assert tile in next_state.players["p1"].discard_pile
    assert next_state.current_player_id == "p2"
    assert not next_state.current_turn_has_drawn
    assert next_state.last_discard is not None
    assert next_state.last_discard.player_id == "p1"
    assert next_state.last_discard.tile == tile
    assert next_state.last_discard.next_player_id == "p2"
    assert next_state.last_discard.available_for_claim
    assert len(next_state.players["p2"].hand) == p2_hand_count
    assert len(next_state.wall) == wall_count
    assert len(state.players["p1"].discard_pile) == 0
    assert next_state.action_log[-1]["type"] == "discard"


def test_pass_peng_auto_draws_for_next_player() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = state.players["p1"].hand[0]
    pending_state = discard_tile(state, "p1", tile)
    p2_hand_count = len(pending_state.players["p2"].hand)
    wall_count = len(pending_state.wall)

    next_state = pass_peng(pending_state, "p2")

    assert next_state.last_discard is None
    assert next_state.current_player_id == "p2"
    assert next_state.current_turn_has_drawn
    assert len(next_state.players["p2"].hand) == p2_hand_count + 1
    assert len(next_state.wall) == wall_count - 1
    assert next_state.action_log[-1]["type"] == "draw"
    assert next_state.action_log[-1]["auto"] is True


def test_pass_peng_clears_seal_peng_effects() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = state.players["p1"].hand[0]
    pending_state = discard_tile(state, "p1", tile)
    pending_state.sealed_peng_player_ids.add("p2")

    next_state = pass_peng(pending_state, "p3")

    assert next_state.sealed_peng_player_ids == set()


def test_non_current_player_cannot_draw_or_discard() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    tile = state.players["p2"].hand[0]

    with pytest.raises(ValueError, match="当前玩家"):
        draw_tile(state, "p2")

    with pytest.raises(ValueError, match="当前玩家"):
        discard_tile(state, "p2", tile)


def test_discard_missing_tile_raises_error() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    missing_tile = next(
        Tile(suit, rank)
        for suit in ("wan", "tong", "tiao")
        for rank in range(1, 10)
        if Tile(suit, rank) not in state.players["p1"].hand
    )

    with pytest.raises(ValueError, match="没有这张牌"):
        discard_tile(state, "p1", missing_tile)


def test_peng_with_two_matching_tiles_succeeds() -> None:
    state = _state_with_pending_peng()
    hand_count = len(state.players["p2"].hand)

    next_state = peng_tile(state, "p2")

    assert next_state.current_player_id == "p2"
    assert next_state.current_turn_has_drawn
    assert len(next_state.players["p2"].hand) == hand_count - 2
    meld = next_state.players["p2"].melds[0]
    assert meld.type == "peng"
    assert meld.tiles == [Tile("wan", 1), Tile("wan", 1), Tile("wan", 1)]
    assert next_state.last_discard is None
    assert next_state.players["p1"].discard_pile == []
    assert next_state.action_log[-1]["type"] == "peng"


def test_peng_without_two_matching_tiles_fails() -> None:
    state = _state_with_pending_peng()
    state.players["p2"].hand = [Tile("wan", 1), Tile("wan", 2), Tile("wan", 3)]

    with pytest.raises(ValueError, match="没有两张相同"):
        peng_tile(state, "p2")


def test_seal_peng_blocks_peng_once_and_then_is_removed() -> None:
    state = _state_with_pending_peng()
    state.sealed_peng_player_ids.add("p2")

    next_state = peng_tile(state, "p2")

    assert next_state.players["p2"].melds == []
    assert "p2" not in next_state.sealed_peng_player_ids
    assert next_state.last_discard is not None
    assert next_state.last_discard.tile == Tile("wan", 1)
    assert next_state.action_log[-1] == {
        "type": "pass_peng",
        "player_id": "p2",
        "reason": "sealed_peng",
    }


def _state_with_pending_peng():
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    discard = Tile("wan", 1)
    state.players["p1"].hand = [discard, *state.players["p1"].hand[:13]]
    state.players["p2"].hand = [discard, discard, *state.players["p2"].hand[:11]]
    return discard_tile(state, "p1", discard)
