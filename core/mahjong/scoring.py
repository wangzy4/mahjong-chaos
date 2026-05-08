from __future__ import annotations

from typing import TYPE_CHECKING

from core.mahjong.fan import detect_fans, fan_labels
from core.mahjong.tile import Tile, tile_to_str

if TYPE_CHECKING:
    from core.mahjong.game_state import GameState


class InvalidScoreError(ValueError):
    pass


class InvalidSettlementError(ValueError):
    pass


def zero_delta(player_ids: list[str]) -> dict[str, int]:
    return {player_id: 0 for player_id in player_ids}


def apply_delta(state: GameState, delta: dict[str, int], event: dict) -> GameState:
    _validate_delta(state.player_order, delta)
    _ensure_score_fields(state)

    for player_id, value in delta.items():
        state.scores[player_id] += value
        state.round_score_delta[player_id] += value

    score_event = {**event, "delta": dict(delta)}
    state.score_events.append(score_event)
    state.action_log.append(
        {
            "type": "score",
            "score_type": score_event.get("type"),
            "label": score_event.get("label"),
            "message": score_event.get("message"),
            "player_id": score_event.get("winner_id") or score_event.get("gang_player_id"),
            "winner_id": score_event.get("winner_id"),
            "loser_id": score_event.get("loser_id"),
            "gang_player_id": score_event.get("gang_player_id"),
            "from_player_id": score_event.get("from_player_id"),
            "base": score_event.get("base"),
            "fan_multiplier": score_event.get("fan_multiplier"),
            "dealer_multiplier": score_event.get("dealer_multiplier"),
            "double_score_multiplier": score_event.get("double_score_multiplier"),
            "multiplier": score_event.get("multiplier"),
            "fans": score_event.get("fans"),
            "fan_labels": score_event.get("fan_labels"),
            "payments": score_event.get("payments"),
            "delta": dict(delta),
        }
    )
    return state


def calculate_win_delta(
    state: GameState,
    winner_id: str,
    win_type: str,
    loser_id: str | None,
    winning_tile: Tile | None,
) -> tuple[dict[str, int], dict]:
    _validate_win_context(state, winner_id, win_type, loser_id)

    fan_result = detect_fans(state, winner_id, win_type, winning_tile)
    double_score_multiplier = _double_score_multiplier(state, winner_id, loser_id, win_type)
    delta = zero_delta(state.player_order)
    payments: list[dict] = []

    if win_type == "discard":
        assert loser_id is not None
        dealer_multiplier = _dealer_payment_multiplier(state, winner_id, loser_id)
        amount = 3 * fan_result.multiplier * dealer_multiplier * double_score_multiplier
        _apply_payment(delta, loser_id, winner_id, amount)
        payments.append(
            _payment(
                loser_id,
                winner_id,
                base=3,
                fan_multiplier=fan_result.multiplier,
                dealer_multiplier=dealer_multiplier,
                double_score_multiplier=double_score_multiplier,
                amount=amount,
            )
        )
    elif win_type == "self_draw":
        for payer_id in state.player_order:
            if payer_id == winner_id:
                continue
            dealer_multiplier = _dealer_payment_multiplier(state, winner_id, payer_id)
            amount = 2 * fan_result.multiplier * dealer_multiplier * double_score_multiplier
            _apply_payment(delta, payer_id, winner_id, amount)
            payments.append(
                _payment(
                    payer_id,
                    winner_id,
                    base=2,
                    fan_multiplier=fan_result.multiplier,
                    dealer_multiplier=dealer_multiplier,
                    double_score_multiplier=double_score_multiplier,
                    amount=amount,
                )
            )
    else:
        raise InvalidSettlementError(f"不支持的胡牌类型：{win_type}")

    _validate_delta(state.player_order, delta)
    event = {
        "type": "win",
        "win_type": win_type,
        "label": _win_type_label(win_type),
        "winner_id": winner_id,
        "loser_id": loser_id,
        "winning_tile": tile_to_str(winning_tile) if winning_tile else None,
        "fans": list(fan_result.fans),
        "fan_labels": fan_labels(fan_result.fans),
        "fan_multiplier": fan_result.multiplier,
        "dealer_id": state.dealer_id,
        "dealer_multiplier": max(payment["dealer_multiplier"] for payment in payments),
        "double_score_multiplier": double_score_multiplier,
        "multiplier": fan_result.multiplier * double_score_multiplier,
        "payments": payments,
        "delta": delta,
    }
    event["message"] = _win_message(event, delta)
    return delta, event


