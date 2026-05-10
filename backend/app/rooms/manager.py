import random
from uuid import uuid4

from backend.app.rooms.room import Room
from core.mahjong.actions import (
    chi_tile,
    confirm_discard,
    discard_tile,
    gang_tile,
    pass_peng,
    peng_tile,
    select_skills,
    use_skill,
)
from core.mahjong.actions import (
    start_game as start_core_game,
)
from core.mahjong.hu_checker import can_hu_with_melds
from core.mahjong.scoring import settle_win
from core.mahjong.tile import Tile, parse_tile, sort_tiles, tile_to_str
from core.skills.registry import SkillRegistry


class RoomError(ValueError):
    pass


class RoomNotFoundError(RoomError):
    pass


class RoomFullError(RoomError):
    pass


class PlayerNotInRoomError(RoomError):
    pass


class GameNotStartedError(RoomError):
    pass


class GameAlreadyStartedError(RoomError):
    pass


class InvalidActionError(RoomError):
    pass


class InvalidRoomActionError(InvalidActionError):
    pass


class RoomManager:
    def __init__(self, registry: SkillRegistry, seed: int | None = None) -> None:
        self._rooms: dict[str, Room] = {}
        self._registry = registry
        self._random = random.Random(seed)

    def create_room(self, host_player_id: str, host_name: str) -> str:
        room_id = uuid4().hex[:8]
        self._rooms[room_id] = Room(
            room_id=room_id,
            host_player_id=host_player_id,
            players={host_player_id: host_name},
        )
        return room_id

    def join_room(self, room_id: str, player_id: str, player_name: str) -> Room:
        room = self.get_room(room_id)
        if room.status != "waiting":
            if player_id in room.players:
                room.players[player_id] = player_name
                return room
            raise GameAlreadyStartedError("游戏已经开始，暂时不允许新玩家加入")
        if player_id in room.players:
            room.players[player_id] = player_name
            return room
        if len(room.players) >= 4:
            raise RoomFullError("房间已满")

        room.players[player_id] = player_name
        return room

    def _ensure_room_can_change_members(self, room: Room) -> None:
        if room.status not in {"waiting", "finished"}:
            raise InvalidActionError("游戏进行中不能变更房间成员")

    def set_ready(self, room_id: str, player_id: str, ready: bool = True) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        if room.status == "waiting":
            if ready:
                room.ready_player_ids.add(player_id)
            else:
                room.ready_player_ids.discard(player_id)
            return room
        if room.status == "finished":
            if player_id == room.host_player_id:
                raise InvalidActionError("房主不需要准备，请使用重新开始")
            if ready:
                room.ready_player_ids.add(player_id)
            else:
                room.ready_player_ids.discard(player_id)
            return room
        raise InvalidActionError("游戏进行中不能修改准备状态")

    def leave_room(self, room_id: str, player_id: str) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        self._ensure_room_can_change_members(room)

        self._remove_player_from_room(room, player_id)
        return room

    def kick_player(self, room_id: str, host_player_id: str, target_player_id: str) -> Room:
        room = self.get_room(room_id)
        if host_player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        if target_player_id not in room.players:
            raise PlayerNotInRoomError("要踢出的玩家不在房间内")
        if host_player_id != room.host_player_id:
            raise InvalidActionError("只有房主可以踢出房间成员")
        if target_player_id == room.host_player_id:
            raise InvalidActionError("房主不能踢出自己，请使用离开房间")
        self._ensure_room_can_change_members(room)

        self._remove_player_from_room(room, target_player_id)
        return room

    def start_game(self, room_id: str, player_id: str, confirm_underfilled: bool = False) -> Room:
        room = self.get_room(room_id)
        if room.status != "waiting":
            raise InvalidActionError("房间不在等待状态")
        if player_id != room.host_player_id:
            raise InvalidActionError("只有房主可以开始游戏")
        if len(room.players) < 2:
            raise InvalidActionError("至少需要 2 名玩家才能开始游戏")
        if len(room.players) < 4 and not confirm_underfilled:
            raise InvalidActionError("当前少于 4 名玩家，需要房主确认后才能开始")
        if room.ready_player_ids:
            missing_ready_player_ids = [
                ready_player_id
                for ready_player_id in room.players
                if ready_player_id not in room.ready_player_ids
            ]
            if missing_ready_player_ids:
                missing = "、".join(missing_ready_player_ids)
                raise InvalidActionError(f"还有玩家未准备：{missing}")

        skills = self._registry.list_skills()
        if not skills:
            raise InvalidActionError("还没有注册任何技能")

        player_ids = list(room.players)
        state = start_core_game(
            room_id=room.room_id,
            player_ids=player_ids,
            player_names=room.players,
        )
        self._assign_starting_skills(state, skills)
        room.game_state = state
        room.status = "playing"
        room.ready_player_ids.clear()
        return room

    def ready_for_next_game(self, room_id: str, player_id: str) -> Room:
        return self.set_ready(room_id, player_id, True)

    def restart_game(
        self,
        room_id: str,
        player_id: str,
        confirm_underfilled: bool = False,
    ) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        if room.status != "finished":
            raise InvalidActionError("只有本局结束后才能重新开始")
        if player_id != room.host_player_id:
            raise InvalidActionError("只有房主可以重新开始")
        if len(room.players) < 2:
            raise InvalidActionError("至少需要 2 名玩家才能重新开始")
        if len(room.players) < 4 and not confirm_underfilled:
            raise InvalidActionError("当前少于 4 名玩家，需要房主确认后才能重新开始")

        missing_ready_player_ids = [
            ready_player_id
            for ready_player_id in room.players
            if ready_player_id != room.host_player_id
            and ready_player_id not in room.ready_player_ids
        ]
        if missing_ready_player_ids:
            missing = "、".join(missing_ready_player_ids)
            raise InvalidActionError(f"还有玩家未准备：{missing}")

        return self._start_new_game_without_underfilled_confirmation(room)

    def get_room(self, room_id: str) -> Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise RoomNotFoundError("房间不存在")
        return room

    def mark_connected(self, room_id: str, player_id: str) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        room.connected_player_ids.add(player_id)
        return room

    def mark_disconnected(self, room_id: str, player_id: str) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        room.connected_player_ids.discard(player_id)
        return room

    def get_public_view(self, room_id: str, viewer_id: str) -> dict:
        room = self.get_room(room_id)
        if viewer_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")

        from backend.app.api.routes import _public_room_view

        return _public_room_view(room, viewer_id)

    def handle_action(self, room_id: str, player_id: str, action: dict) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        if room.game_state is None or room.status != "playing":
            raise GameNotStartedError("游戏尚未开始")

        action_type = action.get("type")
        try:
            if action_type == "draw":
                raise InvalidActionError("摸牌已改为自动进行，请出牌或胡牌")
            elif action_type == "discard":
                room.game_state = discard_tile(
                    room.game_state,
                    player_id,
                    _action_tile(action),
                )
            elif action_type == "peng":
                self._ensure_claim_priority_allows(room.game_state, player_id, "peng")
                room.game_state = peng_tile(room.game_state, player_id)
            elif action_type == "chi":
                tiles = action.get("tiles")
                if not isinstance(tiles, list):
                    raise InvalidActionError("缺少吃牌组合")
                self._ensure_claim_priority_allows(room.game_state, player_id, "chi")
                room.game_state = chi_tile(
                    room.game_state,
                    player_id,
                    [_parse_action_tile(tile) for tile in tiles],
                )
            elif action_type == "gang":
                gang_type = action.get("gang_type")
                if not isinstance(gang_type, str):
                    raise InvalidActionError("缺少杠类型")
                if gang_type == "exposed_gang":
                    self._ensure_claim_priority_allows(room.game_state, player_id, "gang")
                room.game_state = gang_tile(
                    room.game_state,
                    player_id,
                    gang_type,
                    _action_tile(action),
                )
            elif action_type == "select_skills":
                skill_ids = action.get("skill_ids")
                if not isinstance(skill_ids, list):
                    raise InvalidActionError("缺少要选择的技能列表")
                room.game_state = select_skills(
                    room.game_state,
                    player_id,
                    [str(skill_id) for skill_id in skill_ids],
                )
            elif action_type == "confirm_discard":
                confirm = action.get("confirm")
                if not isinstance(confirm, bool):
                    raise InvalidActionError("缺少确认结果")
                room.game_state = confirm_discard(room.game_state, player_id, confirm)
            elif action_type == "pass_peng":
                room.game_state = pass_peng(room.game_state, player_id)
            elif action_type == "pass":
                room.game_state = pass_peng(room.game_state, player_id)
            elif action_type == "hu":
                self._ensure_claim_priority_allows(room.game_state, player_id, "hu")
                room.game_state = self._handle_hu(room.game_state, player_id)
                room.status = "finished"
            elif action_type == "hu_on_discard":
                self._ensure_claim_priority_allows(room.game_state, player_id, "hu")
                if (
                    room.game_state.last_discard is None
                    or not room.game_state.last_discard.available_for_claim
                    or room.game_state.last_discard.player_id == player_id
                ):
                    raise InvalidActionError("当前没有可以点炮胡的弃牌")
                room.game_state = self._handle_hu(room.game_state, player_id)
                room.status = "finished"
            elif action_type == "use_skill":
                skill_id = action.get("skill_id")
                if not isinstance(skill_id, str):
                    raise InvalidActionError("缺少技能 ID")
                params = action.get("params", {})
                if not isinstance(params, dict):
                    raise InvalidActionError("技能参数必须是对象")
                room.game_state = use_skill(
                    room.game_state,
                    player_id,
                    skill_id,
                    params,
                    self._registry,
                )
            else:
                raise InvalidActionError(f"不支持的操作类型：{action_type}")
        except RoomError:
            raise
        except ValueError as exc:
            raise InvalidActionError(str(exc)) from exc

        return room

    def set_auto_sort_hand(self, room_id: str, player_id: str, enabled: bool) -> Room:
        room = self.get_room(room_id)
        if player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        if room.game_state is None:
            raise GameNotStartedError("游戏尚未开始")

        player = room.game_state.players[player_id]
        player.auto_sort_hand = enabled
        if enabled:
            player.hand = sort_tiles(player.hand)
        room.game_state.action_log.append(
            {
                "type": "set_auto_sort_hand",
                "player_id": player_id,
                "enabled": enabled,
            }
        )
        return room

    def _handle_hu(self, state, player_id: str):
        player = state.players[player_id]
        win_type = "self_draw"
        from_player_id = None
        claimed_tile = None
        winning_hand = list(player.hand)

        if (
            state.last_discard is not None
            and state.last_discard.available_for_claim
            and state.last_discard.player_id != player_id
        ):
            win_type = "discard"
            from_player_id = state.last_discard.player_id
            claimed_tile = state.last_discard.tile
            winning_hand.append(claimed_tile)

        if not can_hu_with_melds(winning_hand, player.melds):
            raise InvalidActionError("当前手牌不能胡")

        state.winner_id = player_id
        state.loser_id = from_player_id
        state.win_type = win_type
        state.winning_tile = claimed_tile
        state.phase = "finished"
        if state.last_discard is not None:
            state.last_discard.available_for_claim = False
            state.last_discard = None
        state.action_log.append(
            {
                "type": "hu",
                "player_id": player_id,
                "win_type": win_type,
                "from_player_id": from_player_id,
                "claimed_tile": tile_to_str(claimed_tile) if claimed_tile else None,
            }
        )
        state = settle_win(
            state,
            winner_id=player_id,
            win_type=state.win_type,
            loser_id=from_player_id,
            winning_tile=claimed_tile,
        )
        return state

    def _ensure_claim_priority_allows(
        self,
        state,
        player_id: str,
        action_type: str,
    ) -> None:
        if state.last_discard is None or not state.last_discard.available_for_claim:
            return

        if action_type != "hu" and self._claimable_hu_player_ids(state):
            raise InvalidActionError("有玩家可以胡，必须先处理胡牌")
        if action_type in {"peng", "chi"} and self._claimable_gang_player_ids(state):
            raise InvalidActionError("有玩家可以杠，必须先处理杠牌")
        if action_type == "chi":
            peng_player_ids = self._claimable_peng_player_ids(state)
            if peng_player_ids:
                raise InvalidActionError("有玩家可以碰，必须先处理碰牌")

    def _claimable_hu_player_ids(self, state) -> list[str]:
        last_discard = state.last_discard
        if last_discard is None or not last_discard.available_for_claim:
            return []

        claimable_player_ids = []
        for other_player_id, player in state.players.items():
            if other_player_id == last_discard.player_id:
                continue
            if can_hu_with_melds([*player.hand, last_discard.tile], player.melds):
                claimable_player_ids.append(other_player_id)
        return claimable_player_ids

    def _claimable_gang_player_ids(self, state) -> list[str]:
        last_discard = state.last_discard
        if last_discard is None or not last_discard.available_for_claim:
            return []

        return [
            other_player_id
            for other_player_id, player in state.players.items()
            if other_player_id != last_discard.player_id
            and player.hand.count(last_discard.tile) >= 3
        ]

    def _claimable_peng_player_ids(self, state) -> list[str]:
        last_discard = state.last_discard
        if last_discard is None or not last_discard.available_for_claim:
            return []

        return [
            other_player_id
            for other_player_id, player in state.players.items()
            if other_player_id != last_discard.player_id
            and other_player_id not in state.sealed_peng_player_ids
            and player.hand.count(last_discard.tile) >= 2
        ]

    def _start_new_game_without_underfilled_confirmation(self, room: Room) -> Room:
        skills = self._registry.list_skills()
        if not skills:
            raise InvalidActionError("还没有注册任何技能")

        previous_scores = dict(room.game_state.scores) if room.game_state is not None else {}
        state = start_core_game(
            room_id=room.room_id,
            player_ids=list(room.players),
            player_names=room.players,
        )
        if previous_scores:
            state.scores = {
                player_id: previous_scores.get(player_id, 0)
                for player_id in state.player_order
            }
            state.round_score_delta = {player_id: 0 for player_id in state.player_order}
        self._assign_starting_skills(state, skills)
        state.action_log.append(
            {
                "type": "restart_game",
                "player_id": room.host_player_id,
                "player_ids": list(room.players),
            }
        )
        room.game_state = state
        room.status = "playing"
        room.ready_player_ids.clear()
        return room

    def _remove_player_from_room(self, room: Room, player_id: str) -> None:
        del room.players[player_id]
        room.ready_player_ids.discard(player_id)
        room.connected_player_ids.discard(player_id)

        if room.game_state is not None and room.status == "finished":
            room.game_state.players.pop(player_id, None)
            if player_id in room.game_state.player_order:
                room.game_state.player_order.remove(player_id)
            room.game_state.scores.pop(player_id, None)
            room.game_state.round_score_delta.pop(player_id, None)
            room.game_state.turn_counts.pop(player_id, None)
            room.game_state.player_effects.pop(player_id, None)
            room.game_state.river_recycle_usage.pop(player_id, None)

        if player_id == room.host_player_id and room.players:
            room.host_player_id = next(iter(room.players))
        if not room.players:
            self._rooms.pop(room.room_id, None)

    def _assign_starting_skills(self, state, skills) -> None:
        if len(skills) < 3:
            for player in state.players.values():
                player.skills = [skill.id for skill in skills]
            state.phase = "playing"
            return
        for player in state.players.values():
            player.skill_candidates = [skill.id for skill in self._random.sample(skills, k=3)]
        state.phase = "skill_selection"


def _action_tile(action: dict) -> Tile:
    tile = action.get("tile")
    return _parse_action_tile(tile)


def _parse_action_tile(tile) -> Tile:
    if isinstance(tile, Tile):
        return tile
    if isinstance(tile, str):
        return parse_tile(tile)
    raise InvalidActionError("缺少要出的牌")
