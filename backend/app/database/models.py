"""Relational SQLAlchemy 2.0 ORM schema for CrowdVision Platform."""

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


def new_uuid() -> str:
    """Generate string UUID4."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="operator", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    floorplan_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    calibration_homography: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_calibrated: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    zones: Mapped[list["Zone"]] = relationship("Zone", back_populates="venue", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    venue_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("venues.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), default="general")
    status: Mapped[str] = mapped_column(String(32), default="planning", index=True)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_attendance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)



class VenueLayout(Base):
    __tablename__ = "venue_layouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    venue_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    camera_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scale_pixels_per_meter: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    canvas_width: Mapped[int] = mapped_column(Integer, default=1920)
    canvas_height: Mapped[int] = mapped_column(Integer, default=1080)
    zones_data: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    scale_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    background_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    calibration_homography: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    venue_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(64), default="general")
    polygon_points: Mapped[list[Any]] = mapped_column(JSON, default=list)
    color: Mapped[str] = mapped_column(String(32), default="#3B82F6")
    adjacent_zone_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_emergency_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    venue: Mapped[Optional["Venue"]] = relationship("Venue", back_populates="zones")
    capacity: Mapped[Optional["ZoneCapacity"]] = relationship("ZoneCapacity", back_populates="zone", uselist=False, cascade="all, delete-orphan")


class ZoneCapacity(Base):
    __tablename__ = "zone_capacities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    zone_id: Mapped[str] = mapped_column(String(36), ForeignKey("zones.id", ondelete="CASCADE"), index=True, nullable=False)
    max_capacity: Mapped[int] = mapped_column(Integer, default=500)
    area_sqm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_physically_calibrated: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold_low: Mapped[float] = mapped_column(Float, default=0.5)
    threshold_moderate: Mapped[float] = mapped_column(Float, default=0.7)
    threshold_high: Mapped[float] = mapped_column(Float, default=0.85)
    threshold_critical: Mapped[float] = mapped_column(Float, default=0.95)
    density_moderate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density_critical: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    zone: Mapped["Zone"] = relationship("Zone", back_populates="capacity")


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    input_type: Mapped[str] = mapped_column(String(64), default="file")
    source_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    associated_zone_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    perspective: Mapped[str] = mapped_column(String(64), default="drone_top_down")
    is_moving_camera: Mapped[bool] = mapped_column(Boolean, default=False)
    layout_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    calibration_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)



class VideoFile(Base):
    __tablename__ = "video_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    camera_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frame_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    video_file_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    camera_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    detector_backend: Mapped[str] = mapped_column(String(64), default="yolo")
    sample_fps: Mapped[float] = mapped_column(Float, default=2.0)
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    total_sampled_frames: Mapped[int] = mapped_column(Integer, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    processing_fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_inference_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_people_detected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    layout_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    camera_perspective: Mapped[str] = mapped_column(String(64), default="drone_top_down")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class DetectionSummary(Base):
    __tablename__ = "detection_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    video_timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    total_people: Mapped[int] = mapped_column(Integer, default=0)
    inference_ms: Mapped[float] = mapped_column(Float, default=0.0)
    detections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    heatmap_grid: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



    __table_args__ = (
        Index("ix_det_job_ts", "job_id", "video_timestamp_sec"),
    )


class CrowdMetric(Base):
    __tablename__ = "crowd_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    zone_name: Mapped[str] = mapped_column(String(255), nullable=False)
    video_timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    people_count: Mapped[int] = mapped_column(Integer, default=0)
    occupancy_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    density_value: Mapped[float] = mapped_column(Float, default=0.0)
    density_unit: Mapped[str] = mapped_column(String(32), default="ppl/m2")
    inflow_rate: Mapped[float] = mapped_column(Float, default=0.0)
    outflow_rate: Mapped[float] = mapped_column(Float, default=0.0)
    net_flow: Mapped[float] = mapped_column(Float, default=0.0)
    avg_speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    movement_direction: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    crowd_increase_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capacity_utilization_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_bottleneck: Mapped[bool] = mapped_column(Boolean, default=False)
    is_counterflow: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_cm_event_zone_ts", "event_id", "zone_id", "video_timestamp_sec"),
    )


class PredictionRecord(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    zone_name: Mapped[str] = mapped_column(String(255), nullable=False)
    video_timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    horizon_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    current_occupancy: Mapped[float] = mapped_column(Float, default=0.0)
    current_density: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_occupancy: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_density: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_trend: Mapped[str] = mapped_column(String(32), default="stable")
    risk_category: Mapped[str] = mapped_column(String(32), default="NORMAL")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    is_experimental: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_occupancy_later: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    absolute_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(64), default="linear_trend_ema_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



    __table_args__ = (
        Index("ix_pred_event_zone_ts", "event_id", "zone_id", "video_timestamp_sec"),
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    zone_name: Mapped[str] = mapped_column(String(255), nullable=False)
    video_timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="NORMAL")
    reason: Mapped[str] = mapped_column(Text, default="All indicators normal")
    supporting_measurements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    monitoring_priority: Mapped[str] = mapped_column(String(32), default="ROUTINE")
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    zone_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="occupancy_warning")
    severity: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_measurements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    video_timestamp_sec: Mapped[float] = mapped_column(Float, default=0.0)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="RISK_ENGINE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    zone_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(512), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    suggested_team: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    supporting_data: Mapped[list[Any]] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="AI_AGENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class OperatorAction(Base):
    __tablename__ = "operator_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class ReportRecord(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    component: Mapped[str] = mapped_column(String(64), default="system")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class SingleImageAnalysis(Base):
    __tablename__ = "single_image_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    venue_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    layout_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    image_url: Mapped[str] = mapped_column(String(512), nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    total_people: Mapped[int] = mapped_column(Integer, default=0)
    inference_ms: Mapped[float] = mapped_column(Float, default=0.0)
    detector_backend: Mapped[str] = mapped_column(String(64), default="yolo")
    camera_perspective: Mapped[str] = mapped_column(String(64), default="drone_top_down")
    detections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    heatmap_grid: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    zone_occupancies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    analysis_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disclaimer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Aliases for backwards and route compatibility
Prediction = PredictionRecord
Report = ReportRecord


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    layout_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("venue_layouts.id", ondelete="SET NULL"), nullable=True)
    layout_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    video_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    analysis_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    history: Mapped[list["TaskHistory"]] = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan", order_by="desc(TaskHistory.timestamp)", lazy="selectin")


class TaskHistory(Base):
    __tablename__ = "task_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped["Task"] = relationship("Task", back_populates="history")

