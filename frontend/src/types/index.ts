export type RiskLevel = 'NORMAL' | 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type PerspectiveType = 'drone_top_down' | 'elevated_cctv' | 'ground_level' | 'standard';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'ADMIN' | 'OPERATOR' | 'VIEWER';
  is_active: boolean;
}

export interface ZoneCapacity {
  id: string;
  zone_id: string;
  max_capacity: number;
  area_sqm: number;
  normal_threshold: number;
  low_threshold: number;
  moderate_threshold: number;
  high_threshold: number;
  critical_threshold: number;
}

export interface Zone {
  id: string;
  venue_id: string;
  name: string;
  zone_type: string;
  capacity?: ZoneCapacity;
}

export interface Venue {
  id: string;
  name: string;
  venue_type: string;
  total_capacity?: number;
  zones?: Zone[];
}

export interface EventItem {
  id: string;
  name: string;
  event_type: string;
  status: 'ACTIVE' | 'SCHEDULED' | 'COMPLETED' | 'PAUSED';
  venue_id?: string;
  expected_attendance?: number;
  created_at: string;
}

export interface PolygonPoint {
  x: number;
  y: number;
}

export interface LayoutZoneData {
  id: string;
  name: string;
  zone_id?: string;
  zone_name?: string;
  zone_type: string;
  polygon_points: PolygonPoint[];
  capacity: number;
  max_capacity?: number;
  area_sqm?: number;
  color?: string;
}

export interface VenueLayout {
  id: string;
  venue_id?: string;
  name: string;
  description?: string;
  version?: number;
  canvas_width?: number;
  canvas_height?: number;
  scale_pixels_per_meter?: number;
  reference_image_path?: string;
  background_image_url?: string | null;
  zones_data: LayoutZoneData[];
  calibration_homography?: number[][];
  camera_perspective?: PerspectiveType;
  created_at: string;
  updated_at?: string;
}

export interface ProcessingJob {
  id: string;
  event_id?: string;
  video_file_id: string;
  status: 'PENDING' | 'QUEUED' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'STOPPED';
  sample_fps: number;
  frames_processed: number;
  total_sampled_frames: number;
  progress_pct: number;
  processing_fps?: number;
  avg_inference_ms?: number;
  max_people_detected: number;
  camera_perspective: PerspectiveType;
  detector_backend?: string;
  error_message?: string;
  created_at: string;
}

export interface VideoFile {
  id: string;
  event_id: string;
  filename: string;
  original_filename: string;
  file_size_bytes: number;
  duration_seconds: number;
  fps: number;
  width: number;
  height: number;
  created_at: string;
}

export interface DetectionBox {
  track_id: number;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2]
  confidence: number;
  ground_contact: [number, number]; // [x, y]
  velocity?: [number, number]; // [vx, vy]
  zone_id?: string;
}

export interface DetectionSummary {
  id: string;
  job_id: string;
  frame_index: number;
  video_timestamp_sec: number;
  total_people: number;
  inference_ms: number;
  detections: DetectionBox[];
  heatmap_grid?: number[][];
}

export interface HeatmapData {
  job_id: string;
  video_timestamp_sec: number;
  current?: number[][];
  predicted?: {
    '30'?: number[][];
    '60'?: number[][];
    '180'?: number[][];
    '300'?: number[][];
    '30s'?: number[][];
    '60s'?: number[][];
    '180s'?: number[][];
    '300s'?: number[][];
    [key: string]: number[][] | undefined;
  };
}

export interface PredictionItem {
  id: string;
  job_id: string;
  zone_id: string;
  zone_name: string;
  video_timestamp_sec: number;
  horizon_seconds: number;
  current_occupancy: number;
  predicted_occupancy: number;
  predicted_change_pct: number;
  estimated_trend: 'rapidly_increasing' | 'increasing' | 'stable' | 'decreasing' | 'rapidly_decreasing';
  risk_category: RiskLevel;
  confidence: number;
  is_experimental: boolean;
}

export interface RiskItem {
  id: string;
  job_id: string;
  zone_id: string;
  zone_name: string;
  video_timestamp_sec: number;
  risk_level: RiskLevel;
  reason: string;
  monitoring_priority: number;
  requires_human_review: boolean;
  supporting_measurements?: Record<string, any>;
}

export interface AlertItem {
  id: string;
  event_id: string;
  zone_id?: string;
  zone_name?: string;
  category: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
  video_timestamp_sec?: number;
  created_at: string;
  supporting_measurements?: Record<string, any>;
}