def calculate_legacy_win_delta(
    player_ids: list[str],
    winner_id: str,
    win_type: str,
    loser_id: str | None,
    multiplier: int = 1,
) -> dict[str, int]:
    if winner_id not in player_ids:
        raise InvalidSettlementError("胡牌玩家不在玩家列表中")
    if multiplier < 1:
        raise InvalidSettlementError("计分倍率必须大于等于 1")

    delta = zero_delta(player_ids)
    if win_type == "self_draw":
        if loser_id is not None:
            raise InvalidSettlementError("自摸胡不能有点炮玩家")
        for player_id in player_ids:
            delta[player_id] = (
                2 * (len(player_ids) - 1) * multiplier
                if player_id == winner_id
                else -2 * multiplier
            )
    elif win_type == "discard":
        if loser_id is None:
            raise InvalidSettlementError("点炮胡必须提供点炮玩家")
        delta[winner_id] = 3 * multiplier
        delta[loser_id] = -3 * multiplier
    elif win_type == "draw_game":
        if loser_id is not None:
            raise InvalidSettlementError("流局不能有点炮玩家")
    else:
        raise InvalidSettlementError(f"不支持的胡牌类型：{win_type}")

    _validate_delta(player_ids, delta)
    return delta


def calculate_gang_delta(
    state: GameState,
    gang_player_id: str,
    gang_type: str,
    from_player_id: str | None = None,
) -> tuple[dict[str, int], dict]:
    _validate_gang_context(state, gang_player_id, gang_type, from_player_id)

    delta = zero_delta(state.player_order)
    payments: list[dict] = []
    if gang_type == "concealed_gang":
        for payer_id in state.player_order:
            if payer_id == gang_player_id:
                continue
            dealer_multiplier = _dealer_payment_multiplier(state, gang_player_id, payer_id)
            amount = 2 * dealer_multiplier
            _apply_payment(delta, payer_id, gang_player_id, amount)
            payments.append(
                _payment(
                    payer_id,
                    gang_player_id,
                    base=2,
                    fan_multiplier=1,
                    dealer_multiplier=dealer_multiplier,
                    double_score_multiplier=1,
                    amount=amount,
                )
            )
    elif gang_type == "exposed_gang":
        assert from_player_id is not None
        dealer_multiplier = _dealer_payment_multiplier(state, gang_player_id, from_player_id)
        amount = 3 * dealer_multiplier
        _apply_payment(delta, from_player_id, gang_player_id, amount)
        payments.append(
            _payment(
                from_player_id,
                gang_player_id,
                base=3,
                fan_multiplier=1,
                dealer_multiplier=dealer_multiplier,
                double_score_multiplier=1,
                amount=amount,
            )
        )
    elif gang_type == "added_gang":
        for payer_id in state.player_order:
            if payer_id == gang_player_id:
                continue
            dealer_multiplier = _dealer_payment_multiplier(state, gang_player_id, payer_id)
            amount = dealer_multiplier
            _apply_payment(delta, payer_id, gang_player_id, amount)
            payments.append(
                _payment(
                    payer_id,
                    gang_player_id,
                    base=1,
                    fan_multiplier=1,
                    dealer_multiplier=dealer_multiplier,
                    double_score_multiplier=1,
                    amount=amount,
                )
            )
    else:
        raise InvalidSettlementError(f"不支持的杠类型：{gang_type}")

    _validate_delta(state.player_order, delta)
    event = {
        "type": "gang",
        "gang_type": gang_type,
        "label": _gang_type_label(gang_type),
        "gang_player_id": gang_player_id,
        "from_player_id": from_player_id,
        "dealer_id": state.dealer_id,
        "dealer_multiplier": max(payment["dealer_multiplier"] for payment in payments),
        "fan_multiplier": 1,
        "double_score_multiplier": 1,
        "multiplier": 1,
        "payments": payments,
        "delta": delta,
    }
    event["message"] = _gang_score_message(event, delta)
    return delta, event


