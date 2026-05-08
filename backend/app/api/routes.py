from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from backend.app.rooms.manager import (
    GameAlreadyStartedError,
    GameNotStartedError,
    InvalidActionError,
    PlayerNotInRoomError,
    RoomFullError,
    RoomManager,
    RoomNotFoundError,
)
from backend.app.rooms.room import Room
from backend.app.websocket.connection_manager import ConnectionManager
from core.mahjong.game_state import GameState
from core.mahjong.hu_checker import can_hu_with_melds
from core.mahjong.tile import tile_to_str
from core.skills.new_skills import create_skill_registry


class CreateRoomRequest(BaseModel):
    player_id: str = Field(min_length=1, title="玩家 ID", description="创建房间的玩家唯一标识。")
    name: str = Field(min_length=1, title="玩家昵称", description="创建房间的玩家显示名称。")

    model_config = {
        "json_schema_extra": {
            "examples": [{"player_id": "p1", "name": "Alice"}],
        },
    }


class JoinRoomRequest(BaseModel):
    player_id: str = Field(min_length=1, title="玩家 ID", description="加入房间的玩家唯一标识。")
    name: str = Field(min_length=1, title="玩家昵称", description="加入房间的玩家显示名称。")

    model_config = {
        "json_schema_extra": {
            "examples": [{"player_id": "p2", "name": "Bob"}],
        },
    }


class StartRoomRequest(BaseModel):
    player_id: str = Field(
        min_length=1,
        title="玩家 ID",
        description="发起开局的玩家 ID，必须是房主。",
    )
    confirm_underfilled: bool = Field(
        default=False,
        title="确认少人开局",
        description="当房间人数为 2-3 人时，房主需要传 true 才能正式开始。",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"player_id": "p1", "confirm_underfilled": True}],
        },
    }


class PlayerRoomRequest(BaseModel):
    player_id: str = Field(min_length=1, title="玩家 ID", description="执行房间操作的玩家 ID。")

    model_config = {
        "json_schema_extra": {
            "examples": [{"player_id": "p2"}],
        },
    }


class ReadyRoomRequest(PlayerRoomRequest):
    ready: bool = Field(
        default=True,
        title="是否准备",
        description="true 表示准备，false 表示取消准备。",
    )


class RestartRoomRequest(BaseModel):
    player_id: str = Field(min_length=1, title="玩家 ID", description="执行重新开始的房主玩家 ID。")
    confirm_underfilled: bool = Field(
        default=False,
        title="确认少人重新开始",
        description="当房间人数为 2-3 人时，房主需要传 true 才能重新开始。",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"player_id": "p1", "confirm_underfilled": True}],
        },
    }


class ActionRequest(BaseModel):
    player_id: str = Field(min_length=1, title="玩家 ID", description="执行操作的玩家 ID。")
    type: str = Field(
        min_length=1,
        title="操作类型",
        description="支持 discard、hu、peng、chi、gang、pass_peng、use_skill。",
    )
    tile: str | None = Field(
        default=None,
        title="单张牌",
        description="出牌或杠牌时使用，例如 3万。",
    )
    tiles: list[str] | None = Field(
        default=None,
        title="多张牌",
        description="吃牌时传入三张牌，包含刚打出的牌和自己手里的两张牌。",
    )
    gang_type: str | None = Field(
        default=None,
        title="杠牌类型",
        description="支持 concealed_gang、exposed_gang、added_gang。",
    )
    skill_id: str | None = Field(
        default=None,
        title="技能 ID",
        description="使用技能时传入技能 ID。",
    )
    params: dict[str, object] = Field(
        default_factory=dict,
        title="操作参数",
        description="技能等扩展操作的参数。",
    )
    skill_ids: list[str] | None = Field(default=None, title="选择的技能 ID")
    confirm: bool | None = Field(default=None, title="确认结果")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"player_id": "p1", "type": "discard", "tile": "3万"},
                {"player_id": "p2", "type": "chi", "tiles": ["3万", "1万", "2万"]},
                {"player_id": "p2", "type": "gang", "gang_type": "exposed_gang", "tile": "3万"},
            ],
        },
    }


