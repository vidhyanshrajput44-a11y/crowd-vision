"""Alert queries, statistics, creation, and acknowledge/resolve workflow endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, security_scheme
from app.database.models import Alert, User
from app.database.session import get_db
from app.schemas.api_schemas import (
    AlertAcknowledgeRequest,
    AlertCreateRequest,
    AlertResolveRequest,
    AlertResponse,
    AlertStatsResponse,
)

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_operator(credentials, db: AsyncSession) -> str:
    if credentials:
        payload = decode_access_token(credentials.credentials)
        if payload and "sub" in payload:
            return payload["sub"]
    return "operator"


class AlertStatusPatchRequest(BaseModel):
    status: str
    note: Optional[str] = None


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    target_id = event_id or task_id
    stmt = select(Alert).order_by(desc(Alert.created_at))
    if target_id:
        stmt = stmt.where(Alert.event_id == target_id)
    if status:
        stmt = stmt.where(Alert.status == status.upper())
    if severity:
        stmt = stmt.where(Alert.severity == severity.upper())
    if category:
        stmt = stmt.where(Alert.category == category.lower())
    if zone_id:
        stmt = stmt.where(Alert.zone_id == zone_id)
    stmt = stmt.offset(offset).limit(limit)

    alerts = (await db.execute(stmt)).scalars().all()
    return [AlertResponse.model_validate(a) for a in alerts]


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
):
    """Retrieve statistical breakdown of alerts across severities, categories, and resolution states."""
    target_id = event_id or task_id
    stmt = select(Alert)
    if target_id:
        stmt = stmt.where(Alert.event_id == target_id)

    alerts = (await db.execute(stmt)).scalars().all()

    total = len(alerts)
    active = sum(1 for a in alerts if a.status == "ACTIVE")
    acknowledged = sum(1 for a in alerts if a.status == "ACKNOWLEDGED")
    resolved = sum(1 for a in alerts if a.status == "RESOLVED")

    by_sev: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_cat: dict[str, int] = {}

    for a in alerts:
        s = a.severity.upper()
        by_sev[s] = by_sev.get(s, 0) + 1
        c = a.category.lower()
        by_cat[c] = by_cat.get(c, 0) + 1

    return AlertStatsResponse(
        total=total,
        active=active,
        acknowledged=acknowledged,
        resolved=resolved,
        by_severity=by_sev,
        by_category=by_cat,
    )


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Manually create or inject an alert from operator or external monitoring sensor."""
    alert = Alert(
        id=f"alt_{uuid.uuid4().hex[:12]}",
        event_id=payload.event_id,
        zone_id=payload.zone_id or "zone_general",
        zone_name=payload.zone_name or "General Area",
        category=payload.category,
        severity=payload.severity.upper(),
        title=payload.title,
        description=payload.description,
        supporting_measurements=payload.supporting_measurements,
        status="ACTIVE",
        video_timestamp_sec=0.0,
        source=payload.source,
        created_at=_utcnow(),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Optional[Any] = Depends(security_scheme),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    if alert.status == "RESOLVED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Alert is already resolved")

    user_email = await _resolve_operator(credentials, db)
    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = user_email
    alert.acknowledged_at = _utcnow()
    if payload.note:
        alert.resolution_note = (
            f"[Ack Note: {payload.note}] " + (alert.resolution_note or "")
        ).strip()

    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    payload: AlertResolveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Optional[Any] = Depends(security_scheme),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    user_email = await _resolve_operator(credentials, db)
    alert.status = "RESOLVED"
    alert.resolved_by = user_email
    alert.resolved_at = _utcnow()
    if payload.resolution_note:
        alert.resolution_note = payload.resolution_note

    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}/status", response_model=AlertResponse)
async def update_alert_status(
    alert_id: str,
    payload: AlertStatusPatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Optional[Any] = Depends(security_scheme),
):
    """Backwards-compatible PATCH endpoint for quick alert state update."""
    st = payload.status.upper()
    if st == "ACKNOWLEDGED":
        return await acknowledge_alert(
            alert_id=alert_id,
            payload=AlertAcknowledgeRequest(note=payload.note),
            db=db,
            credentials=credentials,
        )
    elif st == "RESOLVED":
        return await resolve_alert(
            alert_id=alert_id,
            payload=AlertResolveRequest(resolution_note=payload.note),
            db=db,
            credentials=credentials,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported status '{payload.status}'. Must be ACKNOWLEDGED or RESOLVED.",
        )
