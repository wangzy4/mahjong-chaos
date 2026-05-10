from core.mahjong.actions import select_skills, start_game, use_skill
from core.mahjong.player import Meld
from core.mahjong.tile import Tile
from core.skills.new_skills import create_skill_registry


def make_playing_state():
    state = start_game("r", ["p1", "p2"], {"p1": "东风", "p2": "南风"}, seed=1)
    state.phase = "playing"
    return state


def test_players_can_select_skills_in_any_order() -> None:
    state = start_game("r", ["p1", "p2"], {"p1": "东风", "p2": "南风"}, seed=1)
    state.phase = "skill_selection"
    state.players["p1"].skill_candidates = ["astrology", "wish_tile", "change_suit"]
    state.players["p2"].skill_candidates = ["stealth_gang", "wish_tile", "change_suit"]

    state = select_skills(state, "p2", ["stealth_gang", "wish_tile"])

    assert state.phase == "skill_selection"
    assert state.players["p2"].skills == ["stealth_gang", "wish_tile"]
    assert state.players["p1"].skills == []

    state = select_skills(state, "p1", ["astrology", "change_suit"])

    assert state.phase == "playing"


def test_change_suit_replaces_tile_without_increasing_hand_count() -> None:
    state = make_playing_state()
    state.players["p1"].skills = ["change_suit"]
    state.players["p1"].hand = [
        Tile("tiao", 3),
        *[tile for tile in state.players["p1"].hand if tile != Tile("tiao", 3)][:13],
    ]
    state.wall = [tile for tile in state.wall if tile != Tile("tong", 3)]
    state.wall.append(Tile("tong", 3))
    before_count = len(state.players["p1"].hand)

    state = use_skill(
        state,
        "p1",
        "change_suit",
        {"from_tile": "3条", "to_suit": "筒"},
        create_skill_registry(),
    )

    assert len(state.players["p1"].hand) == before_count
    assert Tile("tiao", 3) not in state.players["p1"].hand
    assert Tile("tong", 3) in state.players["p1"].hand


def test_wish_tile_cannot_be_used_after_player_has_drawn() -> None:
    state = make_playing_state()
    state.players["p1"].skills = ["wish_tile"]
    assert state.current_turn_has_drawn is True

    try:
        use_skill(state, "p1", "wish_tile", {"tile": "5筒"}, create_skill_registry())
    except ValueError as exc:
        assert "已经摸过牌" in str(exc)
    else:
        raise AssertionError("wish_tile should be rejected after draw")


def test_stealth_gang_uses_three_same_tiles_plus_desired_tile_without_limit() -> None:
    state = make_playing_state()
    state.players["p1"].skills = ["stealth_gang"]
    state.players["p1"].hand = [
        Tile("wan", 5),
        Tile("wan", 5),
        Tile("wan", 5),
        *state.players["p1"].hand[:11],
    ]

    state = use_skill(
        state,
        "p1",
        "stealth_gang",
        {"triplet_tile": "5万", "extra_tile": "9筒"},
        create_skill_registry(),
    )

    meld = state.players["p1"].melds[-1]
    assert meld.type == "concealed_gang"
    assert meld.tiles == [Tile("wan", 5), Tile("wan", 5), Tile("wan", 5), Tile("tong", 9)]
    assert state.players["p1"].skill_usage["stealth_gang"] == 1

    state.players["p1"].hand = [
        Tile("wan", 6),
        Tile("wan", 6),
        Tile("wan", 6),
        *state.players["p1"].hand,
    ]
    state = use_skill(
        state,
        "p1",
        "stealth_gang",
        {"triplet_tile": "6万", "extra_tile": "1条"},
        create_skill_registry(),
    )

    assert len(state.players["p1"].melds) == 2
    assert state.players["p1"].skill_usage["stealth_gang"] == 2


def test_steal_concealed_gang_can_be_used_multiple_times_on_different_gangs() -> None:
    state = make_playing_state()
    state.players["p1"].skills = ["steal_concealed_gang"]
    state.players["p1"].hand = [Tile("wan", 1), Tile("wan", 2), *state.players["p1"].hand]
    state.players["p2"].melds = [
        Meld(type="concealed_gang", tiles=[Tile("tong", 3)] * 4, concealed=True),
        Meld(type="concealed_gang", tiles=[Tile("tiao", 4)] * 4, concealed=True),
    ]

    state = use_skill(
        state,
        "p1",
        "steal_concealed_gang",
        {"target_player_id": "p2", "your_tile": "1万"},
        create_skill_registry(),
    )
    state = use_skill(
        state,
        "p1",
        "steal_concealed_gang",
        {"target_player_id": "p2", "your_tile": "2万"},
        create_skill_registry(),
    )

    assert state.players["p1"].skill_usage["steal_concealed_gang"] == 2
    assert all(meld.stolen for meld in state.players["p2"].melds)
