from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum

from core.mahjong.game_state import GameState, LastDiscard
from core.mahjong.hu_checker import can_hu, can_hu_with_melds
from core.mahjong.player import Meld, PlayerState
from core.mahjong.scoring import apply_delta, calculate_gang_delta
from core.mahjong.tile import Tile, sort_tiles, tile_to_str
from core.mahjong.wall import create_wall
from core.skills.base import SkillUseRecord
from core.skills.registry import SkillRegistry


class ActionType(StrEnum):
    START_GAME = "start_game"
    DRAW = "draw"
    DISCARD = "discard"
    CHI = "chi"
    PENG = "peng"
    PASS_PENG = "pass_peng"
    GANG = "gang"
    SUPPLEMENT_DRAW = "supplement_draw"
    DECLARE_HU = "declare_hu"
    USE_SKILL = "use_skill"
    SELECT_SKILLS = "select_skills"
    CONFIRM_DISCARD = "confirm_discard"


@dataclass(frozen=True, slots=True)
class GameAction:
    player_id: str
    action_type: ActionType


def start_game(
    room_id: str,
    player_ids: list[str],
    player_names: dict[str, str],
    seed: int | None = None,
) -> GameState:
    if not 2 <= len(player_ids) <= 4:
        raise ValueError("开始游戏需要 2 到 4 名玩家")
    if len(set(player_ids)) != len(player_ids):
        raise ValueError("玩家 ID 不能重复")

    missing_names = [player_id for player_id in player_ids if player_id not in player_names]
    if missing_names:
        raise ValueError(f"缺少玩家昵称：{missing_names}")

    dealer_id = player_ids[0]
    wall = create_wall(seed=seed)
    players = {
        player_id: PlayerState(
            player_id=player_id,
            name=player_names[player_id],
            is_dealer=player_id == dealer_id,
        )
        for player_id in player_ids
    }

    for player_id in player_ids:
        hand_size = 14 if player_id == dealer_id else 13
        players[player_id].hand = [wall.pop() for _ in range(hand_size)]
        _sort_hand_if_enabled(players[player_id])

    return GameState(
        room_id=room_id,
        players=players,
        player_order=list(player_ids),
        wall=wall,
        current_player_id=dealer_id,
        current_turn_has_drawn=True,
        dealer_id=dealer_id,
        phase="playing",
        action_log=[
            {
                "type": ActionType.START_GAME.value,
                "dealer_id": dealer_id,
                "player_ids": list(player_ids),
                "hand_counts": {
                    player_id: len(player.hand) for player_id, player in players.items()
                },
                "wall_count": len(wall),
            }
        ],
        scores={player_id: 0 for player_id in player_ids},
        round_score_delta={player_id: 0 for player_id in player_ids},
        turn_counts={player_id: 0 for player_id in player_ids},
        player_effects={player_id: [] for player_id in player_ids},
        river_recycle_usage={
            player_id: {"own": 0, "others": 0} for player_id in player_ids
        },
    )


def draw_tile(state: GameState, player_id: str) -> GameState:
    if state.phase != "playing":
        raise ValueError("游戏不在进行中")
    if _has_claimable_discard(state):
        raise ValueError("当前正在等待吃碰杠响应")
    if player_id != state.current_player_id:
        raise ValueError("只有当前玩家可以摸牌")
    if state.current_turn_has_drawn:
        raise ValueError("当前玩家已经摸牌，必须先出牌")

    next_state = deepcopy(state)
    return _draw_for_current_player(next_state, auto=False)


