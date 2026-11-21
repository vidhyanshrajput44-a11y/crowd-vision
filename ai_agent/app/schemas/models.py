"""Pydantic schemas for all API request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ════════════════════════════════════════════════════════════════
# Enumerations
# ════════════════════════════════════════════════════════════════

class RiskLevel(str, Enum):
    NORMAL = "NORMAL"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def severity_order(self) -> int:
        return {"NORMAL": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}[self.value]

    def __ge__(self, other: RiskLevel) -> bool:
        return self.severity_order >= other.severity_order

    def __gt__(self, other: RiskLevel) -> bool:
        return self.severity_order > other.severity_order

    def __le__(self, other: RiskLevel) -> bool:
        return self.severity_order <= other.severity_order

    def __lt__(self, other: RiskLevel) -> bool:
        return self.severity_order < other.severity_order


class AlertState(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class AlertPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MovementDirection(str, Enum):
    INWARD = "INWARD"
    OUTWARD = "OUTWARD"
    LATERAL = "LATERAL"
    MIXED = "MIXED"
    STATIONARY = "STATIONARY"
    UNKNOWN = "UNKNOWN"


class RecommendationPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ForecastHorizon(str, Enum):
    ONE_MIN = "1m"
    THREE_MIN = "3m"
    FIVE_MIN = "5m"
    TEN_MIN = "10m"
    FIFTEEN_MIN = "15m"
    THIRTY_MIN = "30m"


# ════════════════════════════════════════════════════════════════
# Zone Configuration
# ════════════════════════════════════════════════════════════════

class ZoneConfig(BaseModel):
    """Venue zone configuration with capacity and threshold settings."""
    zone_id: str
    zone_name: str
    capacity: int = Field(gt=0, description="Max safe occupancy")
    area_sqm: Optional[float] = Field(None, gt=0, description="Zone area in sq metres")
    adjacent_zones: list[str] = Field(default_factory=list)
    is_entry: bool = False
    is_exit: bool = False
    is_emergency_exit: bool = False

    # Configurable risk thresholds (fraction of capacity)
    threshold_low: float = Field(0.5, ge=0, le=1)
    threshold_moderate: float = Field(0.7, ge=0, le=1)
    threshold_high: float = Field(0.85, ge=0, le=1)
    threshold_critical: float = Field(0.95, ge=0, le=1)

    # Density thresholds (people/sqm) — optional, used only when area_sqm is set
    density_moderate: Optional[float] = Field(None, gt=0)
    density_high: Optional[float] = Field(None, gt=0)
    density_critical: Optional[float] = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_thresholds_ascending(self) -> ZoneConfig:
        thresholds = [self.threshold_low, self.threshold_moderate,
                      self.threshold_high, self.threshold_critical]
        for i in range(len(thresholds) - 1):
            if thresholds[i] >= thresholds[i + 1]:
                raise ValueError(
                    "Risk thresholds must be strictly ascending: "
                    "low < moderate < high < critical"
                )
        return self


class VenueConfig(BaseModel):
    """Venue configuration."""
    venue_id: str
    venue_name: str
    zones: list[ZoneConfig]
    total_capacity: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_zone(self, zone_id: str) -> Optional[ZoneConfig]:
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        return None


# ════════════════════════════════════════════════════════════════
# Crowd Data Input (from main CrowdVision app)
# ════════════════════════════════════════════════════════════════

class CrowdDataInput(BaseModel):
    """Structured crowd analytics from the main application."""
    # Identifiers
    event_id: str
    camera_id: Optional[str] = None
    venue_id: str
    zone_id: str
    timestamp: datetime

    # Current measurements
    people_count: int = Field(ge=0)
    estimated_density: Optional[float] = Field(None, ge=0, description="People per sq metre")
    current_occupancy: Optional[float] = Field(None, ge=0, le=1, description="Fraction of capacity")
    inflow_rate: Optional[float] = Field(None, ge=0, description="People per minute entering")
    outflow_rate: Optional[float] = Field(None, ge=0, description="People per minute leaving")

    # Movement
    movement_direction: Optional[MovementDirection] = None
    movement_speed: Optional[float] = Field(None, ge=0, description="Average m/s")

    # Trends
    density_growth_rate: Optional[float] = Field(None, description="Change per minute")

    # Predictions from main app
    predicted_density: Optional[float] = Field(None, ge=0)
    predicted_occupancy: Optional[float] = Field(None, ge=0)
    forecast_horizon_seconds: Optional[int] = Field(None, gt=0)
    forecast_confidence: Optional[float] = Field(None, ge=0, le=1)

    # Additional predictions at multiple horizons
    multi_horizon_forecasts: Optional[list[ForecastPoint]] = None

    # Idempotency
    message_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))


class ForecastPoint(BaseModel):
    """A single forecast at a specific time horizon."""
    horizon_seconds: int = Field(gt=0)
    predicted_density: Optional[float] = Field(None, ge=0)
    predicted_occupancy: Optional[float] = Field(None, ge=0)
    predicted_count: Optional[int] = Field(None, ge=0)
    confidence: Optional[float] = Field(None, ge=0, le=1)


# Fix forward reference
CrowdDataInput.model_rebuild()


# ════════════════════════════════════════════════════════════════
# Analysis Output
# ════════════════════════════════════════════════════════════════

class RiskFactor(BaseModel):
    """Individual factor contributing to risk assessment."""
    factor: str
    description: str
    severity: RiskLevel
    value: Optional[float] = None
    threshold: Optional[float] = None


class ZoneRiskAssessment(BaseModel):
    """Risk assessment for a single zone."""
    zone_id: str
    zone_name: str
    risk_level: RiskLevel
    previous_risk_level: Optional[RiskLevel] = None
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    occupancy_ratio: Optional[float] = None
    density: Optional[float] = None
    people_count: int = 0
    capacity: int = 0
    inflow_rate: Optional[float] = None
    outflow_rate: Optional[float] = None
    net_flow: Optional[float] = None
    congestion_duration_seconds: Optional[float] = None
    timestamp: datetime
    explanation: Optional[str] = None


class PredictionInterpretation(BaseModel):
    """Interpreted prediction for a zone."""
    zone_id: str
    zone_name: str
    current_risk: RiskLevel
    predicted_risk: RiskLevel
    forecast_horizon_seconds: int
    predicted_occupancy: Optional[float] = None
    predicted_density: Optional[float] = None
    growth_trend: str = "stable"  # "increasing", "decreasing", "stable", "rapid_increase", "rapid_decrease"
    confidence: Optional[float] = None
    is_emerging_hotspot: bool = False
    is_low_confidence: bool = False
    explanation: str = ""


class AnalysisResult(BaseModel):
    """Complete analysis result for one processing cycle."""
    event_id: str
    timestamp: datetime
    zones_analyzed: int = 0
    risk_assessments: list[ZoneRiskAssessment] = Field(default_factory=list)
    predictions: list[PredictionInterpretation] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    new_alerts: list[AlertResponse] = Field(default_factory=list)
    processing_time_ms: float = 0


# ════════════════════════════════════════════════════════════════
# Recommendations
# ════════════════════════════════════════════════════════════════

class Recommendation(BaseModel):
    """Context-aware recommendation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: str
    reason: str
    affected_zone: str
    affected_zone_name: Optional[str] = None
    priority: RecommendationPriority
    supporting_observations: list[str] = Field(default_factory=list)
    suggested_team: Optional[str] = None
    requires_human_approval: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_id: Optional[str] = None
    expiry_seconds: Optional[int] = None


