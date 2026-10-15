
from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WebSocketConnectionManager:
    """Manage active WebSocket connections by room and player."""

    def __init__(self) -> None:
        self._connections: dict[
            str, dict[int, set[WebSocket]]
        ] = defaultdict(lambda: defaultdict(set))
        self._lock = asyncio.Lock()

    async def connect(
        self,
        room_code: str,
        player_id: int,
        websocket: WebSocket,
    ) -> bool:
        """Register a socket. Return True for the player's first socket."""
        room_code = room_code.upper()

        async with self._lock:
            player_connections = self._connections[room_code][player_id]
            was_disconnected = len(player_connections) == 0
            player_connections.add(websocket)
            return was_disconnected

    async def disconnect(
        self,
        room_code: str,
        player_id: int,
        websocket: WebSocket,
    ) -> bool:
        """Remove a socket. Return True when the player's last socket closes."""
        room_code = room_code.upper()

        async with self._lock:
            room_connections = self._connections.get(room_code)
            if room_connections is None:
                return False

            player_connections = room_connections.get(player_id)
            if player_connections is None:
                return False

            player_connections.discard(websocket)

            if player_connections:
                return False

            room_connections.pop(player_id, None)

            if not room_connections:
                self._connections.pop(room_code, None)

            return True

    async def is_player_connected(
        self,
        room_code: str,
        player_id: int,
    ) -> bool:
        room_code = room_code.upper()

        async with self._lock:
            return bool(
                self._connections.get(room_code, {}).get(player_id)
            )

    async def get_connected_player_ids(
        self,
        room_code: str,
    ) -> set[int]:
        room_code = room_code.upper()

        async with self._lock:
            return {
                player_id
                for player_id, sockets
                in self._connections.get(room_code, {}).items()
                if sockets
            }

    async def send_to_player(
        self,
        room_code: str,
        player_id: int,
        message: dict,
    ) -> int:
        """Send a JSON message to every active socket for one player."""
        room_code = room_code.upper()

        async with self._lock:
            sockets = list(
                self._connections.get(room_code, {}).get(player_id, set())
            )

        sent = 0
        for websocket in sockets:
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception:
                # The socket's endpoint will clean up its registration.
                continue

        return sent

    async def broadcast_to_room(
        self,
        room_code: str,
        message: dict,
        exclude_player_id: int | None = None,
    ) -> int:
        """Broadcast JSON to sockets in one room only."""
        room_code = room_code.upper()

        async with self._lock:
            recipients = [
                (player_id, websocket)
                for player_id, sockets
                in self._connections.get(room_code, {}).items()
                if player_id != exclude_player_id
                for websocket in list(sockets)
            ]

        sent = 0
        for _, websocket in recipients:
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception:
                # Do not let one failed socket interrupt other recipients.
                continue

        return sent


websocket_manager = WebSocketConnectionManager()