def discard_tile(state: GameState, player_id: str, tile: Tile) -> GameState:
    if state.phase != "playing":
        raise ValueError("游戏不在进行中")
    if _has_claimable_discard(state):
        raise ValueError("当前正在等待吃碰杠响应")
    if player_id != state.current_player_id:
        raise ValueError("只有当前玩家可以出牌")
    if not state.current_turn_has_drawn:
        raise ValueError("当前玩家需要先摸牌再出牌")
    if (
        state.pending_action is not None
        and state.pending_action.get("type") == "confirm_dangerous_discard"
    ):
        raise ValueError("请先确认或取消危险弃牌")
    if _should_warn_dangerous_discard(state, player_id, tile):
        next_state = deepcopy(state)
        next_state.pending_action = {
            "type": "confirm_dangerous_discard",
            "player_id": player_id,
            "tile": tile,
        }
        _add_private_skill_result(
            next_state,
            player_id,
            {
                "type": "killing_intent_sense",
                "message": "这张牌可能点炮，是否仍然打出？",
                "tile": tile_to_str(tile),
            },
        )
        _record_player_skill_use(next_state, player_id, "killing_intent_sense")
        next_state.action_log.append({"type": "passive_skill_triggered", "player_id": player_id})
        return next_state

    next_state = deepcopy(state)
    player = next_state.players[player_id]

    try:
        player.hand.remove(tile)
    except ValueError as exc:
        raise ValueError("玩家手里没有这张牌") from exc

    player.discard_pile.append(tile)
    next_player_id = _next_player_id(next_state, player_id)
    next_state.current_player_id = next_player_id
    next_state.current_turn_has_drawn = False
    next_state.last_discard = LastDiscard(
        tile=tile,
        player_id=player_id,
        next_player_id=next_player_id,
        available_for_claim=True,
    )
    next_state.action_log.append(
        {
            "type": ActionType.DISCARD.value,
            "player_id": player_id,
            "tile": tile_to_str(tile),
            "next_player_id": next_state.current_player_id,
            "hand_count": len(player.hand),
            "discard_count": len(player.discard_pile),
            "can_hu": can_hu(player.hand),
        }
    )
    next_state.turn_counts[player_id] = next_state.turn_counts.get(player_id, 0) + 1
    return next_state


def confirm_discard(state: GameState, player_id: str, confirm: bool) -> GameState:
    if state.pending_action is None:
        raise ValueError("当前没有需要确认的操作")
    if state.pending_action.get("type") != "confirm_dangerous_discard":
        raise ValueError("当前待确认操作不是危险弃牌")
    if state.pending_action.get("player_id") != player_id:
        raise ValueError("只能由触发玩家确认危险弃牌")

    tile = state.pending_action["tile"]
    next_state = deepcopy(state)
    next_state.pending_action = None
    next_state.action_log.append(
        {"type": ActionType.CONFIRM_DISCARD.value, "player_id": player_id, "confirm": confirm}
    )
    if not confirm:
        return next_state
    return discard_tile(next_state, player_id, tile)


def select_skills(
    state: GameState,
    player_id: str,
    selected_skill_ids: list[str],
) -> GameState:
    if state.phase != "skill_selection":
        raise ValueError("当前不在技能选择阶段")
    if player_id not in state.players:
        raise ValueError("玩家不存在")
    if len(selected_skill_ids) != 2:
        raise ValueError("必须选择 2 个技能")
    if len(set(selected_skill_ids)) != 2:
        raise ValueError("不能重复选择同一个技能")

    next_state = deepcopy(state)
    player = next_state.players[player_id]
    if any(skill_id not in player.skill_candidates for skill_id in selected_skill_ids):
        raise ValueError("只能从候选技能中选择")
    player.skills = list(selected_skill_ids)
    next_state.action_log.append(
        {
            "type": ActionType.SELECT_SKILLS.value,
            "player_id": player_id,
            "selected_count": len(selected_skill_ids),
        }
    )
    if all(len(next_state.players[pid].skills) == 2 for pid in next_state.player_order):
        next_state.phase = "playing"
        next_state.action_log.append({"type": "skill_selection_finished"})
    return next_state


def chi_tile(state: GameState, player_id: str, tiles: list[Tile]) -> GameState:
    last_discard = _require_claimable_discard(state)
    if player_id != last_discard.next_player_id:
        raise ValueError("只有出牌者的下家可以吃")
    if len(tiles) != 3:
        raise ValueError("吃牌必须提交三张牌")
    if last_discard.tile not in tiles:
        raise ValueError("吃牌组合必须包含刚打出的牌")
    if not _is_sequence(tiles):
        raise ValueError("吃牌必须是同花色连续三张")

    next_state = deepcopy(state)
    claimed_tile = next_state.last_discard.tile
    from_player_id = next_state.last_discard.player_id
    player = next_state.players[player_id]
    hand_tiles = list(tiles)
    hand_tiles.remove(claimed_tile)

    for tile in hand_tiles:
        try:
            player.hand.remove(tile)
        except ValueError as exc:
            raise ValueError("玩家手里缺少吃牌所需的牌") from exc

    _sort_hand_if_enabled(player)
    meld_tiles = sort_tiles(list(tiles))
    player.melds.append(
        Meld(
            type="chi",
            tiles=meld_tiles,
            from_player_id=from_player_id,
            claimed_tile=claimed_tile,
        )
    )
    _remove_last_discard_from_discards(next_state, from_player_id, claimed_tile)
    _clear_last_discard(next_state)
    next_state.current_player_id = player_id
    next_state.current_turn_has_drawn = True
    next_state.phase = "playing"
    next_state.action_log.append(
        {
            "type": ActionType.CHI.value,
            "player_id": player_id,
            "tiles": [tile_to_str(tile) for tile in meld_tiles],
            "from_player_id": from_player_id,
            "claimed_tile": tile_to_str(claimed_tile),
            "hand_count": len(player.hand),
            "meld_count": len(player.melds),
        }
    )
    return next_state


