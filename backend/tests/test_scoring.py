import pytest

from core.mahjong.actions import gang_tile, start_game
from core.mahjong.player import Meld
from core.mahjong.scoring import (
    InvalidScoreError,
    InvalidSettlementError,
    apply_delta,
    calculate_draw_delta,
    calculate_gang_delta,
    calculate_legacy_win_delta,
    calculate_win_delta,
    settle_win,
)
from core.mahjong.tile import Tile

PLAYER_IDS = ["p1", "p2", "p3", "p4"]
PLAYER_NAMES = {"p1": "东风", "p2": "南风", "p3": "西风", "p4": "北风"}


def test_discard_win_without_fans_and_dealer() -> None:
    state = make_state()
    make_no_fan_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "discard", "p4", wan(9))

    assert delta == {"p1": 0, "p2": 0, "p3": 3, "p4": -3}
    assert event["fan_multiplier"] == 1
    assert event["payments"][0]["dealer_multiplier"] == 1


def test_discard_win_menqing_fan() -> None:
    state = make_state()
    make_menqing_mixed_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "discard", "p4", tong(9))

    assert delta["p3"] == 6
    assert delta["p4"] == -6
    assert event["fans"] == ["menqing"]
    assert event["fan_multiplier"] == 2


def test_dealer_discard_win_without_fans() -> None:
    state = make_state()
    make_no_fan_player(state, "p1")

    delta, _event = calculate_win_delta(state, "p1", "discard", "p4", wan(9))

    assert delta == {"p1": 6, "p2": 0, "p3": 0, "p4": -6}


def test_dealer_loses_discard_win_without_fans() -> None:
    state = make_state()
    make_no_fan_player(state, "p3")

    delta, _event = calculate_win_delta(state, "p3", "discard", "p1", wan(9))

    assert delta == {"p1": -6, "p2": 0, "p3": 6, "p4": 0}


def test_discard_win_two_fans_and_dealer_loser() -> None:
    state = make_state()
    make_menqing_qingyise_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "discard", "p1", wan(9))

    assert delta == {"p1": -24, "p2": 0, "p3": 24, "p4": 0}
    assert event["fans"] == ["menqing", "qingyise"]
    assert event["fan_multiplier"] == 4
    assert event["payments"][0]["dealer_multiplier"] == 2


def test_non_dealer_self_draw_without_fans_dealer_pays_double() -> None:
    state = make_state()
    make_no_fan_player(state, "p3")

    delta, _event = calculate_win_delta(state, "p3", "self_draw", None, None)

    assert delta == {"p1": -4, "p2": -2, "p3": 8, "p4": -2}


def test_dealer_self_draw_without_fans() -> None:
    state = make_state()
    make_no_fan_player(state, "p1")

    delta, _event = calculate_win_delta(state, "p1", "self_draw", None, None)

    assert delta == {"p1": 12, "p2": -4, "p3": -4, "p4": -4}


def test_non_dealer_menqing_self_draw_dealer_pays_double() -> None:
    state = make_state()
    make_menqing_mixed_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "self_draw", None, None)

    assert delta == {"p1": -8, "p2": -4, "p3": 16, "p4": -4}
    assert event["fan_multiplier"] == 2


def test_dealer_qingyise_self_draw() -> None:
    state = make_state()
    make_qingyise_open_player(state, "p1")

    delta, event = calculate_win_delta(state, "p1", "self_draw", None, None)

    assert delta == {"p1": 24, "p2": -8, "p3": -8, "p4": -8}
    assert event["fans"] == ["qingyise"]
    assert event["fan_multiplier"] == 2


def test_double_score_stacks_with_fan_and_dealer_but_not_gang() -> None:
    state = make_state()
    make_menqing_mixed_player(state, "p3")
    state.players["p3"].skills = ["double_score"]

    delta, event = calculate_win_delta(state, "p3", "discard", "p1", tong(9))
    gang_delta, _gang_event = calculate_gang_delta(state, "p3", "exposed_gang", "p1")

    assert delta == {"p1": -24, "p2": 0, "p3": 24, "p4": 0}
    assert event["double_score_multiplier"] == 2
    assert gang_delta == {"p1": -6, "p2": 0, "p3": 6, "p4": 0}


