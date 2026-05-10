from dataclasses import dataclass

import pytest

from backend.app.rooms.manager import (
    InvalidActionError,
    PlayerNotInRoomError,
    RoomFullError,
    RoomManager,
)
from core.mahjong.game_state import GameState
from core.mahjong.tile import Tile, sort_tiles
from core.skills.registry import SkillRegistry


@dataclass(frozen=True, slots=True)
class DummySkill:
    id: str = "dummy"
    name: str = "测试技能"
    description: str = "用于房间管理测试"
    timing: str = "manual"
    max_uses_per_game: int = 99

    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return True

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        state.action_log.append({"type": "dummy_skill_applied", "player_id": player_id})
        return state


def make_manager() -> RoomManager:
    registry = SkillRegistry()
    registry.register(DummySkill())
    return RoomManager(registry=registry, seed=1)


def fill_room(manager: RoomManager) -> str:
    room_id = manager.create_room("p1", "东风")
    manager.join_room(room_id, "p2", "南风")
    manager.join_room(room_id, "p3", "西风")
    manager.join_room(room_id, "p4", "北风")
    return room_id


def test_create_room_success() -> None:
    manager = make_manager()

    room_id = manager.create_room("p1", "东风")
    room = manager.get_room(room_id)

    assert room.room_id == room_id
    assert room.players == {"p1": "东风"}
    assert room.status == "waiting"


def test_join_room_success() -> None:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")

    room = manager.join_room(room_id, "p2", "南风")

    assert room.players["p2"] == "南风"


def test_join_room_fails_when_room_has_more_than_four_players() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    with pytest.raises(RoomFullError):
        manager.join_room(room_id, "p5", "白板")


def test_leave_room_removes_player_while_waiting() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    room = manager.leave_room(room_id, "p2")

    assert "p2" not in room.players
    assert len(room.players) == 3


def test_host_leave_transfers_host_to_next_player() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    room = manager.leave_room(room_id, "p1")

    assert "p1" not in room.players
    assert room.host_player_id == "p2"


def test_leave_room_rejects_during_game() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    manager.start_game(room_id, "p1")

    with pytest.raises(InvalidActionError, match="游戏进行中"):
        manager.leave_room(room_id, "p2")


def test_host_can_kick_member_while_waiting() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    room = manager.kick_player(room_id, "p1", "p3")

    assert "p3" not in room.players
    assert len(room.players) == 3


def test_non_host_cannot_kick_member() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    with pytest.raises(InvalidActionError, match="只有房主"):
        manager.kick_player(room_id, "p2", "p3")


def test_kick_rejects_missing_player() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    with pytest.raises(PlayerNotInRoomError):
        manager.kick_player(room_id, "p1", "p5")


def test_kick_rejects_during_game() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    manager.start_game(room_id, "p1")

    with pytest.raises(InvalidActionError, match="游戏进行中"):
        manager.kick_player(room_id, "p1", "p2")


def test_start_game_fails_with_one_player() -> None:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")

    with pytest.raises(InvalidActionError, match="至少需要 2 名玩家"):
        manager.start_game(room_id, "p1")


def test_start_game_under_four_players_requires_host_confirmation() -> None:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")
    manager.join_room(room_id, "p2", "南风")

    with pytest.raises(InvalidActionError, match="需要房主确认"):
        manager.start_game(room_id, "p1")


def test_start_game_under_four_players_success_after_host_confirmation() -> None:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")
    manager.join_room(room_id, "p2", "南风")

    room = manager.start_game(room_id, "p1", confirm_underfilled=True)

    assert room.status == "playing"
    assert room.game_state is not None
    assert room.game_state.player_order == ["p1", "p2"]


def test_only_host_can_start_game() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    with pytest.raises(InvalidActionError, match="只有房主"):
        manager.start_game(room_id, "p2")


def test_start_game_success_when_room_is_full() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    room = manager.start_game(room_id, "p1")

    assert room.status == "playing"
    assert room.game_state is not None
    assert room.game_state.phase == "playing"