def peng_tile(state: GameState, player_id: str) -> GameState:
    last_discard = _require_claimable_discard(state)
    if player_id == last_discard.player_id:
        raise ValueError("不能碰自己打出的牌")
    if player_id not in state.players:
        raise ValueError("玩家不存在")
    if player_id in state.sealed_peng_player_ids:
        next_state = deepcopy(state)
        next_state.sealed_peng_player_ids.discard(player_id)
        next_state.action_log.append(
            {
                "type": ActionType.PASS_PENG.value,
                "player_id": player_id,
                "reason": "sealed_peng",
            }
        )
        return next_state

    next_state = deepcopy(state)
    tile = next_state.last_discard.tile
    from_player_id = next_state.last_discard.player_id
    player = next_state.players[player_id]
    if player.hand.count(tile) < 2:
        raise ValueError("手牌中没有两张相同的牌，不能碰")

    _remove_tiles_from_hand(player, tile, 2)
    _sort_hand_if_enabled(player)
    player.melds.append(
        Meld(
            type="peng",
            tiles=[tile, tile, tile],
            from_player_id=from_player_id,
            claimed_tile=tile,
        )
    )
    _remove_last_discard_from_discards(next_state, from_player_id, tile)
    _clear_last_discard(next_state)
    next_state.current_player_id = player_id
    next_state.current_turn_has_drawn = True
    next_state.sealed_peng_player_ids.discard(player_id)
    next_state.action_log.append(
        {
            "type": ActionType.PENG.value,
            "player_id": player_id,
            "tile": tile_to_str(tile),
            "hand_count": len(player.hand),
            "meld_count": len(player.melds),
        }
    )
    return next_state


def gang_tile(state: GameState, player_id: str, gang_type: str, tile: Tile) -> GameState:
    if gang_type == "concealed_gang":
        return _concealed_gang(state, player_id, tile)
    if gang_type == "exposed_gang":
        return _exposed_gang(state, player_id, tile)
    if gang_type == "added_gang":
        return _added_gang(state, player_id, tile)
    raise ValueError(f"不支持的杠类型：{gang_type}")


def pass_peng(state: GameState, player_id: str) -> GameState:
    if state.phase != "playing":
        raise ValueError("游戏不在进行中")
    if not _has_claimable_discard(state):
        raise ValueError("当前没有待处理的吃碰杠机会")

    next_state = deepcopy(state)
    next_state.sealed_peng_player_ids.clear()
    next_state.current_player_id = next_state.last_discard.next_player_id
    next_state.current_turn_has_drawn = False
    _clear_last_discard(next_state)
    next_state.action_log.append(
        {
            "type": ActionType.PASS_PENG.value,
            "player_id": player_id,
        }
    )
    return _draw_for_current_player(next_state, auto=True)