export interface ZoneTelemetry {
  zone_id: string;
  zone_name: string;
  people_count: number;
  occupancy_ratio: number;
  capacity_utilization_pct: number;
  density_value: number;
  inflow_rate: number;
  outflow_rate: number;
  net_flow: number;
  avg_speed?: number;
  movement_direction?: string;
  risk_level: RiskLevel;
  is_bottleneck: boolean;
  is_counterflow: boolean;
  video_timestamp_sec: number;
}

export interface EventZoneSummary {
  event_id: string;
  video_timestamp_sec: number;
  total_people: number;
  zones: ZoneTelemetry[];
  trend_series: {
    timestamp: number;
    total_people: number;
  }[];
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
  reasoning?: string[];
  recommendations?: string[];
  risk_evaluations?: Record<string, any>;
}

export interface ReportItem {
  id: string;
  event_id: string;
  title: string;
  report_type: string;
  executive_summary?: string;
  summary_data: {
    event_name?: string;
    venue_name?: string;
    max_concurrent_crowd?: number;
    frames_analyzed?: number;
    alert_metrics?: {
      total_alerts: number;
      critical: number;
      high: number;
      medium: number;
      low: number;
    };
    zone_breakdown?: Record<string, {
      zone_name: string;
      peak_people: number;
      avg_people: number;
      peak_capacity_utilization_pct: number;
      max_inflow: number;
      max_outflow: number;
      bottleneck_count: number;
      counterflow_count: number;
    }>;
  };
  created_at: string;
}

// --- Phase 1: Task Management, Spatial Layout, and Copilot Types ---

export type TaskLifecycleState =
  | 'DRAFT'
  | 'CONFIGURING'
  | 'READY'
  | 'PROCESSING'
  | 'LIVE'
  | 'PAUSED'
  | 'COMPLETED'
  | 'FAILED';

export type VideoSourceType = 'FILE' | 'CCTV_STREAM' | 'DRONE_RECORDING';

export interface TaskVideoConfig {
  source_type: VideoSourceType;
  file_id?: string;
  video_id?: string;
  filename?: string;
  source_uri?: string;
  stored_path?: string;
  stream_url?: string;
  playback_url?: string;
  duration_seconds?: number;
  fps?: number;
  camera_perspective?: string;
  sample_fps?: number;
  auto_process?: boolean;
  resolution?: string;
}

export interface TaskAnalysisSettings {
  detector?: string;
  confidence_threshold?: number;
  density_method?: string;
  risk_hysteresis?: boolean;
}

export interface LayoutSnapshot {
  layout_id?: string;
  name: string;
  description?: string;
  version?: number;
  canvas_width?: number;
  canvas_height?: number;
  scale_pixels_per_meter?: number;
  background_image_url?: string | null;
  zones_count?: number;
  zones_data: LayoutZoneData[];
  snapshot_created_at?: string;
}

export interface TaskHistoryItem {
  id: string;
  task_id: string;
  event_type: string;
  details: Record<string, any>;
  timestamp: string;
}

export interface TaskItem {
  id: string;
  name: string;
  description?: string;
  location?: string;
  state: TaskLifecycleState;
  layout_id?: string;
  layout_snapshot: LayoutSnapshot;
  video_config: TaskVideoConfig;
  analysis_settings: TaskAnalysisSettings;
  notes?: string;
  created_at: string;
  updated_at: string;
  history?: TaskHistoryItem[];
}

export interface CopilotActionProposal {
  action_type: string;
  parameters: Record<string, any>;
  rationale: string;
  risk_assessment: string;
  requires_approval: boolean;
}

export interface CopilotQueryResponse {
  session_id: string;
  response: string;
  source: string;
  data_sources: string[];
  action_proposal?: CopilotActionProposal;
  timestamp: string;
}

export interface CopilotActionExecuteResponse {
  success: boolean;
  action_type: string;
  result: Record<string, any>;
  message: string;
  task_id?: string;
  timestamp: string;
}

export interface CopilotToolDefinition {
  name: string;
  description: string;
  category: 'read_only' | 'action';
  requires_confirmation: boolean;
  parameters: Record<string, any>;
}

export interface AlertStats {
  total: number;
  active: number;
  acknowledged: number;
  resolved: number;
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
}

export interface HistoricalAnalytics {
  task_id?: string;
  data_points: number;
  peak_people: number;
  timeline: {
    timestamp_sec: number;
    total_people: number;
    zone_counts: Record<string, number>;
    avg_speed?: number;
  }[];
}

