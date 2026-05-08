from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from core.mahjong.game_state import GameState


@dataclass(frozen=True, slots=True)
class SkillUseRecord:
    player_id: str
    skill_id: str
    used_count: int = 0


class Skill(Protocol):
    id: str
    name: str
    description: str
    timing: str
    max_uses_per_game: int

    def can_use(self, state: GameState, player_id: str, params: dict[str, object]) -> bool:
        ...

    def apply(self, state: GameState, player_id: str, params: dict[str, object]) -> GameState:
        ...