def calculate_draw_delta(player_ids: list[str]) -> dict[str, int]:
    return zero_delta(player_ids)


def get_win_multiplier(
    state: GameState,
    winner_id: str,
    loser_id: str | None,
    win_type: str,
) -> int:
    fan_result = detect_fans(state, winner_id, win_type, None)
    return fan_result.multiplier * _double_score_multiplier(state, winner_id, loser_id, win_type)


def settle_win(
    state: GameState,
    winner_id: str,
    win_type: str,
    loser_id: str | None,
    winning_tile: Tile | None = None,
) -> GameState:
    delta, event = calculate_win_delta(
        state,
        winner_id=winner_id,
        win_type=win_type,
        loser_id=loser_id,
        winning_tile=winning_tile,
    )
    state.settlement_summary = {
        "type": win_type,
        "label": event["label"],
        "message": event["message"],
        "winner_id": winner_id,
        "loser_id": loser_id,
        "winning_tile": event["winning_tile"],
        "fans": list(event["fans"]),
        "fan_labels": list(event["fan_labels"]),
        "fan_multiplier": event["fan_multiplier"],
        "dealer_id": event["dealer_id"],
        "dealer_multiplier": event["dealer_multiplier"],
        "double_score_multiplier": event["double_score_multiplier"],
        "payments": list(event["payments"]),
        "delta": dict(delta),
    }
    return apply_delta(state, delta, event)


def _validate_win_context(
    state: GameState,
    winner_id: str,
    win_type: str,
    loser_id: str | None,
) -> None:
    if winner_id not in state.players:
        raise InvalidSettlementError("胡牌玩家不在玩家列表中")
    if win_type == "self_draw":
        if loser_id is not None:
            raise InvalidSettlementError("自摸胡不能有点炮玩家")
    elif win_type == "discard":
        if loser_id is None:
            raise InvalidSettlementError("点炮胡必须提供点炮玩家")
        if loser_id not in state.players:
            raise InvalidSettlementError("点炮玩家不在玩家列表中")
        if loser_id == winner_id:
            raise InvalidSettlementError("胡牌玩家不能同时是点炮玩家")
    else:
        raise InvalidSettlementError(f"不支持的胡牌类型：{win_type}")


def _validate_gang_context(
    state: GameState,
    gang_player_id: str,
    gang_type: str,
    from_player_id: str | None,
) -> None:
    if gang_player_id not in state.players:
        raise InvalidSettlementError("杠牌玩家不在玩家列表中")
    if gang_type == "concealed_gang":
        if from_player_id is not None:
            raise InvalidSettlementError("暗杠不能有点杠玩家")
    elif gang_type == "exposed_gang":
        if from_player_id is None:
            raise InvalidSettlementError("明杠必须提供点杠玩家")
        if from_player_id not in state.players:
            raise InvalidSettlementError("点杠玩家不在玩家列表中")
        if from_player_id == gang_player_id:
            raise InvalidSettlementError("杠牌玩家不能杠自己打出的牌")
    elif gang_type == "added_gang":
        if from_player_id is not None:
            raise InvalidSettlementError("补杠不需要点杠玩家")
    else:
        raise InvalidSettlementError(f"不支持的杠类型：{gang_type}")


def _dealer_payment_multiplier(state: GameState, receiver_id: str, payer_id: str) -> int:
    return 2 if receiver_id == state.dealer_id or payer_id == state.dealer_id else 1


