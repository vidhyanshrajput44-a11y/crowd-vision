"""WebSocket notification service managing event-scoped real-time updates and broadcast channels."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Optional

import orjson
from fastapi import WebSocket

from app.monitoring.logger import get_logger
from app.schemas.models import AlertResponse, Recommendation, RiskLevel, WSMessage

logger = get_logger("services.notification")


class NotificationService:
    """Manages active WebSocket connections and delivers low-latency notifications."""

    def __init__(self) -> None:
        # event_id -> set of WebSockets
        self._event_subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        # Global subscribers (listening to all events)
        self._global_subscribers: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, event_id: Optional[str] = None) -> None:
        """Register a new active WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            if event_id:
                self._event_subscribers[event_id].add(websocket)
            else:
                self._global_subscribers.add(websocket)
        logger.info("WebSocket client connected", event_id=event_id, total_clients=self.connection_count)

    async def disconnect(self, websocket: WebSocket, event_id: Optional[str] = None) -> None:
        """Deregister a disconnected WebSocket."""
        async with self._lock:
            if event_id and event_id in self._event_subscribers:
                self._event_subscribers[event_id].discard(websocket)
                if not self._event_subscribers[event_id]:
                    del self._event_subscribers[event_id]
            self._global_subscribers.discard(websocket)
        logger.info("WebSocket client disconnected", event_id=event_id, total_clients=self.connection_count)

    async def _send_to_sockets(self, sockets: set[WebSocket], payload_json: str) -> None:
        """Deliver JSON string to a collection of sockets, pruning dead connections."""
        dead_sockets: list[WebSocket] = []
        for ws in list(sockets):
            try:
                await ws.send_text(payload_json)
            except Exception:
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for ws in dead_sockets:
                    sockets.discard(ws)
                    self._global_subscribers.discard(ws)

    async def broadcast(self, message: WSMessage) -> None:
        """Send message to all subscribers (event-specific and global)."""
        payload_bytes = orjson.dumps(message.model_dump(mode="json"))
        payload_str = payload_bytes.decode("utf-8")

        targets: set[WebSocket] = set(self._global_subscribers)
        if message.event_id in self._event_subscribers:
            targets.update(self._event_subscribers[message.event_id])

        if targets:
            await self._send_to_sockets(targets, payload_str)

    async def notify_alert(self, alert: AlertResponse) -> None:
        """Broadcast new alert or escalation event."""
        msg = WSMessage(
            type="alert",
            event_id=alert.event_id,
            payload=alert.model_dump(mode="json"),
        )
        await self.broadcast(msg)

    async def notify_risk_change(
        self,
        event_id: str,
        zone_id: str,
        zone_name: str,
        old_risk: Optional[RiskLevel],
        new_risk: RiskLevel,
        explanation: Optional[str] = None,
    ) -> None:
        """Notify subscribers of a confirmed zone risk change."""
        msg = WSMessage(
            type="risk_change",
            event_id=event_id,
            payload={
                "zone_id": zone_id,
                "zone_name": zone_name,
                "old_risk": old_risk.value if old_risk else None,
                "new_risk": new_risk.value,
                "explanation": explanation,
            },
        )
        await self.broadcast(msg)

    async def notify_recommendation(self, event_id: str, rec: Recommendation) -> None:
        """Notify subscribers of newly generated operational recommendations."""
        msg = WSMessage(
            type="recommendation",
            event_id=event_id,
            payload=rec.model_dump(mode="json"),
        )
        await self.broadcast(msg)

    async def notify_insight(self, event_id: str, title: str, content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        """Notify subscribers of an analytical insight."""
        msg = WSMessage(
            type="insight",
            event_id=event_id,
            payload={
                "title": title,
                "content": content,
                "metadata": metadata or {},
            },
        )
        await self.broadcast(msg)

    @property
    def connection_count(self) -> int:
        """Total active connection count."""
        event_conns = sum(len(s) for s in self._event_subscribers.values())
        return event_conns + len(self._global_subscribers)