# ════════════════════════════════════════════════════════════════
# Alerts
# ════════════════════════════════════════════════════════════════

class AlertCreate(BaseModel):
    """Internal alert creation model."""
    event_id: str
    zone_id: str
    zone_name: Optional[str] = None
    alert_type: str
    title: str
    description: str
    priority: AlertPriority
    risk_level: RiskLevel
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertResponse(BaseModel):
    """Alert response for API."""
    id: str
    event_id: str
    zone_id: str
    zone_name: Optional[str] = None
    alert_type: str
    title: str
    description: str
    priority: AlertPriority
    risk_level: RiskLevel
    state: AlertState = AlertState.NEW
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    escalation_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertAcknowledgeRequest(BaseModel):
    acknowledged_by: str


class AlertResolveRequest(BaseModel):
    resolved_by: str
    resolution_note: Optional[str] = None


# ════════════════════════════════════════════════════════════════
# Chat / Conversational
# ════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    """Chat request from event managers."""
    event_id: str
    message: str
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    venue_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response from the agent."""
    session_id: str
    response: str
    tool_calls_made: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_data_stale: bool = False
    stale_warning: Optional[str] = None


# ════════════════════════════════════════════════════════════════
# Feedback
# ════════════════════════════════════════════════════════════════

class FeedbackRequest(BaseModel):
    """Human feedback on agent actions."""
    event_id: str
    target_type: str  # "alert", "recommendation", "analysis"
    target_id: str
    feedback: str  # "helpful", "not_helpful", "incorrect", "acted_on", "ignored"
    comment: Optional[str] = None
    submitted_by: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: str
    received: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ════════════════════════════════════════════════════════════════
# Event Management
# ════════════════════════════════════════════════════════════════

class EventCreate(BaseModel):
    """Create or register a new event."""
    event_id: str
    event_name: str
    venue: VenueConfig
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    event_id: str
    event_name: str
    venue_id: str
    status: str = "active"
    created_at: datetime
    zones_count: int = 0


# ════════════════════════════════════════════════════════════════
# Status / Health
# ════════════════════════════════════════════════════════════════

class AgentStatus(BaseModel):
    """Agent operational status."""
    status: str = "operational"
    uptime_seconds: float = 0
    events_active: int = 0
    zones_monitored: int = 0
    alerts_active: int = 0
    queue_depth: int = 0
    llm_available: bool = False
    redis_available: bool = False
    database_available: bool = False
    last_analysis_at: Optional[datetime] = None
    version: str = "1.0.0"


class HealthResponse(BaseModel):
    status: str = "healthy"
    checks: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ════════════════════════════════════════════════════════════════
# WebSocket Messages
# ════════════════════════════════════════════════════════════════

class WSMessage(BaseModel):
    """WebSocket message envelope."""
    type: str  # "alert", "risk_change", "recommendation", "insight", "status"
    event_id: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ════════════════════════════════════════════════════════════════
# API Wrappers
# ════════════════════════════════════════════════════════════════

class AnalyzeRequest(BaseModel):
    """Batch analysis request."""
    data: list[CrowdDataInput]


class AnalyzeResponse(BaseModel):
    """Batch analysis response."""
    accepted: int = 0
    duplicates_skipped: int = 0
    results: Optional[AnalysisResult] = None
    processing_time_ms: float = 0


class ZoneAnalysisResponse(BaseModel):
    """Detailed zone analysis response."""
    zone_id: str
    zone_name: str
    risk_assessment: Optional[ZoneRiskAssessment] = None
    latest_prediction: Optional[PredictionInterpretation] = None
    active_alerts: list[AlertResponse] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    recent_history: list[dict[str, Any]] = Field(default_factory=list)


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int = 0
    page: int = 1
    page_size: int = 50


class RecommendationListResponse(BaseModel):
    recommendations: list[Recommendation]
    total: int = 0


# Rebuild models with forward references
AnalysisResult.model_rebuild()
