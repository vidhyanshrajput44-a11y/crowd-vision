"""WebSocket route endpoints for live real-time push streaming."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dependencies import get_notification
from app.monitoring.logger import get_logger
from app.services.notification import NotificationService

logger = get_logger("websocket.handler")
router = APIRouter(tags=["websockets"])


@router.websocket("/ws/{event_id}")
async def websocket_event_endpoint(
    websocket: WebSocket,
    event_id: str,
    notification_service: NotificationService = Depends(get_notification),
) -> None:
    """Event-scoped WebSocket connection streaming live alerts, risk shifts, and recommendations."""
    await notification_service.connect(websocket, event_id=event_id)
    try:
        while True:
            # Keep-alive heartbeat & client message handling
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        await notification_service.disconnect(websocket, event_id=event_id)
    except Exception as exc:
        logger.error("WebSocket unexpected error", event_id=event_id, error=str(exc))
        await notification_service.disconnect(websocket, event_id=event_id)


@router.websocket("/ws")
async def websocket_global_endpoint(
    websocket: WebSocket,
    notification_service: NotificationService = Depends(get_notification),
) -> None:
    """Global broadcast WebSocket connection receiving system-wide telemetry and alerts."""
    await notification_service.connect(websocket, event_id=None)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        await notification_service.disconnect(websocket, event_id=None)
    except Exception as exc:
        logger.error("Global WebSocket error", error=str(exc))
        await notification_service.disconnect(websocket, event_id=None)
