"""WebSocket endpoint for client subscription to real-time crowd metrics and alerts."""
from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.services.ws_manager import ws_manager

router = APIRouter()
logger = get_logger("api.websocket")


@router.websocket("/ws/events/{event_id}")
@router.websocket("/ws/tasks/{event_id}")
@router.websocket("/ws/{event_id}")
async def websocket_endpoint(websocket: WebSocket, event_id: str):
    await ws_manager.connect(event_id, websocket)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "event_id": event_id,
                    "task_id": event_id,
                    "message": "Subscribed to CROWD VISION real-time telemetry stream",
                }
            )
        )
        while True:
            raw = await websocket.receive_text()
            if raw.strip().lower() == "ping":
                await websocket.send_text(
                    json.dumps({"type": "pong", "event_id": event_id, "task_id": event_id})
                )
    except WebSocketDisconnect:
        await ws_manager.disconnect(event_id, websocket)
    except Exception as exc:
        logger.debug("WebSocket error", error=str(exc))
        await ws_manager.disconnect(event_id, websocket)