def test_non_dealer_qidui_discard_win_from_non_dealer() -> None:
    state = make_state()
    make_qidui_mixed_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "discard", "p4", tong(7))

    assert delta == {"p1": 0, "p2": 0, "p3": 12, "p4": -12}
    assert event["fans"] == ["qidui"]
    assert event["fan_multiplier"] == 4
    assert event["payments"][0]["amount"] == 12


def test_non_dealer_qidui_qingyise_discard_win_from_non_dealer() -> None:
    state = make_state()
    make_qidui_qingyise_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "discard", "p4", wan(7))

    assert delta == {"p1": 0, "p2": 0, "p3": 24, "p4": -24}
    assert event["fans"] == ["qidui", "qingyise"]
    assert event["fan_multiplier"] == 8


def test_dealer_qidui_discard_win() -> None:
    state = make_state()
    make_qidui_mixed_player(state, "p1")

    delta, event = calculate_win_delta(state, "p1", "discard", "p4", tong(7))

    assert delta == {"p1": 24, "p2": 0, "p3": 0, "p4": -24}
    assert event["fan_multiplier"] == 4
    assert event["payments"][0]["dealer_multiplier"] == 2


def test_non_dealer_qidui_self_draw_dealer_pays_double() -> None:
    state = make_state()
    make_qidui_mixed_self_draw_player(state, "p3")

    delta, event = calculate_win_delta(state, "p3", "self_draw", None, None)

    assert delta == {"p1": -16, "p2": -8, "p3": 32, "p4": -8}
    assert event["fans"] == ["qidui"]
    assert event["fan_multiplier"] == 4


def test_dealer_qidui_self_draw() -> None:
    state = make_state()
    make_qidui_mixed_self_draw_player(state, "p1")

    delta, event = calculate_win_delta(state, "p1", "self_draw", None, None)

    assert delta == {"p1": 48, "p2": -16, "p3": -16, "p4": -16}
    assert event["fans"] == ["qidui"]
    assert event["fan_multiplier"] == 4


def test_concealed_gang_non_dealer_with_dealer_payer() -> None:
    state = make_state()

    delta, event = calculate_gang_delta(state, "p3", "concealed_gang")

    assert delta == {"p1": -4, "p2": -2, "p3": 8, "p4": -2}
    assert event["fan_multiplier"] == 1


def test_concealed_gang_by_dealer() -> None:
    state = make_state()

    delta, _event = calculate_gang_delta(state, "p1", "concealed_gang")

    assert delta == {"p1": 12, "p2": -4, "p3": -4, "p4": -4}


def test_exposed_gang_non_dealer_from_non_dealer() -> None:
    state = make_state()

    delta, _event = calculate_gang_delta(state, "p3", "exposed_gang", "p4")

    assert delta == {"p1": 0, "p2": 0, "p3": 3, "p4": -3}


def test_exposed_gang_by_dealer() -> None:
    state = make_state()

    delta, _event = calculate_gang_delta(state, "p1", "exposed_gang", "p4")

    assert delta == {"p1": 6, "p2": 0, "p3": 0, "p4": -6}


def test_exposed_gang_from_dealer() -> None:
    state = make_state()

    delta, _event = calculate_gang_delta(state, "p3", "exposed_gang", "p1")

    assert delta == {"p1": -6, "p2": 0, "p3": 6, "p4": 0}


def test_added_gang_non_dealer_with_dealer_payer() -> None:
    state = make_state()

    delta, _event = calculate_gang_delta(state, "p3", "added_gang")

    assert delta == {"p1": -2, "p2": -1, "p3": 4, "p4": -1}


def test_added_gang_by_dealer() -> None:
    state = make_state()

    delta, _event = calculate_gang_delta(state, "p1", "added_gang")

    assert delta == {"p1": 6, "p2": -2, "p3": -2, "p4": -2}


def test_gang_score_updates_scores_immediately() -> None:
    state = make_state()
    tile = wan(1)
    state.players["p1"].hand = [tile, tile, tile, tile, *state.players["p1"].hand[:10]]

    state = gang_tile(state, "p1", "concealed_gang", tile)

    assert state.scores == {"p1": 12, "p2": -4, "p3": -4, "p4": -4}
    assert state.score_events[-1]["type"] == "gang"
    assert state.score_events[-1]["gang_type"] == "concealed_gang"


