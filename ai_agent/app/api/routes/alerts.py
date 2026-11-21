"""Alert management and resolution route handlers."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.middleware.auth import verify_api_key
from app.core.orchestrator import AgentOrchestrator
from app.dependencies import get_alert_manager, get_orchestrator
from app.monitoring.logger import get_logger
from app.schemas.models import (
    AlertAcknowledgeRequest,
    AlertListResponse,
    AlertResolveRequest,
    AlertResponse,
)

logger = get_logger("routes.alerts")
router = APIRouter(prefix="/api/v1/agent", tags=["alerts"])


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    event_id: str,
    zone_id: Optional[str] = None,
    priority: Optional[str] = None,
    state: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _: str = Depends(verify_api_key),
) -> AlertListResponse:
    """Query active or historical alerts with filtering and pagination."""
    alerts = orchestrator.get_alerts(
        event_id=event_id,
        zone_id=zone_id,
        priority=priority,
        state=state,
    )
    total = len(alerts)
    start_idx = (page - 1) * page_size
    paged = alerts[start_idx : start_idx + page_size]

    return AlertListResponse(
        alerts=paged,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: str,
    request: AlertAcknowledgeRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _: str = Depends(verify_api_key),
) -> AlertResponse:
    """Acknowledge an alert, pausing unacknowledged escalation timeouts."""
    updated = await orchestrator.acknowledge_alert(alert_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found",
        )
    return updated


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    request: AlertResolveRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _: str = Depends(verify_api_key),
) -> AlertResponse:
    """Mark an active alert as resolved."""
    updated = await orchestrator.resolve_alert(alert_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found",
        )
    return updated


@router.get("/alerts/{alert_id}/history")
async def get_alert_history(
    alert_id: str,
    alert_manager = Depends(get_alert_manager),
    _: str = Depends(verify_api_key),
) -> dict:
    """Retrieve chronological audit trail of state transitions for an alert."""
    history = alert_manager.get_alert_history(alert_id=alert_id)
    return {"alert_id": alert_id, "history": history}