def test_start_game_assigns_one_skill_to_each_player() -> None:
    manager = make_manager()
    room_id = fill_room(manager)

    room = manager.start_game(room_id, "p1")

    assert room.game_state is not None
    assert [len(player.skills) for player in room.game_state.players.values()] == [1, 1, 1, 1]
    assert {player.skills[0] for player in room.game_state.players.values()} == {"dummy"}


def test_non_host_can_ready_after_game_finished() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    room.status = "finished"

    room = manager.ready_for_next_game(room_id, "p2")

    assert room.ready_player_ids == {"p2"}


def test_host_cannot_ready_after_game_finished() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    room.status = "finished"

    with pytest.raises(InvalidActionError, match="房主不需要准备"):
        manager.ready_for_next_game(room_id, "p1")


def test_restart_requires_all_non_host_players_ready() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    room.status = "finished"
    manager.ready_for_next_game(room_id, "p2")
    manager.ready_for_next_game(room_id, "p3")

    with pytest.raises(InvalidActionError, match="还有玩家未准备：p4"):
        manager.restart_game(room_id, "p1")


def test_host_can_restart_after_all_non_host_players_ready() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    room.status = "finished"
    old_state = room.game_state
    manager.ready_for_next_game(room_id, "p2")
    manager.ready_for_next_game(room_id, "p3")
    manager.ready_for_next_game(room_id, "p4")

    room = manager.restart_game(room_id, "p1")

    assert room.status == "playing"
    assert room.ready_player_ids == set()
    assert room.game_state is not old_state
    assert room.game_state is not None
    assert room.game_state.action_log[-1]["type"] == "restart_game"


def test_restart_under_four_players_requires_host_confirmation() -> None:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")
    manager.join_room(room_id, "p2", "南风")
    room = manager.start_game(room_id, "p1", confirm_underfilled=True)
    room.status = "finished"
    manager.ready_for_next_game(room_id, "p2")

    with pytest.raises(InvalidActionError, match="需要房主确认"):
        manager.restart_game(room_id, "p1")


def test_restart_allows_under_four_players_after_host_confirmation() -> None:
    manager = make_manager()
    room_id = manager.create_room("p1", "东风")
    manager.join_room(room_id, "p2", "南风")
    room = manager.start_game(room_id, "p1", confirm_underfilled=True)
    room.status = "finished"
    manager.ready_for_next_game(room_id, "p2")

    room = manager.restart_game(room_id, "p1", confirm_underfilled=True)

    assert room.status == "playing"
    assert room.game_state is not None
    assert room.game_state.player_order == ["p1", "p2"]


def test_handle_action_rejects_manual_draw() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None
    current_player_id = room.game_state.current_player_id

    with pytest.raises(InvalidActionError, match="自动进行"):
        manager.handle_action(room_id, current_player_id, {"type": "draw"})


def test_handle_action_can_call_discard_and_use_skill() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None
    current_player_id = room.game_state.current_player_id

    tile = room.game_state.players[current_player_id].hand[0]
    room = manager.handle_action(room_id, current_player_id, {"type": "discard", "tile": tile})
    assert room.game_state is not None
    assert room.game_state.players[current_player_id].discard_pile[-1] == tile

    next_player_id = room.game_state.current_player_id
    room = manager.handle_action(
        room_id,
        next_player_id,
        {"type": "use_skill", "skill_id": "dummy", "params": {}},
    )
    assert room.game_state is not None
    assert room.game_state.skill_usage[next_player_id]["dummy"].used_count == 1
    assert room.game_state.action_log[-1]["type"] == "use_skill"


def test_handle_action_can_call_peng() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None
    discard = Tile("wan", 1)
    room.game_state.players["p1"].hand = [discard, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].hand = [
        discard,
        discard,
        *without_tile(room.game_state.players["p2"].hand, discard)[:11],
    ]
    room.game_state.players["p3"].hand = without_tile(room.game_state.players["p3"].hand, discard)
    room.game_state.players["p4"].hand = without_tile(room.game_state.players["p4"].hand, discard)

    room = manager.handle_action(room_id, "p1", {"type": "discard", "tile": discard})
    room = manager.handle_action(room_id, "p2", {"type": "peng"})

    assert room.game_state is not None
    assert room.game_state.current_player_id == "p2"
    meld = room.game_state.players["p2"].melds[0]
    assert meld.type == "peng"
    assert meld.tiles == [discard, discard, discard]


