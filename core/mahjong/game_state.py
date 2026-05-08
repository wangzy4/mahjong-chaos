from dataclasses import dataclass, field

from core.mahjong.player import PlayerState
from core.mahjong.tile import Tile
from core.skills.base import SkillUseRecord


@dataclass(slots=True)
class LastDiscard:
    tile: Tile
    player_id: str
    next_player_id: str
    available_for_claim: bool = True


@dataclass(slots=True)
class GameState:
    room_id: str
    players: dict[str, PlayerState]
    player_order: list[str]
    wall: list[Tile] = field(default_factory=list)
    current_player_id: str = ""
    current_turn_has_drawn: bool = False
    last_discard: LastDiscard | None = None
    sealed_peng_player_ids: set[str] = field(default_factory=set)
    dealer_id: str = ""
    phase: str = "waiting"
    action_log: list[dict] = field(default_factory=list)
    skill_usage: dict[str, dict[str, SkillUseRecord]] = field(default_factory=dict)
    private_data: dict[str, dict[str, object]] = field(default_factory=dict)
    turn_counts: dict[str, int] = field(default_factory=dict)
    player_effects: dict[str, list[dict]] = field(default_factory=dict)
    concealed_gang_locks: dict[str, bool] = field(default_factory=dict)
    river_recycle_usage: dict[str, dict[str, int]] = field(default_factory=dict)
    pending_action: dict | None = None
    scores: dict[str, int] = field(default_factory=dict)
    round_score_delta: dict[str, int] = field(default_factory=dict)
    score_events: list[dict] = field(default_factory=list)
    settlement_summary: dict | None = None
    winner_id: str | None = None
    loser_id: str | None = None
    win_type: str | None = None
    winning_tile: Tile | None = None

    @property
    def pending_discard_player_id(self) -> str | None:
        return self.last_discard.player_id if self.last_discard else None

    @pending_discard_player_id.setter
    def pending_discard_player_id(self, value: str | None) -> None:
        if self.last_discard is None or value is None:
            self.last_discard = None
        else:
            self.last_discard.player_id = value

    @property
    def pending_discard_tile(self) -> Tile | None:
        return self.last_discard.tile if self.last_discard else None

    @pending_discard_tile.setter
    def pending_discard_tile(self, value: Tile | None) -> None:
        if self.last_discard is None or value is None:
            self.last_discard = None
        else:
            self.last_discard.tile = value

    @property
    def pending_next_player_id(self) -> str | None:
        return self.last_discard.next_player_id if self.last_discard else None

    @pending_next_player_id.setter
    def pending_next_player_id(self, value: str | None) -> None:
        if self.last_discard is None or value is None:
            self.last_discard = None
        else:
            self.last_discard.next_player_id = value
