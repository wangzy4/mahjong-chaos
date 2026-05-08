from collections.abc import Callable
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, player_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(room_id, {})[player_id] = websocket

    def disconnect(self, room_id: str, player_id: str) -> None:
        room_connections = self.connections.get(room_id)
        if room_connections is None:
            return
        room_connections.pop(player_id, None)
        if not room_connections:
            self.connections.pop(room_id, None)

    async def send_to_player(self, room_id: str, player_id: str, message: dict[str, Any]) -> None:
        websocket = self.connections.get(room_id, {}).get(player_id)
        if websocket is None:
            return
        await websocket.send_json(message)

    async def broadcast_room(
        self,
        room_id: str,
        build_message_for_player: Callable[[str], dict[str, Any] | None],
    ) -> None:
        for player_id, websocket in list(self.connections.get(room_id, {}).items()):
            try:
                message = build_message_for_player(player_id)
                if message is None:
                    continue
                await websocket.send_json(message)
            except RuntimeError:
                self.disconnect(room_id, player_id)

    async def broadcast_public_views(self, room_id: str, room_manager) -> None:
        await self.broadcast_room(
            room_id,
            lambda player_id: {
                "type": "state",
                "data": room_manager.get_public_view(room_id, player_id),
            },
        )