class AutoSortHandRequest(BaseModel):
    player_id: str = Field(min_length=1, title="玩家 ID", description="修改理牌设置的玩家 ID。")
    enabled: bool = Field(title="是否开启自动理牌", description="true 表示开启，false 表示关闭。")

    model_config = {
        "json_schema_extra": {
            "examples": [{"player_id": "p1", "enabled": True}],
        },
    }


def create_default_room_manager() -> RoomManager:
    return RoomManager(registry=create_skill_registry(), seed=1)


room_manager = create_default_room_manager()
websocket_hub = ConnectionManager()
router = APIRouter(tags=["房间与对局"])

PUBLIC_ACTION_LOG_KEYS = {
    "type",
    "player_id",
    "dealer_id",
    "player_ids",
    "hand_counts",
    "wall_count",
    "result",
    "tile",
    "next_player_id",
    "hand_count",
    "discard_count",
    "skill_id",
    "used_count",
    "count",
    "auto",
    "can_hu",
    "enabled",
    "meld_count",
    "reason",
    "target_player_id",
    "selected_count",
    "reflected_player_id",
    "reflected_skill_id",
    "confirm",
    "source",
    "tiles",
    "from_player_id",
    "claimed_tile",
    "gang_type",
    "win_type",
    "winner_id",
    "loser_id",
    "winning_tile",
    "score_type",
    "label",
    "message",
    "gang_player_id",
    "base",
    "fans",
    "fan_labels",
    "fan_multiplier",
    "dealer_multiplier",
    "double_score_multiplier",
    "skill_multipliers",
    "skill_multiplier",
    "total_multiplier",
    "multiplier",
    "payments",
    "delta",
}


@router.post(
    "/rooms",
    status_code=status.HTTP_201_CREATED,
    summary="创建房间",
    description="创建一个等待中的房间，并把请求玩家设为房主。",
)
def create_room(request: CreateRoomRequest) -> dict[str, Any]:
    room_id = room_manager.create_room(request.player_id, request.name)
    room = room_manager.get_room(room_id)
    return _room_summary(room)


@router.post(
    "/rooms/{room_id}/join",
    summary="加入房间",
    description="玩家加入指定房间。房间最多 4 人，已开局房间不能继续加入。",
)
async def join_room(room_id: str, request: JoinRoomRequest) -> dict[str, Any]:
    try:
        room = room_manager.join_room(room_id, request.player_id, request.name)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RoomFullError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GameAlreadyStartedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidActionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _broadcast_room_public_views(room)
    return _room_summary(room)


