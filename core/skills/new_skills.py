from __future__ import annotations

import random
from dataclasses import dataclass

from core.mahjong.game_state import GameState
from core.mahjong.player import Meld, PlayerState
from core.mahjong.scoring import apply_delta, calculate_gang_delta
from core.mahjong.tile import Suit, Tile, parse_tile, sort_tiles, tile_to_str
from core.skills.base import Skill
from core.skills.registry import SkillRegistry

SKILL_IDS = [
    "mirror_reflection",
    "desperate_gamble",
    "close_enough",
    "astrology",
    "peek_neighbor",
    "swap_with_neighbor",
    "killing_intent_sense",
    "change_suit",
    "stealth_gang",
    "steal_concealed_gang",
    "recycle_river",
    "wish_tile",
]

FOUR_TURN_COOLDOWN_SKILLS = {"astrology", "peek_neighbor", "change_suit"}


@dataclass(frozen=True, slots=True)
class BasicSkill:
    id: str
    name: str
    description: str
    timing: str = "manual"
    max_uses_per_game: int = 1

    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return player_id in state.players

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        state.action_log.append({"type": f"{self.id}_noop", "player_id": player_id})
        return state


class PassiveSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return False


class DesperateGambleSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return _is_own_turn(state, player_id) and not _has_effect(state, player_id, self.id)

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        state.player_effects.setdefault(player_id, []).append(
            {"type": self.id, "active": True, "settled": False}
        )
        state.action_log.append(
            {"type": "skill_effect", "player_id": player_id, "skill_id": self.id}
        )
        return state


class AstrologySkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return _is_own_turn(state, player_id) and _cooldown_ready(state, player_id, self.id)

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        tiles = [tile_to_str(tile) for tile in state.wall[-4:]]
        _add_private_result(state, player_id, {"type": self.id, "tiles": tiles})
        _set_cooldown(state, player_id, self.id)
        state.action_log.append(
            {"type": "skill_effect", "player_id": player_id, "skill_id": self.id}
        )
        return state


class PeekNeighborSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return _is_own_turn(state, player_id) and _cooldown_ready(state, player_id, self.id)

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        target_player_id = _neighbor_id(state, player_id, params)
        _peek_target_hand(state, player_id, target_player_id, self.id)
        _set_cooldown(state, player_id, self.id)
        state.action_log.append(
            {
                "type": "skill_effect",
                "player_id": player_id,
                "skill_id": self.id,
                "target_player_id": target_player_id,
            }
        )
        return state

    def reflected_apply(
        self,
        state: GameState,
        original_player_id: str,
        target_player_id: str,
    ) -> GameState:
        _peek_target_hand(state, target_player_id, original_player_id, self.id)
        return state


class SwapWithNeighborSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        try:
            target_player_id = _neighbor_id(state, player_id, params)
            give_tile = parse_tile(str(params.get("give_tile")))
        except ValueError:
            return False
        return (
            _is_own_turn(state, player_id)
            and give_tile in state.players[player_id].hand
            and bool(state.players[target_player_id].hand)
        )

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        target_player_id = _neighbor_id(state, player_id, params)
        give_tile = parse_tile(str(params["give_tile"]))
        gained_tile = _swap_random_tile(state, player_id, target_player_id, give_tile)
        _add_private_result(
            state,
            player_id,
            {"type": self.id, "gained_tile": tile_to_str(gained_tile)},
        )
        state.action_log.append(
            {
                "type": "skill_effect",
                "player_id": player_id,
                "skill_id": self.id,
                "target_player_id": target_player_id,
            }
        )
        return state

    def reflected_apply(
        self,
        state: GameState,
        original_player_id: str,
        target_player_id: str,
    ) -> GameState:
        if not state.players[target_player_id].hand or not state.players[original_player_id].hand:
            return state
        give_tile = random.choice(state.players[target_player_id].hand)
        gained_tile = _swap_random_tile(state, target_player_id, original_player_id, give_tile)
        _add_private_result(
            state,
            target_player_id,
            {"type": self.id, "reflected": True, "gained_tile": tile_to_str(gained_tile)},
        )
        return state


class ChangeSuitSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        try:
            from_tile = parse_tile(str(params.get("from_tile")))
            to_suit = Suit(str(params.get("to_suit")))
        except ValueError:
            return False
        target_tile = Tile(to_suit, from_tile.rank)
        return (
            _is_own_turn(state, player_id)
            and _cooldown_ready(state, player_id, self.id)
            and from_tile.suit != to_suit
            and from_tile in state.players[player_id].hand
            and target_tile in state.wall
        )

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        from_tile = parse_tile(str(params["from_tile"]))
        to_suit = Suit(str(params["to_suit"]))
        target_tile = Tile(to_suit, from_tile.rank)
        player = state.players[player_id]
        player.hand.remove(from_tile)
        state.wall.remove(target_tile)
        player.hand.append(target_tile)
        state.wall.insert(0, from_tile)
        _sort_hand(player)
        _set_cooldown(state, player_id, self.id)
        _add_private_result(
            state,
            player_id,
            {
                "type": self.id,
                "from_tile": tile_to_str(from_tile),
                "to_tile": tile_to_str(target_tile),
            },
        )
        state.action_log.append(
            {"type": "skill_effect", "player_id": player_id, "skill_id": self.id}
        )
        return state


class StealthGangSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        try:
            tile = parse_tile(str(params.get("tile")))
        except ValueError:
            return False
        return (
            _is_own_turn(state, player_id)
            and state.players[player_id].hand.count(tile) >= 3
            and tile in state.wall
        )

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        tile = parse_tile(str(params["tile"]))
        player = state.players[player_id]
        for _ in range(3):
            player.hand.remove(tile)
        state.wall.remove(tile)
        player.melds.append(Meld(type="concealed_gang", tiles=[tile] * 4, concealed=True))
        _sort_hand(player)
        delta, event = calculate_gang_delta(state, player_id, "concealed_gang")
        state = apply_delta(state, delta, event)
        _supplement_draw(state, player_id)
        state.action_log.append(
            {"type": "skill_effect", "player_id": player_id, "skill_id": self.id}
        )
        return state


class StealConcealedGangSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        try:
            your_tile = parse_tile(str(params.get("your_tile")))
        except ValueError:
            return False
        target_player_id = params.get("target_player_id")
        if not isinstance(target_player_id, str) or target_player_id not in state.players:
            return False
        return your_tile in state.players[player_id].hand and _find_stealable_gang(
            state.players[target_player_id]
        ) is not None

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        target_player_id = str(params["target_player_id"])
        your_tile = parse_tile(str(params["your_tile"]))
        _steal_concealed_gang(state, player_id, target_player_id, your_tile, self.id)
        return state

    def reflected_apply(
        self,
        state: GameState,
        original_player_id: str,
        target_player_id: str,
    ) -> GameState:
        if not state.players[target_player_id].hand:
            return state
        your_tile = random.choice(state.players[target_player_id].hand)
        if _find_stealable_gang(state.players[original_player_id]) is None:
            return state
        _steal_concealed_gang(state, target_player_id, original_player_id, your_tile, self.id)
        return state


class RecycleRiverSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        try:
            tile = parse_tile(str(params.get("tile")))
        except ValueError:
            return False
        source = params.get("source")
        target_player_id = str(params.get("target_player_id") or player_id)
        usage = state.river_recycle_usage.setdefault(player_id, {"own": 0, "others": 0})
        if not _can_replace_draw(state, player_id) or source not in {"own", "others"}:
            return False
        if source == "own":
            return usage["own"] < 1 and tile in state.players[player_id].discard_pile
        return (
            usage["others"] < 1
            and target_player_id in state.players
            and target_player_id != player_id
            and tile in state.players[target_player_id].discard_pile
        )

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        tile = parse_tile(str(params["tile"]))
        source = str(params["source"])
        target_player_id = str(params.get("target_player_id") or player_id)
        pile = state.players[target_player_id].discard_pile
        pile.remove(tile)
        state.players[player_id].hand.append(tile)
        _sort_hand(state.players[player_id])
        state.current_turn_has_drawn = True
        state.river_recycle_usage[player_id][source] += 1
        state.action_log.append(
            {
                "type": "skill_effect",
                "player_id": player_id,
                "skill_id": self.id,
                "tile": tile_to_str(tile),
                "source": source,
            }
        )
        return state


class WishTileSkill(BasicSkill):
    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        try:
            parse_tile(str(params.get("tile")))
        except ValueError:
            return False
        return _can_replace_draw(state, player_id)

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        wished_tile = parse_tile(str(params["tile"]))
        success = wished_tile in state.wall
        drawn_tile = wished_tile
        if success:
            state.wall.remove(wished_tile)
        else:
            if not state.wall:
                state.phase = "draw_game"
                drawn_tile = None
            else:
                drawn_tile = state.wall.pop()
        if drawn_tile is not None:
            state.players[player_id].hand.append(drawn_tile)
            _sort_hand(state.players[player_id])
            state.current_turn_has_drawn = True
        _add_private_result(
            state,
            player_id,
            {
                "type": self.id,
                "success": success,
                "wished_tile": tile_to_str(wished_tile),
                "drawn_tile": tile_to_str(drawn_tile) if drawn_tile else None,
            },
        )
        state.action_log.append(
            {"type": "skill_effect", "player_id": player_id, "skill_id": self.id}
        )
        return state


def create_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    for skill in create_skills():
        registry.register(skill)
    return registry


