from __future__ import annotations

import asyncio
from collections import deque
from typing import Any


class DrawingStateStore:
    """Bounded, process-local drawing state for reconnect/canvas synchronization.

    For multi-worker or multi-container deployments, replace this store with a
    shared Redis-backed implementation so every worker sees the same canvas.
    """

    def __init__(self, max_events_per_room: int = 5000) -> None:
        self._events: dict[str, deque[dict[str, Any]]] = {}
        self._max_events = max_events_per_room
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _room_lock(self, room_code: str) -> asyncio.Lock:
        async with self._guard:
            return self._locks.setdefault(room_code.upper(), asyncio.Lock())

    async def append(self, room_code: str, event: dict[str, Any]) -> None:
        code = room_code.upper()
        lock = await self._room_lock(code)
        async with lock:
            history = self._events.setdefault(code, deque(maxlen=self._max_events))
            history.append(event)

    async def snapshot(self, room_code: str) -> list[dict[str, Any]]:
        code = room_code.upper()
        lock = await self._room_lock(code)
        async with lock:
            return list(self._events.get(code, ()))

    async def clear(self, room_code: str) -> None:
        code = room_code.upper()
        lock = await self._room_lock(code)
        async with lock:
            self._events[code] = deque(maxlen=self._max_events)

    async def remove_room(self, room_code: str) -> None:
        code = room_code.upper()
        lock = await self._room_lock(code)
        async with lock:
            self._events.pop(code, None)


drawing_state_store = DrawingStateStore()
