"""SQLAlchemy 2.0 ORM models for CrowdVision AI Agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base class for all database models."""
    pass


class EventRecord(Base):
    """Event registration and venue configuration record."""
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    event_name: Mapped[str] = mapped_column(String(256), nullable=False)
    venue_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    venue_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CrowdDataRecord(Base):
    """Raw structured analytical snapshot received from the computer vision pipeline."""
    __tablename__ = "crowd_data"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    venue_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    camera_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    people_count: Mapped[int] = mapped_column(Integer, nullable=False)
    current_occupancy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inflow_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outflow_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    movement_direction: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    movement_speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density_growth_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_occupancy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forecast_horizon_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    forecast_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_crowd_data_event_zone_ts", "event_id", "zone_id", "timestamp"),
    )


class RiskAssessmentRecord(Base):
    """Historical risk assessment calculations."""
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    previous_risk_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    occupancy_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    people_count: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    inflow_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outflow_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    congestion_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_risk_event_zone_ts", "event_id", "zone_id", "timestamp"),
    )


class AlertRecord(Base):
    """Alert entity tracking lifecycle, state changes, escalation, and human resolutions."""
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    zone_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="NEW", index=True, nullable=False)
    risk_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_alerts_event_state", "event_id", "state"),
        Index("ix_alerts_event_zone", "event_id", "zone_id"),
    )


class RecommendationRecord(Base):
    """Generated context-aware recommendations."""
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    zone_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    action: Mapped[str] = mapped_column(String(512), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    suggested_team: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    supporting_observations: Mapped[list[str]] = mapped_column(JSON, default=list)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedbackRecord(Base):
    """Human feedback records on alerts, recommendations, or analyses."""
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    feedback: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditRecord(Base):
    """Audit trail for critical operational events and configuration changes."""
    __tablename__ = "audit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    old_value: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    performed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