@router.post(
    "/rooms/{room_id}/start",
    summary="开始游戏",
    description="房主开始游戏。2-3 人开局需要传入 confirm_underfilled=true 确认少人开局。",
)
async def start_room(room_id: str, request: StartRoomRequest) -> dict[str, Any]:
    try:
        room = room_manager.get_room(room_id)
        if request.player_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
        room = room_manager.start_game(
            room_id,
            request.player_id,
            confirm_underfilled=request.confirm_underfilled,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlayerNotInRoomError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidActionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _broadcast_room_public_views(room)
    return _room_summary(room)


@router.post(
    "/rooms/{room_id}/ready",
    summary="准备下一局",
    description="本局结束后，非房主玩家点击准备。所有非房主准备后，房主可以重新开始。",
)
async def ready_for_next_game(room_id: str, request: ReadyRoomRequest) -> dict[str, Any]:
    try:
        room = room_manager.set_ready(room_id, request.player_id, request.ready)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlayerNotInRoomError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidActionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _broadcast_room_public_views(room)
    return _public_room_view(room, request.player_id)


@router.post(
    "/rooms/{room_id}/restart",
    summary="重新开始",
    description="本局结束后，房主在所有非房主准备后重新开始下一局。2-3 人需要房主再次确认。",
)
async def restart_game(room_id: str, request: RestartRoomRequest) -> dict[str, Any]:
    try:
        room = room_manager.restart_game(
            room_id,
            request.player_id,
            confirm_underfilled=request.confirm_underfilled,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlayerNotInRoomError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidActionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _broadcast_room_public_views(room)
    return _public_room_view(room, request.player_id)


@router.post(
    "/rooms/{room_id}/actions",
    summary="执行游戏操作",
    description="提交出牌、胡牌、吃、碰、杠、跳过碰牌或使用技能等操作。服务端会校验所有规则。",
)
async def handle_room_action(room_id: str, request: ActionRequest) -> dict[str, Any]:
    action: dict[str, object] = {"type": request.type}
    if request.tile is not None:
        action["tile"] = request.tile
    if request.tiles is not None:
        action["tiles"] = request.tiles
    if request.gang_type is not None:
        action["gang_type"] = request.gang_type
    if request.skill_id is not None:
        action["skill_id"] = request.skill_id
    if request.params:
        action["params"] = request.params
    if request.skill_ids is not None:
        action["skill_ids"] = request.skill_ids
    if request.confirm is not None:
        action["confirm"] = request.confirm

    try:
        room = room_manager.handle_action(room_id, request.player_id, action)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlayerNotInRoomError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except GameNotStartedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InvalidActionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _broadcast_room_public_views(room)
    return _public_room_view(room, request.player_id)


@router.post(
    "/rooms/{room_id}/settings/auto-sort-hand",
    summary="设置自动理牌",
    description="开启或关闭指定玩家的自动理牌。开启后手牌按万、条、筒和点数排序。",
)
async def set_auto_sort_hand(room_id: str, request: AutoSortHandRequest) -> dict[str, Any]:
    try:
        room = room_manager.set_auto_sort_hand(room_id, request.player_id, request.enabled)
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlayerNotInRoomError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except GameNotStartedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _broadcast_room_public_views(room)
    return _public_room_view(room, request.player_id)


@router.get(
    "/rooms/{room_id}/state",
    summary="获取公开对局状态",
    description="获取针对 viewer_id 脱敏后的房间与对局状态。只能看到自己的手牌和私有技能结果。",
)
def get_room_state(
    room_id: str,
    viewer_id: str = Query(
        min_length=1,
        title="查看者玩家 ID",
        description="用于生成脱敏视图的玩家 ID。",
    ),
) -> dict[str, Any]:
    try:
        room = room_manager.get_room(room_id)
        if viewer_id not in room.players:
            raise PlayerNotInRoomError("玩家不在房间内")
    except RoomNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlayerNotInRoomError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return _public_room_view(room, viewer_id)


@router.websocket("/ws/rooms/{room_id}")
async def room_websocket(
    websocket: WebSocket,
    room_id: str,
    viewer_id: str = Query(min_length=1),
) -> None:
    try:
        room = room_manager.get_room(room_id)
        if viewer_id not in room.players:
            await websocket.close(code=1008)
            return
    except RoomNotFoundError:
        await websocket.close(code=1008)
        return

    room_manager.mark_connected(room_id, viewer_id)
    await websocket_hub.connect(room_id, viewer_id, websocket)
    await websocket.send_json(_public_room_view(room, viewer_id))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_hub.disconnect(room_id, viewer_id)
        room_manager.mark_disconnected(room_id, viewer_id)


@router.websocket("/ws/{room_id}/{player_id}")
async def room_action_websocket(
    websocket: WebSocket,
    room_id: str,
    player_id: str,
) -> None:
    try:
        room = room_manager.get_room(room_id)
        if player_id not in room.players:
            await websocket.close(code=1008)
            return
    except RoomNotFoundError:
        await websocket.close(code=1008)
        return

    room_manager.mark_connected(room_id, player_id)
    await websocket_hub.connect(room_id, player_id, websocket)
    await websocket.send_json({"type": "state", "data": _public_room_view(room, player_id)})
    await _broadcast_system_message(
        room_id,
        f"玩家 {player_id} 已连接",
        exclude_player_id=player_id,
    )

    try:
        while True:
            message = await websocket.receive_json()
            try:
                action = _ws_message_to_action(message)
                room = room_manager.handle_action(room_id, player_id, action)
            except (GameNotStartedError, InvalidActionError, PlayerNotInRoomError) as exc:
                await websocket_hub.send_to_player(
                    room_id,
                    player_id,
                    {"type": "error", "message": str(exc)},
                )
                continue
            await _broadcast_room_public_views(room)
    except WebSocketDisconnect:
        websocket_hub.disconnect(room_id, player_id)
        try:
            room_manager.mark_disconnected(room_id, player_id)
        except RoomNotFoundError:
            return
        await _broadcast_system_message(room_id, f"玩家 {player_id} 已断开连接")


async def _broadcast_room_public_views(room: Room) -> None:
    await websocket_hub.broadcast_room(
        room.room_id,
        lambda viewer_id: {
            "type": "state",
            "data": _public_room_view(room, viewer_id),
        },
    )


async def _broadcast_system_message(
    room_id: str,
    message: str,
    exclude_player_id: str | None = None,
) -> None:
    await websocket_hub.broadcast_room(
        room_id,
        lambda viewer_id: None
        if viewer_id == exclude_player_id
        else {"type": "system", "message": message},
    )


def _ws_message_to_action(message: dict[str, Any]) -> dict[str, Any]:
    action_type = message.get("type")
    if not isinstance(action_type, str) or not action_type:
        raise InvalidActionError("WebSocket 消息缺少 type")
    payload = message.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise InvalidActionError("WebSocket payload 必须是对象")

    action: dict[str, Any] = {"type": action_type}
    for key in ("tile", "tiles", "gang_type", "skill_id", "params", "skill_ids", "confirm"):
        if key in payload:
            action[key] = payload[key]
    return action


def _room_summary(room: Room) -> dict[str, Any]:
    return {
        "room_id": room.room_id,
        "host_player_id": room.host_player_id,
        "status": room.status,
        "ready_player_ids": sorted(room.ready_player_ids),
        "players": [
            {
                "player_id": player_id,
                "name": name,
                "ready": player_id in room.ready_player_ids,
                "is_host": player_id == room.host_player_id,
                "connected": player_id in room.connected_player_ids,
            }
            for player_id, name in room.players.items()
        ],
    }


def _public_room_view(room: Room, viewer_id: str) -> dict[str, Any]:
    if room.game_state is None:
        return {
            **_room_summary(room),
            "phase": "waiting",
            "game": None,
        }

    state = room.game_state
    return {
        "room_id": room.room_id,
        "host_player_id": room.host_player_id,
        "status": room.status,
        "ready_player_ids": sorted(room.ready_player_ids),
        "connected_player_ids": sorted(room.connected_player_ids),
        "phase": state.phase,
        "current_player_id": state.current_player_id,
        "current_turn_has_drawn": state.current_turn_has_drawn,
        "pending_peng": _pending_peng_view(state, viewer_id),
        "last_discard": _last_discard_view(state),
        "dealer_id": state.dealer_id,
        "winner_id": state.winner_id,
        "loser_id": state.loser_id,
        "win_type": state.win_type,
        "winning_tile": tile_to_str(state.winning_tile) if state.winning_tile else None,
        "scores": dict(state.scores),
        "round_score_delta": dict(state.round_score_delta),
        "score_events": list(state.score_events),
        "settlement_summary": dict(state.settlement_summary) if state.settlement_summary else None,
        "fans": list(state.settlement_summary.get("fans", [])) if state.settlement_summary else [],
        "fan_labels": (
            list(state.settlement_summary.get("fan_labels", []))
            if state.settlement_summary
            else []
        ),
        "fan_multiplier": (
            state.settlement_summary.get("fan_multiplier", 1)
            if state.settlement_summary
            else 1
        ),
        "hu_notice": _hu_notice(state, viewer_id),
        "wall_count": len(state.wall),
        "can_hu": _can_viewer_hu(state, viewer_id),
        "sealed_peng": viewer_id in state.sealed_peng_player_ids,
        "players": [
            _public_player_view(
                state,
                player_id,
                viewer_id,
                room.host_player_id,
                room.ready_player_ids,
                room.connected_player_ids,
            )
            for player_id in state.player_order
        ],
        "private_data": dict(state.private_data.get(viewer_id, {})),
        "pending_discard_confirmation": _pending_discard_confirmation_view(state, viewer_id),
        "action_log": _public_action_log(state.action_log),
    }


def _public_player_view(
    state: GameState,
    player_id: str,
    viewer_id: str,
    host_player_id: str,
    ready_player_ids: set[str],
    connected_player_ids: set[str],
) -> dict[str, Any]:
    player = state.players[player_id]
    is_viewer = player_id == viewer_id
    view: dict[str, Any] = {
        "player_id": player.player_id,
        "name": player.name,
        "is_host": player_id == host_player_id,
        "ready": player_id in ready_player_ids,
        "connected": player_id in connected_player_ids,
        "is_dealer": player.is_dealer,
        "hand_count": len(player.hand),
        "discard_pile": [tile_to_str(tile) for tile in player.discard_pile],
        "melds": [_public_meld_view(meld, is_viewer) for meld in player.melds],
        "meld_count": len(player.melds),
        "skills": list(player.skills) if is_viewer or state.phase == "playing" else [],
        "skill_candidates": list(player.skill_candidates) if is_viewer else [],
        "skill_selected": len(player.skills) == 2,
        "private_skill_results": list(player.private_skill_results) if is_viewer else [],
        "auto_sort_hand": player.auto_sort_hand if is_viewer else None,
    }
    if is_viewer:
        view["hand"] = [tile_to_str(tile) for tile in player.hand]
    return view


def _pending_discard_confirmation_view(
    state: GameState,
    viewer_id: str,
) -> dict[str, Any] | None:
    if state.pending_action is None:
        return None
    if state.pending_action.get("type") != "confirm_dangerous_discard":
        return None
    if state.pending_action.get("player_id") != viewer_id:
        return None
    tile = state.pending_action.get("tile")
    return {
        "type": "confirm_dangerous_discard",
        "tile": tile_to_str(tile) if tile else None,
        "message": "这张牌可能点炮，是否仍然打出？",
    }


def _pending_peng_view(state: GameState, viewer_id: str) -> dict[str, Any] | None:
    if state.last_discard is None or not state.last_discard.available_for_claim:
        return None
    if viewer_id == state.last_discard.player_id:
        can_peng = False
    else:
        can_peng = (
            state.players[viewer_id].hand.count(state.last_discard.tile) >= 2
            and viewer_id not in state.sealed_peng_player_ids
        )
    return {
        "tile": tile_to_str(state.last_discard.tile),
        "discard_player_id": state.last_discard.player_id,
        "next_player_id": state.last_discard.next_player_id,
        "can_peng": can_peng,
        "sealed": viewer_id in state.sealed_peng_player_ids,
    }


def _last_discard_view(state: GameState) -> dict[str, Any] | None:
    if state.last_discard is None:
        return None
    return {
        "tile": tile_to_str(state.last_discard.tile),
        "player_id": state.last_discard.player_id,
        "next_player_id": state.last_discard.next_player_id,
        "available_for_claim": state.last_discard.available_for_claim,
    }


def _can_viewer_hu(state: GameState, viewer_id: str) -> bool:
    player = state.players[viewer_id]
    hand = list(player.hand)
    if (
        state.last_discard is not None
        and state.last_discard.available_for_claim
        and state.last_discard.player_id != viewer_id
    ):
        hand.append(state.last_discard.tile)
    return can_hu_with_melds(hand, player.melds)


def _public_meld_view(meld, is_viewer: bool) -> dict[str, Any]:
    hide_tiles = meld.concealed and not is_viewer
    tiles = ["?", "?", "?", "?"] if hide_tiles else [tile_to_str(tile) for tile in meld.tiles]
    return {
        "type": "hidden_gang" if hide_tiles else meld.type,
        "tiles": tiles,
        "from_player_id": meld.from_player_id,
        "claimed_tile": tile_to_str(meld.claimed_tile) if meld.claimed_tile else None,
        "concealed": meld.concealed,
    }


def _hu_notice(state: GameState, viewer_id: str) -> dict[str, Any] | None:
    if state.winner_id is None:
        return None
    return {
        "winner_id": state.winner_id,
        "message": f"玩家 {state.winner_id} 胡了",
        "self_message": "恭喜你，胡了！" if viewer_id == state.winner_id else None,
    }


def _public_action_log(action_log: list[dict]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in action.items() if key in PUBLIC_ACTION_LOG_KEYS}
        for action in action_log
    ]