def test_claim_priority_blocks_chi_when_any_player_can_peng() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None
    discard = Tile("wan", 1)
    room.game_state.players["p1"].hand = [discard, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].hand = [
        Tile("wan", 2),
        Tile("wan", 3),
        *without_tile(room.game_state.players["p2"].hand, discard)[:11],
    ]
    room.game_state.players["p3"].hand = [
        discard,
        discard,
        *without_tile(room.game_state.players["p3"].hand, discard)[:11],
    ]
    room.game_state.players["p4"].hand = without_tile(room.game_state.players["p4"].hand, discard)
    manager.handle_action(room_id, "p1", {"type": "discard", "tile": discard})

    with pytest.raises(InvalidActionError, match="先处理碰牌"):
        manager.handle_action(
            room_id,
            "p2",
            {"type": "chi", "tiles": [discard, Tile("wan", 2), Tile("wan", 3)]},
        )


def test_claim_priority_blocks_peng_when_any_player_can_gang() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None
    discard = Tile("wan", 1)
    room.game_state.players["p1"].hand = [discard, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].hand = [
        discard,
        discard,
        *without_tile(room.game_state.players["p2"].hand, discard)[:11],
    ]
    room.game_state.players["p3"].hand = [
        discard,
        discard,
        discard,
        *room.game_state.players["p3"].hand[:10],
    ]
    manager.handle_action(room_id, "p1", {"type": "discard", "tile": discard})

    with pytest.raises(InvalidActionError, match="先处理杠牌"):
        manager.handle_action(room_id, "p2", {"type": "peng"})


def test_claim_priority_blocks_gang_when_any_player_can_hu() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None
    discard = Tile("wan", 9)
    room.game_state.players["p1"].hand = [discard, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].hand = [
        discard,
        discard,
        discard,
        *room.game_state.players["p2"].hand[:10],
    ]
    room.game_state.players["p3"].hand = [
        Tile("wan", 1),
        Tile("wan", 2),
        Tile("wan", 3),
        Tile("wan", 4),
        Tile("wan", 5),
        Tile("wan", 6),
        Tile("tong", 2),
        Tile("tong", 3),
        Tile("tong", 4),
        Tile("tiao", 7),
        Tile("tiao", 8),
        Tile("tiao", 9),
        Tile("wan", 9),
    ]
    manager.handle_action(room_id, "p1", {"type": "discard", "tile": discard})

    with pytest.raises(InvalidActionError, match="先处理胡牌"):
        manager.handle_action(
            room_id,
            "p2",
            {"type": "gang", "gang_type": "exposed_gang", "tile": discard},
        )


def test_set_auto_sort_hand_can_disable_and_enable_sorting() -> None:
    manager = make_manager()
    room_id = fill_room(manager)
    room = manager.start_game(room_id, "p1")
    assert room.game_state is not None

    room = manager.set_auto_sort_hand(room_id, "p1", False)
    assert room.game_state is not None
    assert not room.game_state.players["p1"].auto_sort_hand

    sorted_hand = sort_tiles(room.game_state.players["p1"].hand)
    room.game_state.players["p1"].hand = list(reversed(sorted_hand))
    unsorted_hand = list(room.game_state.players["p1"].hand)
    room = manager.set_auto_sort_hand(room_id, "p1", True)

    assert room.game_state is not None
    assert room.game_state.players["p1"].auto_sort_hand
    assert room.game_state.players["p1"].hand == sort_tiles(unsorted_hand)


def without_tile(tiles: list[Tile], tile: Tile) -> list[Tile]:
    return [hand_tile for hand_tile in tiles if hand_tile != tile]