def _double_score_multiplier(
    state: GameState,
    winner_id: str,
    loser_id: str | None,
    win_type: str,
) -> int:
    if win_type == "self_draw":
        return 2 if _has_double_score(state, winner_id) else 1
    if win_type == "discard":
        if loser_id is None:
            raise InvalidSettlementError("点炮胡必须提供点炮玩家")
        return 2 if _has_double_score(state, winner_id) or _has_double_score(state, loser_id) else 1
    raise InvalidSettlementError(f"不支持的胡牌类型：{win_type}")


def _has_double_score(state: GameState, player_id: str) -> bool:
    player = state.players[player_id]
    if "double_score" in player.skills:
        return True
    return bool(state.private_data.get(player_id, {}).get("double_score"))


def _apply_payment(
    delta: dict[str, int],
    from_player_id: str,
    to_player_id: str,
    amount: int,
) -> None:
    delta[from_player_id] -= amount
    delta[to_player_id] += amount


def _payment(
    from_player_id: str,
    to_player_id: str,
    base: int,
    fan_multiplier: int,
    dealer_multiplier: int,
    double_score_multiplier: int,
    amount: int,
) -> dict:
    return {
        "from": from_player_id,
        "to": to_player_id,
        "base": base,
        "fan_multiplier": fan_multiplier,
        "dealer_multiplier": dealer_multiplier,
        "double_score_multiplier": double_score_multiplier,
        "amount": amount,
    }


def _win_type_label(win_type: str) -> str:
    labels = {
        "self_draw": "自摸胡",
        "discard": "点炮胡",
        "draw_game": "流局",
    }
    return labels.get(win_type, win_type)


def _gang_type_label(gang_type: str) -> str:
    labels = {
        "concealed_gang": "暗杠",
        "exposed_gang": "明杠",
        "added_gang": "补杠",
    }
    return labels.get(gang_type, gang_type)


def _win_message(event: dict, delta: dict[str, int]) -> str:
    fan_text = "、".join(event["fan_labels"]) if event["fan_labels"] else "无番型"
    score_text = _delta_text(delta)
    if event["win_type"] == "self_draw":
        return (
            f"玩家 {event['winner_id']} 自摸胡，番型：{fan_text}，"
            f"番型倍率 x{event['fan_multiplier']}，结算：{score_text}"
        )
    tile_text = f"，胡牌牌为 {event['winning_tile']}" if event.get("winning_tile") else ""
    return (
        f"玩家 {event['winner_id']} 点炮胡，点炮玩家 {event['loser_id']}{tile_text}，"
        f"番型：{fan_text}，番型倍率 x{event['fan_multiplier']}，结算：{score_text}"
    )


def _gang_score_message(event: dict, delta: dict[str, int]) -> str:
    score_text = _delta_text(delta)
    if event.get("from_player_id"):
        return (
            f"玩家 {event['gang_player_id']} {event['label']}，"
            f"点杠玩家 {event['from_player_id']}，结算：{score_text}"
        )
    return f"玩家 {event['gang_player_id']} {event['label']}，结算：{score_text}"


def _delta_text(delta: dict[str, int]) -> str:
    return "，".join(f"{player_id} {value:+d}" for player_id, value in delta.items())


def _ensure_score_fields(state: GameState) -> None:
    if not state.scores:
        state.scores = zero_delta(state.player_order)
    if not state.round_score_delta:
        state.round_score_delta = zero_delta(state.player_order)


def _validate_delta(player_ids: list[str], delta: dict[str, int]) -> None:
    expected_player_ids = set(player_ids)
    actual_player_ids = set(delta)
    if actual_player_ids != expected_player_ids:
        raise InvalidScoreError("计分 delta 必须包含所有玩家且不能包含其他玩家")
    if any(not isinstance(value, int) for value in delta.values()):
        raise InvalidScoreError("计分 delta 只能包含整数")
    if sum(delta.values()) != 0:
        raise InvalidScoreError("计分 delta 总和必须为 0")
