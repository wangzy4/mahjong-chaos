import pytest

from backend.app.api.routes import _public_room_view
from backend.app.rooms.manager import InvalidActionError, RoomManager
from core.skills.new_skills import SKILL_IDS, create_skill_registry


def make_manager() -> RoomManager:
    return RoomManager(registry=create_skill_registry(), seed=1)


def start_skill_selection_game() -> tuple[RoomManager, str]:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")
    manager.join_room(room_id, "p2", "南风")
    manager.join_room(room_id, "p3", "西风")
    manager.join_room(room_id, "p4", "北风")
    manager.start_game(room_id, "p1")
    return manager, room_id


def select_first_two_for_all_players(manager: RoomManager, room_id: str) -> None:
    room = manager.get_room(room_id)
    assert room.game_state is not None
    for player_id in room.game_state.player_order:
        candidates = room.game_state.players[player_id].skill_candidates
        manager.handle_action(
            room_id,
            player_id,
            {"type": "select_skills", "skill_ids": candidates[:2]},
        )


def test_registry_contains_only_new_twelve_skills() -> None:
    registry = create_skill_registry()

    assert {skill.id for skill in registry.list_skills()} == set(SKILL_IDS)
    assert registry.get("peek_wall") is None
    assert registry.get("seal_peng") is None
    assert registry.get("double_score") is None


def test_start_game_enters_skill_selection_and_deals_three_candidates() -> None:
    manager, room_id = start_skill_selection_game()
    room = manager.get_room(room_id)

    assert room.game_state is not None
    assert room.game_state.phase == "skill_selection"
    for player in room.game_state.players.values():
        assert len(player.skill_candidates) == 3
        assert set(player.skill_candidates) <= set(SKILL_IDS)
        assert player.skills == []


def test_select_skills_requires_two_candidates_and_finishes_phase() -> None:
    manager, room_id = start_skill_selection_game()
    room = manager.get_room(room_id)
    assert room.game_state is not None
    p1_candidates = room.game_state.players["p1"].skill_candidates

    with pytest.raises(InvalidActionError):
        manager.handle_action(
            room_id,
            "p1",
            {"type": "select_skills", "skill_ids": [p1_candidates[0], "peek_wall"]},
        )

    select_first_two_for_all_players(manager, room_id)
    assert room.game_state.phase == "playing"
    assert all(len(player.skills) == 2 for player in room.game_state.players.values())


def test_cannot_discard_before_skill_selection_finished() -> None:
    manager, room_id = start_skill_selection_game()
    room = manager.get_room(room_id)
    assert room.game_state is not None
    tile = room.game_state.players["p1"].hand[0]

    with pytest.raises(InvalidActionError, match="游戏不在进行中"):
        manager.handle_action(room_id, "p1", {"type": "discard", "tile": tile})


def test_public_view_hides_other_players_skill_candidates() -> None:
    manager, room_id = start_skill_selection_game()
    room = manager.get_room(room_id)
    assert room.game_state is not None

    view = _public_room_view(room, "p1")

    p1_view = next(player for player in view["players"] if player["player_id"] == "p1")
    p2_view = next(player for player in view["players"] if player["player_id"] == "p2")
    assert len(p1_view["skill_candidates"]) == 3
    assert p2_view["skill_candidates"] == []
    assert p2_view["skill_selected"] is False


def test_astrology_result_is_private_and_does_not_change_wall() -> None:
    manager, room_id = start_skill_selection_game()
    room = manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.players["p1"].skill_candidates = ["astrology", "wish_tile", "change_suit"]
    room.game_state.players["p2"].skill_candidates = ["astrology", "wish_tile", "change_suit"]
    room.game_state.players["p3"].skill_candidates = ["astrology", "wish_tile", "change_suit"]
    room.game_state.players["p4"].skill_candidates = ["astrology", "wish_tile", "change_suit"]
    select_first_two_for_all_players(manager, room_id)
    wall_before = list(room.game_state.wall)

    manager.handle_action(room_id, "p1", {"type": "use_skill", "skill_id": "astrology"})

    p1_view = _public_room_view(room, "p1")
    p2_view = _public_room_view(room, "p2")
    assert room.game_state.wall == wall_before
    assert len(p1_view["private_data"]["private_skill_results"][-1]["tiles"]) == 4
    assert p2_view["private_data"] == {}