def use_skill(
    state: GameState,
    player_id: str,
    skill_id: str,
    params: dict[str, object],
    registry: SkillRegistry,
) -> GameState:
    if player_id not in state.players:
        raise ValueError("玩家不存在")
    if state.phase != "playing":
        raise ValueError("技能只能在正式开局后使用")

    player = state.players[player_id]
    if skill_id not in player.skills:
        raise ValueError("玩家没有这个技能")

    skill = registry.get(skill_id)
    if skill is None:
        raise ValueError("技能未注册")

    current_record = state.skill_usage.get(player_id, {}).get(
        skill_id,
        SkillUseRecord(player_id=player_id, skill_id=skill_id),
    )
    if current_record.used_count >= skill.max_uses_per_game:
        raise ValueError("技能使用次数已达上限")

    reflected_state = _try_reflect_target_skill(state, player_id, skill_id, params, skill)
    if reflected_state is not None:
        return reflected_state

    if not skill.can_use(state, player_id, params):
        raise ValueError(_skill_unavailable_message(state, player_id, skill_id))

    next_state = skill.apply(deepcopy(state), player_id, params)
    player_usage = next_state.skill_usage.setdefault(player_id, {})
    next_record = SkillUseRecord(
        player_id=player_id,
        skill_id=skill_id,
        used_count=current_record.used_count + 1,
    )
    player_usage[skill_id] = next_record
    next_state.players[player_id].skill_usage[skill_id] = next_record.used_count
    next_state.action_log.append(
        {
            "type": ActionType.USE_SKILL.value,
            "player_id": player_id,
            "skill_id": skill_id,
            "used_count": next_record.used_count,
        }
    )
    return next_state


def _concealed_gang(state: GameState, player_id: str, tile: Tile) -> GameState:
    _require_own_turn_for_gang(state, player_id)
    next_state = deepcopy(state)
    player = next_state.players[player_id]
    if player.hand.count(tile) < 4:
        raise ValueError("暗杠需要手中有四张相同的牌")

    _remove_tiles_from_hand(player, tile, 4)
    player.melds.append(Meld(type="concealed_gang", tiles=[tile] * 4, concealed=True))
    _sort_hand_if_enabled(player)
    next_state.action_log.append(
        {
            "type": ActionType.GANG.value,
            "player_id": player_id,
            "gang_type": "concealed_gang",
            "hand_count": len(player.hand),
            "meld_count": len(player.melds),
        }
    )
    next_state = _apply_gang_score(next_state, player_id, "concealed_gang")
    return _draw_supplement_tile(next_state, player_id)


def _exposed_gang(state: GameState, player_id: str, tile: Tile) -> GameState:
    last_discard = _require_claimable_discard(state)
    if player_id == last_discard.player_id:
        raise ValueError("不能杠自己打出的牌")
    if tile != last_discard.tile:
        raise ValueError("明杠必须杠刚打出的牌")

    next_state = deepcopy(state)
    claimed_tile = next_state.last_discard.tile
    from_player_id = next_state.last_discard.player_id
    player = next_state.players[player_id]
    if player.hand.count(claimed_tile) < 3:
        raise ValueError("明杠需要手中有三张相同的牌")

    _remove_tiles_from_hand(player, claimed_tile, 3)
    player.melds.append(
        Meld(
            type="exposed_gang",
            tiles=[claimed_tile] * 4,
            from_player_id=from_player_id,
            claimed_tile=claimed_tile,
        )
    )
    _sort_hand_if_enabled(player)
    _remove_last_discard_from_discards(next_state, from_player_id, claimed_tile)
    _clear_last_discard(next_state)
    next_state.current_player_id = player_id
    next_state.current_turn_has_drawn = True
    next_state.action_log.append(
        {
            "type": ActionType.GANG.value,
            "player_id": player_id,
            "gang_type": "exposed_gang",
            "tile": tile_to_str(claimed_tile),
            "from_player_id": from_player_id,
            "hand_count": len(player.hand),
            "meld_count": len(player.melds),
        }
    )
    next_state = _apply_gang_score(
        next_state,
        player_id,
        "exposed_gang",
        from_player_id=from_player_id,
    )
    return _draw_supplement_tile(next_state, player_id)


def _added_gang(state: GameState, player_id: str, tile: Tile) -> GameState:
    _require_own_turn_for_gang(state, player_id)
    next_state = deepcopy(state)
    player = next_state.players[player_id]
    peng_meld = next(
        (
            meld
            for meld in player.melds
            if (
                meld.type == "peng"
                and len(meld.tiles) == 3
                and all(meld_tile == tile for meld_tile in meld.tiles)
            )
        ),
        None,
    )
    if peng_meld is None:
        raise ValueError("没有对应的碰牌副露，不能补杠")
    if tile not in player.hand:
        raise ValueError("手牌中没有第 4 张牌，不能补杠")

    player.hand.remove(tile)
    peng_meld.type = "added_gang"
    peng_meld.tiles.append(tile)
    _sort_hand_if_enabled(player)
    next_state.action_log.append(
        {
            "type": ActionType.GANG.value,
            "player_id": player_id,
            "gang_type": "added_gang",
            "tile": tile_to_str(tile),
            "hand_count": len(player.hand),
            "meld_count": len(player.melds),
        }
    )
    next_state = _apply_gang_score(next_state, player_id, "added_gang")
    return _draw_supplement_tile(next_state, player_id)


