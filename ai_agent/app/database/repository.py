"""Asynchronous repository for all persistent database operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AlertRecord,
    AuditRecord,
    CrowdDataRecord,
    EventRecord,
    FeedbackRecord,
    RecommendationRecord,
    RiskAssessmentRecord,
    utcnow,
)
from app.monitoring.logger import get_logger
from app.schemas.models import (
    AlertCreate,
    AlertPriority,
    AlertResponse,
    AlertState,
    CrowdDataInput,
    EventCreate,
    FeedbackRequest,
    Recommendation,
    RiskLevel,
    ZoneRiskAssessment,
)

logger = get_logger("database.repository")


class Repository:
    """Async repository providing unified CRUD operations."""

    # ── Events ───────────────────────────────────────────────────

    @staticmethod
    async def save_event(session: AsyncSession, event: EventCreate) -> EventRecord:
        """Register or update an event and its venue configuration."""
        stmt = select(EventRecord).where(EventRecord.event_id == event.event_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.event_name = event.event_name
            existing.venue_id = event.venue.venue_id
            existing.venue_config = event.venue.model_dump()
            existing.updated_at = utcnow()
            return existing

        record = EventRecord(
            id=str(uuid.uuid4()),
            event_id=event.event_id,
            event_name=event.event_name,
            venue_id=event.venue.venue_id,
            venue_config=event.venue.model_dump(),
            status="active",
        )
        session.add(record)
        return record

    @staticmethod
    async def get_event(session: AsyncSession, event_id: str) -> Optional[EventRecord]:
        """Fetch event record by event_id."""
        stmt = select(EventRecord).where(EventRecord.event_id == event_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Crowd Data Snapshots ─────────────────────────────────────

    @staticmethod
    async def save_crowd_data(session: AsyncSession, data: CrowdDataInput) -> CrowdDataRecord:
        """Persist structured analytics received from computer vision."""
        record = CrowdDataRecord(
            id=str(uuid.uuid4()),
            event_id=data.event_id,
            venue_id=data.venue_id,
            zone_id=data.zone_id,
            camera_id=data.camera_id,
            people_count=data.people_count,
            current_occupancy=data.current_occupancy,
            estimated_density=data.estimated_density,
            inflow_rate=data.inflow_rate,
            outflow_rate=data.outflow_rate,
            movement_direction=data.movement_direction.value if data.movement_direction else None,
            movement_speed=data.movement_speed,
            density_growth_rate=data.density_growth_rate,
            predicted_occupancy=data.predicted_occupancy,
            predicted_density=data.predicted_density,
            forecast_horizon_seconds=data.forecast_horizon_seconds,
            forecast_confidence=data.forecast_confidence,
            raw_payload=data.model_dump(mode="json"),
            timestamp=data.timestamp,
        )
        session.add(record)
        return record

    @staticmethod
    async def get_recent_crowd_data(
        session: AsyncSession,
        event_id: str,
        zone_id: str,
        minutes: int = 30,
    ) -> list[CrowdDataRecord]:
        """Fetch historical crowd analytics snapshots for a specific zone."""
        since = utcnow() - timedelta(minutes=minutes)
        stmt = (
            select(CrowdDataRecord)
            .where(
                CrowdDataRecord.event_id == event_id,
                CrowdDataRecord.zone_id == zone_id,
                CrowdDataRecord.timestamp >= since,
            )
            .order_by(CrowdDataRecord.timestamp.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ── Risk Assessments ─────────────────────────────────────────

    @staticmethod
    async def save_risk_assessment(
        session: AsyncSession,
        assessment: ZoneRiskAssessment,
        event_id: str,
    ) -> RiskAssessmentRecord:
        """Persist a computed risk assessment."""
        record = RiskAssessmentRecord(
            id=str(uuid.uuid4()),
            event_id=event_id,
            zone_id=assessment.zone_id,
            risk_level=assessment.risk_level.value,
            previous_risk_level=assessment.previous_risk_level.value if assessment.previous_risk_level else None,
            occupancy_ratio=assessment.occupancy_ratio,
            density=assessment.density,
            people_count=assessment.people_count,
            capacity=assessment.capacity,
            inflow_rate=assessment.inflow_rate,
            outflow_rate=assessment.outflow_rate,
            net_flow=assessment.net_flow,
            congestion_duration_seconds=assessment.congestion_duration_seconds,
            risk_factors=[f.model_dump(mode="json") for f in assessment.risk_factors],
            explanation=assessment.explanation,
            timestamp=assessment.timestamp,
        )
        session.add(record)
        return record

    # ── Alerts ───────────────────────────────────────────────────

    @staticmethod
    async def save_alert(session: AsyncSession, alert: AlertResponse) -> AlertRecord:
        """Persist or update an alert entity."""
        stmt = select(AlertRecord).where(AlertRecord.id == alert.id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.state = alert.state.value
            existing.priority = alert.priority.value
            existing.risk_level = alert.risk_level.value
            existing.escalation_count = alert.escalation_count
            existing.acknowledged_at = alert.acknowledged_at
            existing.acknowledged_by = alert.acknowledged_by
            existing.resolved_at = alert.resolved_at
            existing.resolved_by = alert.resolved_by
            existing.resolution_note = alert.resolution_note
            existing.updated_at = utcnow()
            return existing

        record = AlertRecord(
            id=alert.id,
            event_id=alert.event_id,
            zone_id=alert.zone_id,
            zone_name=alert.zone_name,
            alert_type=alert.alert_type,
            title=alert.title,
            description=alert.description,
            priority=alert.priority.value,
            risk_level=alert.risk_level.value,
            state=alert.state.value,
            risk_factors=[f.model_dump(mode="json") for f in alert.risk_factors],
            escalation_count=alert.escalation_count,
            metadata_=alert.metadata,
            created_at=alert.created_at,
        )
        session.add(record)
        return record

    @staticmethod
    async def get_alerts(
        session: AsyncSession,
        event_id: str,
        zone_id: Optional[str] = None,
        priority: Optional[str] = None,
        state: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AlertRecord], int]:
        """Fetch paginated, filtered alerts."""
        stmt = select(AlertRecord).where(AlertRecord.event_id == event_id)

        if zone_id:
            stmt = stmt.where(AlertRecord.zone_id == zone_id)
        if priority:
            stmt = stmt.where(AlertRecord.priority == priority.upper())
        if state:
            stmt = stmt.where(AlertRecord.state == state.upper())

        stmt = stmt.order_by(desc(AlertRecord.created_at))
        offset = (max(page, 1) - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await session.execute(stmt)
        records = list(result.scalars().all())
        return records, len(records)

    # ── Recommendations ──────────────────────────────────────────

    @staticmethod
    async def save_recommendation(
        session: AsyncSession,
        rec: Recommendation,
    ) -> RecommendationRecord:
        """Persist a generated recommendation."""
        record = RecommendationRecord(
            id=rec.id,
            event_id=rec.event_id or "unknown",
            zone_id=rec.affected_zone,
            zone_name=rec.affected_zone_name,
            action=rec.action,
            reason=rec.reason,
            priority=rec.priority.value,
            suggested_team=rec.suggested_team,
            requires_human_approval=rec.requires_human_approval,
            supporting_observations=rec.supporting_observations,
            timestamp=rec.timestamp,
        )
        session.add(record)
        return record

    # ── Feedback & Audit ─────────────────────────────────────────

    @staticmethod
    async def save_feedback(session: AsyncSession, feedback: FeedbackRequest) -> FeedbackRecord:
        """Persist human operational feedback."""
        record = FeedbackRecord(
            id=str(uuid.uuid4()),
            event_id=feedback.event_id,
            target_type=feedback.target_type,
            target_id=feedback.target_id,
            feedback=feedback.feedback,
            comment=feedback.comment,
            submitted_by=feedback.submitted_by,
        )
        session.add(record)
        return record

    @staticmethod
    async def save_audit(
        session: AsyncSession,
        event_id: Optional[str],
        action: str,
        entity_type: str,
        entity_id: str,
        old_value: Optional[dict[str, Any]] = None,
        new_value: Optional[dict[str, Any]] = None,
        performed_by: Optional[str] = None,
    ) -> AuditRecord:
        """Persist an audit log entry."""
        record = AuditRecord(
            id=str(uuid.uuid4()),
            event_id=event_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            performed_by=performed_by,
        )
        session.add(record)
        return record
