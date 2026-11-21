"""Pydantic v2 request and response schemas for CrowdVision Main Backend API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserPreferencesUpdate(BaseModel):
    preferences: dict[str, Any]


class ZoneLayoutItem(BaseModel):
    """Zone definition within a customizable venue layout."""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(default=None, alias="zone_id")
    name: Optional[str] = Field(default=None, alias="zone_name")
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: str = "GENERAL"
    polygon_points: list[list[float]] = Field(default_factory=list)
    color: str = "#0d9488"
    capacity: int = Field(default=100, alias="max_capacity")
    max_capacity: Optional[int] = None
    area_sqm: Optional[float] = None
    is_physically_calibrated: bool = False
    threshold_low: float = 0.45
    threshold_moderate: float = 0.65
    threshold_high: float = 0.82
    threshold_critical: float = 0.95
    monitoring_priority: str = "ROUTINE"
    description: Optional[str] = None
    is_entry: bool = False
    is_exit: bool = False
    is_emergency_exit: bool = False
    adjacent_zone_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            zid = data.get("id") or data.get("zone_id") or str(uuid.uuid4())
            zname = data.get("name") or data.get("zone_name") or zid
            raw_cap = data.get("capacity") if data.get("capacity") is not None else data.get("max_capacity")
            try:
                cap = int(raw_cap) if raw_cap is not None else 100
            except (ValueError, TypeError):
                cap = 100
            data["id"] = zid
            data["zone_id"] = zid
            data["name"] = zname
            data["zone_name"] = zname
            data["capacity"] = cap
            data["max_capacity"] = cap
            pts = data.get("polygon_points")
            if isinstance(pts, list):
                norm_pts = []
                for p in pts:
                    if isinstance(p, dict):
                        px = p.get("x") if p.get("x") is not None else p.get("lng")
                        py = p.get("y") if p.get("y") is not None else p.get("lat")
                        if px is None and 0 in p:
                            px = p[0]
                        if py is None and 1 in p:
                            py = p[1]
                        if px is not None and py is not None:
                            try:
                                norm_pts.append([float(px), float(py)])
                            except (ValueError, TypeError):
                                pass
                    elif isinstance(p, (list, tuple)) and len(p) >= 2:
                        p0 = p[0]
                        p1 = p[1]
                        if p0 is not None and p1 is not None:
                            try:
                                norm_pts.append([float(p0), float(p1)])
                            except (ValueError, TypeError):
                                pass
                data["polygon_points"] = norm_pts
        return data


class VenueLayoutCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: Optional[str] = None
    venue_id: Optional[str] = None
    event_id: Optional[str] = None
    camera_id: Optional[str] = None
    canvas_width: int = 1920
    canvas_height: int = 1080
    background_image_url: Optional[str] = None
    scale_factor: Optional[float] = None
    scale_pixels_per_meter: Optional[float] = None
    calibration_homography: Optional[list[list[float]]] = None
    zones_data: list[ZoneLayoutItem] = Field(default_factory=list, alias="zones")


class VenueLayoutUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    description: Optional[str] = None
    venue_id: Optional[str] = None
    event_id: Optional[str] = None
    camera_id: Optional[str] = None
    is_active: Optional[bool] = None
    scale_factor: Optional[float] = None
    scale_pixels_per_meter: Optional[float] = None
    canvas_width: Optional[int] = None
    canvas_height: Optional[int] = None
    background_image_url: Optional[str] = None
    calibration_homography: Optional[list[list[float]]] = None
    zones_data: Optional[list[ZoneLayoutItem]] = Field(default=None, alias="zones")


class VenueLayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    venue_id: Optional[str] = None
    event_id: Optional[str] = None
    camera_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    version: int
    is_active: bool = True
    scale_pixels_per_meter: Optional[float] = None
    canvas_width: int = 1920
    canvas_height: int = 1080
    background_image_url: Optional[str] = None
    zones_data: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ZoneCapacityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    max_capacity: int
    area_sqm: Optional[float] = None
    is_physically_calibrated: bool = False
    threshold_low: float = 0.45
    threshold_moderate: float = 0.65
    threshold_high: float = 0.82
    threshold_critical: float = 0.95
    density_moderate: Optional[float] = None
    density_high: Optional[float] = None
    density_critical: Optional[float] = None


class ZoneCreateRequest(BaseModel):
    name: str
    zone_type: str = "GENERAL"
    polygon_points: list[list[float]]
    color: str = "#0d9488"
    max_capacity: int = 50
    area_sqm: Optional[float] = None
    is_physically_calibrated: bool = False
    is_entry: bool = False
    is_exit: bool = False
    is_emergency_exit: bool = False
    adjacent_zone_ids: list[str] = Field(default_factory=list)
    threshold_low: float = 0.45
    threshold_moderate: float = 0.65
    threshold_high: float = 0.82
    threshold_critical: float = 0.95
    density_moderate: Optional[float] = None
    density_high: Optional[float] = None
    density_critical: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_points(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pts = data.get("polygon_points")
            if isinstance(pts, list):
                norm_pts = []
                for p in pts:
                    if isinstance(p, dict):
                        px = p.get("x") if p.get("x") is not None else p.get("lng")
                        py = p.get("y") if p.get("y") is not None else p.get("lat")
                        if px is not None and py is not None:
                            try:
                                norm_pts.append([float(px), float(py)])
                            except (ValueError, TypeError):
                                pass
                    elif isinstance(p, (list, tuple)) and len(p) >= 2:
                        p0, p1 = p[0], p[1]
                        if p0 is not None and p1 is not None:
                            try:
                                norm_pts.append([float(p0), float(p1)])
                            except (ValueError, TypeError):
                                pass
                data["polygon_points"] = norm_pts
        return data


class ZoneUpdateRequest(BaseModel):
    name: Optional[str] = None
    zone_type: Optional[str] = None
    polygon_points: Optional[list[list[float]]] = None
    color: Optional[str] = None
    max_capacity: Optional[int] = None
    area_sqm: Optional[float] = None
    is_physically_calibrated: Optional[bool] = None
    is_entry: Optional[bool] = None
    is_exit: Optional[bool] = None
    is_emergency_exit: Optional[bool] = None
    adjacent_zone_ids: Optional[list[str]] = None
    threshold_low: Optional[float] = None
    threshold_moderate: Optional[float] = None
    threshold_high: Optional[float] = None
    threshold_critical: Optional[float] = None
    density_moderate: Optional[float] = None
    density_high: Optional[float] = None
    density_critical: Optional[float] = None


class ZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    venue_id: str
    name: str
    zone_type: str
    polygon_points: list[list[float]]
    color: str
    is_entry: bool
    is_exit: bool
    is_emergency_exit: bool
    adjacent_zone_ids: list[str] = Field(default_factory=list)
    capacity: Optional[ZoneCapacityResponse] = None
    created_at: Optional[datetime] = None


class VenueCreateRequest(BaseModel):
    name: str
    location: Optional[str] = None
    venue_type: Optional[str] = "STADIUM"
    total_capacity: int = 1000


class VenueUpdateRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    total_capacity: Optional[int] = None
    is_calibrated: Optional[bool] = None
    calibration_homography: Optional[list[list[float]]] = None


class HomographyCalibrationRequest(BaseModel):
    image_points: list[list[float]]
    venue_points: list[list[float]]
    camera_id: Optional[str] = None
    layout_id: Optional[str] = None
    perspective: Optional[str] = "FIXED_CCTV"
    camera_perspective: Optional[str] = None
    scale_factor_m_per_px: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_perspective(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "camera_perspective" in data and not data.get("perspective"):
                data["perspective"] = data["camera_perspective"]
            elif "perspective" in data and not data.get("camera_perspective"):
                data["camera_perspective"] = data["perspective"]
        return data


class VenueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location: Optional[str] = None
    total_capacity: int
    floorplan_url: Optional[str] = None
    is_calibrated: bool = False
    zones: list[ZoneResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class EventCreateRequest(BaseModel):
    name: str
    venue_id: Optional[str] = None
    event_type: str = "CONCERT"
    expected_attendance: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class EventUpdateRequest(BaseModel):
    name: Optional[str] = None
    event_type: Optional[str] = None
    status: Optional[str] = None
    expected_attendance: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    settings: Optional[dict[str, Any]] = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    venue_id: str
    name: str
    event_type: str
    status: str
    expected_attendance: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class CameraCreateRequest(BaseModel):
    event_id: str
    name: str
    location: str = ""
    input_type: str = "RECORDED_VIDEO"
    perspective: str = "FIXED_CCTV"
    is_moving_camera: bool = False
    layout_id: Optional[str] = None
    calibration_data: dict[str, Any] = Field(default_factory=dict)
    source_uri: Optional[str] = None
    associated_zone_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class CameraUpdateRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    input_type: Optional[str] = None
    perspective: Optional[str] = None
    is_moving_camera: Optional[bool] = None
    layout_id: Optional[str] = None
    calibration_data: Optional[dict[str, Any]] = None
    source_uri: Optional[str] = None
    status: Optional[str] = None
    associated_zone_ids: Optional[list[str]] = None
    config: Optional[dict[str, Any]] = None


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    name: str
    location: str
    input_type: str
    perspective: str = "FIXED_CCTV"
    is_moving_camera: bool = False
    layout_id: Optional[str] = None
    calibration_data: dict[str, Any] = Field(default_factory=dict)
    source_uri: Optional[str] = None
    status: str
    associated_zone_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class CameraCalibrationRequest(BaseModel):
    """Footage-based 4-point homography & physical dimension calibration."""
    perspective: str = "FIXED_CCTV"
    image_points: list[list[float]]
    venue_points: list[list[float]]
    ground_plane_width_meters: Optional[float] = None
    ground_plane_height_meters: Optional[float] = None
    scale_factor_m_per_px: Optional[float] = None
    is_moving_camera: bool = False
    camera_id: Optional[str] = None
    layout_id: Optional[str] = None


class PerspectiveAssessmentRequest(BaseModel):
    video_file_id: str
    frame_index: Optional[int] = None


class PerspectiveAssessmentResponse(BaseModel):
    perspective: str = "FIXED_CCTV"
    recommended_perspective: str = "FIXED_CCTV"
    confidence: float = 0.75
    vanishing_points_found: int = 0
    explanation: str = ""
    reason: Optional[str] = None
    aspect_ratio: Optional[float] = None
    vanishing_point_detected: Optional[bool] = None


class VideoFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    camera_id: Optional[str] = None
    original_filename: str
    stored_path: str
    playback_url: str = ""
    file_size_bytes: int
    duration_seconds: float
    fps: float
    frame_count: int
    width: int
    height: int
    created_at: Optional[datetime] = None


class VideoUploadResponse(BaseModel):
    video_id: str
    job_id: str
    filename: str
    playback_url: str
    duration_seconds: float
    fps: float
    frame_count: int
    width: int
    height: int
    file_size_bytes: int


class ProcessStartRequest(BaseModel):
    sample_fps: Optional[float] = Field(default=0.2)
    camera_id: Optional[str] = None
    layout_id: Optional[str] = None
    camera_perspective: Optional[str] = None
    perspective: Optional[str] = None


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    video_file_id: str
    camera_id: Optional[str] = None
    layout_id: Optional[str] = None
    camera_perspective: str = "FIXED_CCTV"
    status: str
    detector_backend: str
    sample_fps: float
    frames_processed: int
    total_sampled_frames: int
    progress_pct: float
    processing_fps: float
    avg_inference_ms: float
    max_people_detected: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CrowdMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    job_id: Optional[str] = None
    zone_id: str
    zone_name: str
    video_timestamp_sec: float
    people_count: int
    occupancy_ratio: float
    density_value: float
    density_unit: str
    inflow_rate: float
    outflow_rate: float
    net_flow: float
    avg_speed: float
    movement_direction: str
    crowd_increase_pct: float = 0.0
    capacity_utilization_pct: float = 0.0
    is_bottleneck: bool
    is_counterflow: bool
    recorded_at: Optional[datetime] = None


class DetectionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    event_id: str
    frame_index: int
    video_timestamp_sec: float
    total_people: int
    inference_ms: float
    detections: list[dict[str, Any]]
    heatmap_grid: list[list[float]]


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    job_id: Optional[str] = None
    zone_id: str
    zone_name: str
    video_timestamp_sec: float
    horizon_seconds: int
    current_occupancy: float
    current_density: float
    predicted_occupancy: float
    predicted_density: float
    predicted_change_pct: float = 0.0
    estimated_trend: str
    risk_category: str
    confidence: float
    is_experimental: bool
    model_name: str
    created_at: Optional[datetime] = None


class RiskAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    job_id: Optional[str] = None
    zone_id: str
    zone_name: str
    video_timestamp_sec: float
    risk_level: str
    reason: str
    supporting_measurements: dict[str, Any]
    monitoring_priority: str
    requires_human_review: bool
    created_at: Optional[datetime] = None


class HeatmapResponse(BaseModel):
    job_id: str
    video_timestamp_sec: float
    current: list[list[float]]
    predicted: dict[str, list[list[float]]] = Field(default_factory=dict)


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    category: str
    severity: str
    title: str
    description: str
    supporting_measurements: dict[str, Any] = Field(default_factory=dict)
    status: str
    video_timestamp_sec: Optional[float] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    source: str
    created_at: Optional[datetime] = None


class AlertAcknowledgeRequest(BaseModel):
    note: Optional[str] = None


class AlertResolveRequest(BaseModel):
    resolution_note: Optional[str] = None


class AlertCreateRequest(BaseModel):
    event_id: str
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    category: str = "occupancy_warning"
    severity: str = "MEDIUM"
    title: str
    description: str
    supporting_measurements: dict[str, Any] = Field(default_factory=dict)
    source: str = "MANUAL"


class AlertStatsResponse(BaseModel):
    total: int
    active: int
    acknowledged: int
    resolved: int
    by_severity: dict[str, int]
    by_category: dict[str, int]


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    action: str
    reason: str
    priority: str
    suggested_team: str
    supporting_data: list[str] = Field(default_factory=list)
    review_status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    source: str
    created_at: Optional[datetime] = None


class RecommendationReviewRequest(BaseModel):
    review_status: str
    review_note: Optional[str] = None


class ReportGenerateRequest(BaseModel):
    event_id: str
    title: Optional[str] = None
    job_id: Optional[str] = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    title: str
    generated_by: Optional[str] = None
    summary_data: dict[str, Any]
    created_at: Optional[datetime] = None


class ChatProxyRequest(BaseModel):
    event_id: str
    message: str
    session_id: Optional[str] = None


class ChatProxyResponse(BaseModel):
    session_id: str
    response: str
    source: str = "ai_agent"
    data_sources: list[str] = Field(default_factory=list)
    is_data_stale: bool = False
    stale_warning: Optional[str] = None
    timestamp: datetime


class HealthResponse(BaseModel):
    status: str
    database: str
    ai_agent: str
    detector_backend: str
    active_ws_connections: int
    timestamp: datetime
    copilot_provider: Optional[str] = "deterministic_grounded_engine"
    copilot_llm_configured: Optional[bool] = False
    copilot_tools_count: Optional[int] = 18
    active_processing_jobs: Optional[int] = 0


class SingleImageAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: Optional[str] = None
    venue_id: Optional[str] = None
    layout_id: Optional[str] = None
    original_filename: str
    image_url: str
    width: int
    height: int
    total_people: int
    inference_ms: float
    detector_backend: str
    camera_perspective: str
    detections: list[dict[str, Any]]
    heatmap_grid: list[list[float]]
    zone_occupancies: list[dict[str, Any]]
    analysis_note: str
    disclaimer: str
    created_at: Optional[datetime] = None


class GeometryValidationRequest(BaseModel):
    polygon_points: list[list[float]]


class GeometryValidationResponse(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    vertex_count: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


# --- Phase 1 Task Schemas ---

class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    state: str = "DRAFT"
    layout_id: Optional[str] = None
    layout_snapshot: Optional[dict[str, Any]] = None
    video_config: Optional[dict[str, Any]] = None
    analysis_settings: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    state: Optional[str] = None
    layout_id: Optional[str] = None
    layout_snapshot: Optional[dict[str, Any]] = None
    video_config: Optional[dict[str, Any]] = None
    analysis_settings: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class TaskStateUpdateRequest(BaseModel):
    state: str
    reason: Optional[str] = None


class TaskHistoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    state: str
    layout_id: Optional[str] = None
    layout_snapshot: dict[str, Any] = Field(default_factory=dict)
    video_config: dict[str, Any] = Field(default_factory=dict)
    analysis_settings: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    history: Optional[list[TaskHistoryItemResponse]] = None


# --- Phase 1 Copilot Schemas ---

class CopilotQueryRequest(BaseModel):
    task_id: Optional[str] = None
    message: str
    session_id: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class CopilotActionProposal(BaseModel):
    action_type: str
    parameters: dict[str, Any]
    rationale: str
    risk_assessment: str
    requires_approval: bool = True


class CopilotQueryResponse(BaseModel):
    session_id: str
    response: str
    source: str
    data_sources: list[str] = Field(default_factory=list)
    action_proposal: Optional[CopilotActionProposal] = None
    timestamp: datetime


class CopilotActionValidateRequest(BaseModel):
    action_type: str
    parameters: dict[str, Any]
    task_id: Optional[str] = None


class CopilotActionValidateResponse(BaseModel):
    is_valid: bool
    validation_errors: list[str] = Field(default_factory=list)
    simulated_impact: Optional[str] = None
    can_execute: bool = False


class CopilotActionExecuteRequest(BaseModel):
    action_type: str
    parameters: dict[str, Any]
    task_id: Optional[str] = None
    confirmed_by: Optional[str] = "operator"


class CopilotActionExecuteResponse(BaseModel):
    success: bool
    action_type: str
    result: dict[str, Any] = Field(default_factory=dict)
    message: str
    task_id: Optional[str] = None
    timestamp: datetime


class CopilotToolDefinition(BaseModel):
    name: str
    description: str
    category: str  # "read_only" | "action"
    requires_confirmation: bool
    parameters: dict[str, Any]