def test_apply_delta_accumulates_scores_and_round_delta() -> None:
    state = make_state()

    apply_delta(state, {"p1": 3, "p2": -3, "p3": 0, "p4": 0}, {"type": "test"})
    apply_delta(state, {"p1": 0, "p2": -3, "p3": 3, "p4": 0}, {"type": "test"})

    assert state.scores == {"p1": 3, "p2": -6, "p3": 3, "p4": 0}
    assert state.round_score_delta == {"p1": 3, "p2": -6, "p3": 3, "p4": 0}


def test_score_events_record_fans_dealer_and_payments() -> None:
    state = make_state()
    make_menqing_mixed_player(state, "p3")

    settle_win(state, "p3", "discard", "p1", tong(9))

    event = state.score_events[-1]
    assert event["type"] == "win"
    assert event["fans"] == ["menqing"]
    assert event["fan_multiplier"] == 2
    assert event["dealer_id"] == "p1"
    assert event["payments"][0] == {
        "from": "p1",
        "to": "p3",
        "base": 3,
        "fan_multiplier": 2,
        "dealer_multiplier": 2,
        "double_score_multiplier": 1,
        "amount": 12,
    }
    assert state.action_log[-1]["type"] == "score"
    assert state.settlement_summary is not None
    assert state.settlement_summary["fan_multiplier"] == 2


def test_invalid_delta_and_contexts_raise_clear_errors() -> None:
    state = make_state()

    with pytest.raises(InvalidScoreError, match="必须包含所有玩家"):
        apply_delta(state, {"p1": 1, "p2": -1}, {"type": "bad"})
    with pytest.raises(InvalidScoreError, match="总和必须为 0"):
        apply_delta(state, {"p1": 1, "p2": 0, "p3": 0, "p4": 0}, {"type": "bad"})
    with pytest.raises(InvalidSettlementError, match="点炮胡必须提供点炮玩家"):
        calculate_win_delta(state, "p3", "discard", None, wan(9))
    with pytest.raises(InvalidSettlementError, match="明杠必须提供点杠玩家"):
        calculate_gang_delta(state, "p3", "exposed_gang")


def test_legacy_draw_delta_still_available() -> None:
    assert calculate_draw_delta(PLAYER_IDS) == {"p1": 0, "p2": 0, "p3": 0, "p4": 0}
    assert calculate_legacy_win_delta(PLAYER_IDS, "p1", "discard", "p2") == {
        "p1": 3,
        "p2": -3,
        "p3": 0,
        "p4": 0,
    }


def make_no_fan_player(state, player_id: str) -> None:
    player = state.players[player_id]
    player.melds = [Meld(type="chi", tiles=[wan(1), wan(2), wan(3)])]
    player.hand = [wan(4), wan(5), tong(6), tong(7), tiao(8), tiao(9), wan(9), wan(9)]


def make_menqing_mixed_player(state, player_id: str) -> None:
    player = state.players[player_id]
    player.melds = []
    player.hand = [
        wan(1),
        wan(2),
        wan(3),
        tong(4),
        tong(5),
        tong(6),
        tiao(7),
        tiao(8),
        tiao(9),
        wan(9),
        wan(9),
        tong(1),
        tong(2),
    ]


def make_menqing_qingyise_player(state, player_id: str) -> None:
    player = state.players[player_id]
    player.melds = []
    player.hand = [
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
    ]


def make_qingyise_open_player(state, player_id: str) -> None:
    player = state.players[player_id]
    player.melds = [Meld(type="chi", tiles=[wan(1), wan(2), wan(3)])]
    player.hand = [wan(4), wan(5), wan(6), wan(7), wan(8), wan(9), wan(9), wan(9)]


def make_qidui_mixed_player(state, player_id: str) -> None:
    player = state.players[player_id]
    player.melds = []
    player.hand = [
        wan(1),
        wan(1),
        wan(2),
        wan(2),
        wan(3),
        wan(3),
        tong(4),
        tong(4),
        tong(5),
        tong(5),
        tiao(6),
        tiao(6),
        tong(7),
    ]


def make_qidui_mixed_self_draw_player(state, player_id: str) -> None:
    make_qidui_mixed_player(state, player_id)
    state.players[player_id].hand.append(tong(7))


def make_qidui_qingyise_player(state, player_id: str) -> None:
    player = state.players[player_id]
    player.melds = []
    player.hand = [
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


def make_state():
    return start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)


def wan(rank: int) -> Tile:
    return Tile("wan", rank)


def tong(rank: int) -> Tile:
    return Tile("tong", rank)


def tiao(rank: int) -> Tile:
    return Tile("tiao", rank)