def _apply_gang_score(
    state: GameState,
    player_id: str,
    gang_type: str,
    from_player_id: str | None = None,
) -> GameState:
    delta, event = calculate_gang_delta(
        state,
        gang_player_id=player_id,
        gang_type=gang_type,
        from_player_id=from_player_id,
    )
    return apply_delta(state, delta, event)


def _draw_supplement_tile(state: GameState, player_id: str) -> GameState:
    if not state.wall:
        state.phase = "draw_game"
        state.current_turn_has_drawn = False
        state.action_log.append(
            {
                "type": ActionType.SUPPLEMENT_DRAW.value,
                "player_id": player_id,
                "result": "wall_empty",
            }
        )
        return state

    player = state.players[player_id]
    player.hand.append(state.wall.pop())
    _sort_hand_if_enabled(player)
    state.current_player_id = player_id
    state.current_turn_has_drawn = True
    state.action_log.append(
        {
            "type": ActionType.SUPPLEMENT_DRAW.value,
            "player_id": player_id,
            "hand_count": len(player.hand),
            "wall_count": len(state.wall),
        }
    )
    return state


def _require_own_turn_for_gang(state: GameState, player_id: str) -> None:
    if state.phase != "playing":
        raise ValueError("游戏不在进行中")
    if _has_claimable_discard(state):
        raise ValueError("当前正在等待吃碰杠响应")
    if player_id != state.current_player_id:
        raise ValueError("只有当前玩家可以杠")
    if not state.current_turn_has_drawn:
        raise ValueError("当前玩家需要先摸牌再杠")


def _require_claimable_discard(state: GameState) -> LastDiscard:
    if state.phase != "playing":
        raise ValueError("游戏不在进行中")
    if not _has_claimable_discard(state):
        raise ValueError("当前没有可响应的弃牌")
    return state.last_discard


def _has_claimable_discard(state: GameState) -> bool:
    return state.last_discard is not None and state.last_discard.available_for_claim


def _is_sequence(tiles: list[Tile]) -> bool:
    sorted_tiles = sort_tiles(tiles)
    suit = sorted_tiles[0].suit
    ranks = [tile.rank for tile in sorted_tiles]
    return all(tile.suit == suit for tile in sorted_tiles) and ranks == list(
        range(ranks[0], ranks[0] + 3)
    )


def _remove_tiles_from_hand(player: PlayerState, tile: Tile, count: int) -> None:
    for _ in range(count):
        try:
            player.hand.remove(tile)
        except ValueError as exc:
            raise ValueError("玩家手牌数量不足") from exc


def _remove_last_discard_from_discards(state: GameState, player_id: str, tile: Tile) -> None:
    discarder = state.players[player_id]
    if discarder.discard_pile and discarder.discard_pile[-1] == tile:
        discarder.discard_pile.pop()


def _clear_last_discard(state: GameState) -> None:
    if state.last_discard is not None:
        state.last_discard.available_for_claim = False
    state.last_discard = None


def _next_player_id(state: GameState, player_id: str) -> str:
    current_index = state.player_order.index(player_id)
    return state.player_order[(current_index + 1) % len(state.player_order)]


def _draw_for_current_player(state: GameState, auto: bool) -> GameState:
    player_id = state.current_player_id
    if not state.wall:
        state.phase = "draw_game"
        state.action_log.append(
            {
                "type": ActionType.DRAW.value,
                "player_id": player_id,
                "result": "wall_empty",
                "auto": auto,
            }
        )
        return state

    player = state.players[player_id]
    player.hand.append(state.wall.pop())
    _sort_hand_if_enabled(player)
    state.current_turn_has_drawn = True
    state.action_log.append(
        {
            "type": ActionType.DRAW.value,
            "player_id": player_id,
            "hand_count": len(player.hand),
            "wall_count": len(state.wall),
            "auto": auto,
            "can_hu": can_hu(player.hand),
        }
    )
    return state