def create_skills() -> list[Skill]:
    return [
        PassiveSkill("mirror_reflection", "镜像反射", "反射一次目标型主动技能", "passive", 1),
        DesperateGambleSkill("desperate_gamble", "破釜沉舟", "胡牌 x4，未胡额外扣分"),
        PassiveSkill("close_enough", "差不多就行", "差一点番型时胡牌 x2", "passive", 1),
        AstrologySkill("astrology", "观星", "查看牌墙顶 4 张", max_uses_per_game=99),
        PeekNeighborSkill(
            "peek_neighbor",
            "偷窥",
            "查看邻家随机两张手牌",
            max_uses_per_game=99,
        ),
        SwapWithNeighborSkill(
            "swap_with_neighbor",
            "偷天换日",
            "与邻家随机换一张牌",
            max_uses_per_game=2,
        ),
        PassiveSkill("killing_intent_sense", "杀意感知", "第一次点炮前提醒", "passive", 1),
        ChangeSuitSkill("change_suit", "换色", "换成同数字另一花色", max_uses_per_game=99),
        StealthGangSkill("stealth_gang", "偷摸开杠", "三张加牌墙一张形成暗杠"),
        StealConcealedGangSkill("steal_concealed_gang", "偷暗杠", "替换别人暗杠一张牌"),
        RecycleRiverSkill("recycle_river", "回收牌河", "从牌河回收一张牌", max_uses_per_game=2),
        WishTileSkill("wish_tile", "自行印牌", "摸牌时许愿一张牌"),
    ]


def _is_own_turn(state: GameState, player_id: str) -> bool:
    return state.phase == "playing" and state.current_player_id == player_id


def _can_replace_draw(state: GameState, player_id: str) -> bool:
    return _is_own_turn(state, player_id) and not state.current_turn_has_drawn


def _cooldown_ready(state: GameState, player_id: str, skill_id: str) -> bool:
    last_used = state.players[player_id].skill_cooldowns.get(skill_id)
    if last_used is None:
        return True
    return state.turn_counts.get(player_id, 0) - last_used >= 4


def _set_cooldown(state: GameState, player_id: str, skill_id: str) -> None:
    state.players[player_id].skill_cooldowns[skill_id] = state.turn_counts.get(player_id, 0)


def _neighbor_id(state: GameState, player_id: str, params: dict[str, object]) -> str:
    direction = params.get("target_direction")
    if direction not in {"prev", "next"}:
        raise ValueError("目标方向必须是 prev 或 next")
    index = state.player_order.index(player_id)
    offset = -1 if direction == "prev" else 1
    return state.player_order[(index + offset) % len(state.player_order)]


def _peek_target_hand(
    state: GameState,
    viewer_id: str,
    target_player_id: str,
    skill_id: str,
) -> None:
    target_hand = state.players[target_player_id].hand
    tiles = random.sample(target_hand, min(2, len(target_hand)))
    _add_private_result(
        state,
        viewer_id,
        {
            "type": skill_id,
            "target_player_id": target_player_id,
            "tiles": [tile_to_str(tile) for tile in tiles],
        },
    )


def _swap_random_tile(
    state: GameState,
    player_id: str,
    target_player_id: str,
    give_tile: Tile,
) -> Tile:
    player = state.players[player_id]
    target = state.players[target_player_id]
    player.hand.remove(give_tile)
    gained_tile = random.choice(target.hand)
    target.hand.remove(gained_tile)
    target.hand.append(give_tile)
    player.hand.append(gained_tile)
    _sort_hand(player)
    _sort_hand(target)
    return gained_tile


def _find_stealable_gang(player: PlayerState) -> Meld | None:
    return next(
        (
            meld
            for meld in player.melds
            if meld.type == "concealed_gang" and meld.concealed and not meld.stolen
        ),
        None,
    )


def _steal_concealed_gang(
    state: GameState,
    player_id: str,
    target_player_id: str,
    your_tile: Tile,
    skill_id: str,
) -> None:
    player = state.players[player_id]
    target = state.players[target_player_id]
    meld = _find_stealable_gang(target)
    if meld is None:
        raise ValueError("目标没有可偷的暗杠")
    player.hand.remove(your_tile)
    stolen_tile = random.choice(meld.tiles)
    meld.tiles.remove(stolen_tile)
    meld.tiles.append(your_tile)
    meld.stolen = True
    player.hand.append(stolen_tile)
    _sort_hand(player)
    _add_private_result(
        state,
        player_id,
        {
            "type": skill_id,
            "target_player_id": target_player_id,
            "stolen_tile": tile_to_str(stolen_tile),
        },
    )
    _add_private_result(
        state,
        target_player_id,
        {"type": "concealed_gang_touched", "message": "你的暗杠被动过"},
    )
    state.action_log.append(
        {
            "type": "skill_effect",
            "player_id": player_id,
            "skill_id": skill_id,
            "target_player_id": target_player_id,
        }
    )


def _has_effect(state: GameState, player_id: str, effect_type: str) -> bool:
    return any(
        effect.get("type") == effect_type
        for effect in state.player_effects.get(player_id, [])
    )


def _add_private_result(state: GameState, player_id: str, result: dict) -> None:
    state.players[player_id].private_skill_results.append(result)
    private_results = state.private_data.setdefault(player_id, {}).setdefault(
        "private_skill_results",
        [],
    )
    private_results.append(result)


def _sort_hand(player: PlayerState) -> None:
    if player.auto_sort_hand:
        player.hand = sort_tiles(player.hand)


def _supplement_draw(state: GameState, player_id: str) -> None:
    if not state.wall:
        state.phase = "draw_game"
        return
    state.players[player_id].hand.append(state.wall.pop())
    _sort_hand(state.players[player_id])
    state.current_player_id = player_id
    state.current_turn_has_drawn = True
