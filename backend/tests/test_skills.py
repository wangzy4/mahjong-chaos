from dataclasses import dataclass

import pytest

from core.mahjong.actions import start_game, use_skill
from core.mahjong.game_state import GameState
from core.skills.registry import SkillRegistry

PLAYER_IDS = ["p1", "p2", "p3", "p4"]
PLAYER_NAMES = {
    "p1": "东风",
    "p2": "南风",
    "p3": "西风",
    "p4": "北风",
}


@dataclass(frozen=True, slots=True)
class DummySkill:
    id: str = "dummy"
    name: str = "测试技能"
    description: str = "只用于测试技能系统流程"
    timing: str = "manual"
    max_uses_per_game: int = 1
    allowed: bool = True

    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        return self.allowed

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        state.players[player_id].skills.append("applied-marker")
        return state


def make_state_with_skill(skill_id: str = "dummy") -> GameState:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)
    state.players["p1"].skills.append(skill_id)
    return state


def make_registry(skill: DummySkill | None = None) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(skill or DummySkill())
    return registry


def test_player_cannot_use_skill_they_do_not_have() -> None:
    state = start_game("room-1", PLAYER_IDS, PLAYER_NAMES, seed=1)

    with pytest.raises(ValueError, match="没有这个技能"):
        use_skill(state, "p1", "dummy", {}, make_registry())


def test_player_cannot_use_skill_more_than_max_uses() -> None:
    state = make_state_with_skill()
    registry = make_registry()

    next_state = use_skill(state, "p1", "dummy", {}, registry)

    with pytest.raises(ValueError, match="使用次数已达上限"):
        use_skill(next_state, "p1", "dummy", {}, registry)


def test_player_cannot_use_skill_when_can_use_returns_false() -> None:
    state = make_state_with_skill()
    registry = make_registry(DummySkill(allowed=False))

    with pytest.raises(ValueError, match="当前不能使用"):
        use_skill(state, "p1", "dummy", {}, registry)


def test_successful_skill_use_increments_skill_usage() -> None:
    state = make_state_with_skill()

    next_state = use_skill(state, "p1", "dummy", {}, make_registry())

    assert next_state.skill_usage["p1"]["dummy"].used_count == 1
    assert "applied-marker" in next_state.players["p1"].skills
    assert "applied-marker" not in state.players["p1"].skills


def test_successful_skill_use_records_action_log() -> None:
    state = make_state_with_skill()

    next_state = use_skill(state, "p1", "dummy", {"target": "p2"}, make_registry())

    assert next_state.action_log[-1] == {
        "type": "use_skill",
        "player_id": "p1",
        "skill_id": "dummy",
        "used_count": 1,
    }


def test_registry_can_get_and_list_skills() -> None:
    skill = DummySkill()
    registry = make_registry(skill)

    assert registry.get("dummy") is skill
    assert registry.list_skills() == [skill]