def _sort_hand_if_enabled(player: PlayerState) -> None:
    if player.auto_sort_hand:
        player.hand = sort_tiles(player.hand)


def _add_private_skill_result(state: GameState, player_id: str, result: dict) -> None:
    state.players[player_id].private_skill_results.append(result)
    private_results = state.private_data.setdefault(player_id, {}).setdefault(
        "private_skill_results",
        [],
    )
    private_results.append(result)


def _record_player_skill_use(state: GameState, player_id: str, skill_id: str) -> None:
    used_count = state.players[player_id].skill_usage.get(skill_id, 0) + 1
    state.players[player_id].skill_usage[skill_id] = used_count
    state.skill_usage.setdefault(player_id, {})[skill_id] = SkillUseRecord(
        player_id=player_id,
        skill_id=skill_id,
        used_count=used_count,
    )


def _should_warn_dangerous_discard(state: GameState, player_id: str, tile: Tile) -> bool:
    player = state.players[player_id]
    if "killing_intent_sense" not in player.skills:
        return False
    if player.skill_usage.get("killing_intent_sense", 0) >= 1:
        return False
    for other_player_id, other_player in state.players.items():
        if other_player_id == player_id:
            continue
        if can_hu_with_melds([*other_player.hand, tile], other_player.melds):
            return True
    return False


def _skill_unavailable_message(state: GameState, player_id: str, skill_id: str) -> str:
    if skill_id in {"astrology", "peek_neighbor", "change_suit"}:
        if state.phase != "playing":
            return "这个技能只能在正式对局中使用"
        if state.current_player_id != player_id:
            return f"这个技能只能在自己回合使用，当前轮到：{state.current_player_id}"
        last_used = state.players[player_id].skill_cooldowns.get(skill_id)
        if last_used is not None and state.turn_counts.get(player_id, 0) - last_used < 4:
            remaining = 4 - (state.turn_counts.get(player_id, 0) - last_used)
            return f"这个技能四巡一次，还需要再完成 {remaining} 次自己的回合"
    if skill_id == "wish_tile":
        if state.current_player_id != player_id:
            return f"自行印牌只能在自己摸牌前使用，当前轮到：{state.current_player_id}"
        if state.current_turn_has_drawn:
            return "自行印牌需要在摸牌前使用；当前已经摸过牌"
    if skill_id == "recycle_river":
        if state.current_player_id != player_id:
            return f"回收牌河只能在自己摸牌前使用，当前轮到：{state.current_player_id}"
        if state.current_turn_has_drawn:
            return "回收牌河需要在摸牌前使用；当前已经摸过牌"
    return "当前不能使用这个技能，请检查是否轮到你、是否在冷却中、参数是否正确"


def _try_reflect_target_skill(
    state: GameState,
    player_id: str,
    skill_id: str,
    params: dict[str, object],
    skill,
) -> GameState | None:
    if skill_id not in {"peek_neighbor", "swap_with_neighbor", "steal_concealed_gang"}:
        return None
    if getattr(skill, "reflected_apply", None) is None:
        return None
    target_player_id = _target_player_id_for_skill(state, player_id, skill_id, params)
    if target_player_id is None:
        return None
    target = state.players[target_player_id]
    if "mirror_reflection" not in target.skills:
        return None
    if target.skill_usage.get("mirror_reflection", 0) >= 1:
        return None

    next_state = deepcopy(state)
    _record_player_skill_use(next_state, target_player_id, "mirror_reflection")
    next_state.action_log.append(
        {
            "type": "mirror_reflection",
            "player_id": target_player_id,
            "reflected_player_id": player_id,
            "reflected_skill_id": skill_id,
        }
    )
    return skill.reflected_apply(
        next_state,
        original_player_id=player_id,
        target_player_id=target_player_id,
    )


def _target_player_id_for_skill(
    state: GameState,
    player_id: str,
    skill_id: str,
    params: dict[str, object],
) -> str | None:
    if skill_id == "steal_concealed_gang":
        target = params.get("target_player_id")
        return target if isinstance(target, str) else None
    direction = params.get("target_direction")
    if direction not in {"prev", "next"}:
        return None
    current_index = state.player_order.index(player_id)
    offset = -1 if direction == "prev" else 1
    return state.player_order[(current_index + offset) % len(state.player_order)]
