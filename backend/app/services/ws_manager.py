"""WebSocket manager for real-time live streaming of crowd metrics and heatmaps."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("services.ws_manager")


class WebSocketManager:
    """Manages active WebSocket connections grouped by event_id."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, event_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if event_id not in self._connections:
                self._connections[event_id] = []
            self._connections[event_id].append(ws)
        logger.info("WebSocket client connected", event_id=event_id, total=len(self._connections[event_id]))

    async def disconnect(self, event_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if event_id in self._connections:
                if ws in self._connections[event_id]:
                    self._connections[event_id].remove(ws)
                if not self._connections[event_id]:
                    del self._connections[event_id]
        logger.info("WebSocket client disconnected", event_id=event_id)

    async def broadcast(self, event_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._connections.get(event_id, []))

        if not conns:
            return

        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(event_id, ws)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        event_ids = list(self._connections.keys())
        for eid in event_ids:
            await self.broadcast(eid, message)

    def connection_count(self, event_id: Optional[str] = None) -> int:
        if event_id:
            return len(self._connections.get(event_id, []))
        return sum(len(c) for c in self._connections.values())


ws_manager = WebSocketManager()
