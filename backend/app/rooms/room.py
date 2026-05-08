from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.mahjong.game_state import GameState


@dataclass(slots=True)
class PlayerSession:
    player_id: str
    name: str
    connected: bool = False


@dataclass(slots=True)
class Room:
    room_id: str
    host_player_id: str
    players: dict[str, str]
    game_state: GameState | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "waiting"
    ready_player_ids: set[str] = field(default_factory=set)
    connected_player_ids: set[str] = field(default_factory=set)

    @property
    def player_sessions(self) -> dict[str, PlayerSession]:
        return {
            player_id: PlayerSession(
                player_id=player_id,
                name=name,
                connected=player_id in self.connected_player_ids,
            )
            for player_id, name in self.players.items()
        }
