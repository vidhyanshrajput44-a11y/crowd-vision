import {
  EventItem,
  Venue,
  VenueLayout,
  VideoFile,
  ProcessingJob,
  DetectionSummary,
  HeatmapData,
  PredictionItem,
  RiskItem,
  AlertItem,
  EventZoneSummary,
  ReportItem,
  User,
  TaskItem,
  TaskHistoryItem,
  CopilotQueryResponse,
} from '../types';

const RAW_API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || '';
const API_BASE = (RAW_API_BASE ? String(RAW_API_BASE).replace(/\/$/, '') : '') + '/api';

class ApiService {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('crowdvision_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('crowdvision_token', token);
    } else {
      localStorage.removeItem('crowdvision_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      // Auto-relogin or clear token
      this.setToken(null);
    }

    if (!res.ok) {
      let errDetail = 'Request failed';
      try {
        const data = await res.json();
        if (typeof data.detail === 'string') {
          errDetail = data.detail;
        } else if (Array.isArray(data.detail)) {
          errDetail = data.detail
            .map((item: any) => {
              const field = item.loc ? item.loc[item.loc.length - 1] : '';
              return `${field ? field + ': ' : ''}${item.msg || JSON.stringify(item)}`;
            })
            .join(', ');
        } else if (data.detail && typeof data.detail === 'object') {
          errDetail = JSON.stringify(data.detail);
        } else {
          errDetail = JSON.stringify(data);
        }
      } catch {
        errDetail = res.statusText;
      }
      throw new Error(`[${res.status}] ${errDetail}`);
    }

    // For file downloads
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('text/csv')) {
      return (await res.text()) as unknown as T;
    }

    return res.json();
  }

  // --- Auth ---
  async login(email = 'admin@crowdvision.io', password = 'admin123'): Promise<{ access_token: string }> {
    const res = await this.request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(res.access_token);
    return res;
  }

  async getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  // --- Health ---
  async getHealth(): Promise<{ status: string; database: string; ai_agent_service: string }> {
    return this.request('/health/');
  }

  // --- Events / Tasks ---
  async getEvents(): Promise<EventItem[]> {
    return this.request<EventItem[]>('/events/');
  }

  async getEvent(id: string): Promise<EventItem> {
    return this.request<EventItem>(`/events/${id}`);
  }

  async createEvent(data: { name: string; event_type: string; venue_id?: string; expected_attendance?: number }): Promise<EventItem> {
    return this.request<EventItem>('/events/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // --- Venues & Layouts ---
  async getVenues(): Promise<Venue[]> {
    return this.request<Venue[]>('/venues/');
  }

  async getVenue(id: string): Promise<Venue> {
    return this.request<Venue>(`/venues/${id}`);
  }

  async createVenue(data: { name: string; venue_type?: string; total_capacity?: number }): Promise<Venue> {
    return this.request<Venue>('/venues/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getLayouts(venueId?: string): Promise<VenueLayout[]> {
    const query = venueId ? `?venue_id=${venueId}` : '';
    return this.request<VenueLayout[]>(`/layouts/${query}`);
  }

  async getLayout(layoutId: string): Promise<VenueLayout> {
    return this.request<VenueLayout>(`/layouts/${layoutId}`);
  }

  async createLayout(data: {
    venue_id?: string;
    name: string;
    description?: string;
    canvas_width?: number;
    canvas_height?: number;
    background_image_url?: string | null;
    zones_data: any[];
    calibration_homography?: number[][];
    camera_perspective?: string;
  }): Promise<VenueLayout> {
    return this.request<VenueLayout>('/layouts/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async uploadLayoutBackground(
    file: File
  ): Promise<{ image_url: string; width: number; height: number; filename: string }> {
    const formData = new FormData();
    formData.append('file', file);
    return this.request('/layouts/upload-background', {
      method: 'POST',
      body: formData,
    });
  }

  // --- Videos & Jobs ---
  async uploadVideo(
    eventId: string,
    file: File,
    sampleFps = 2.0,
    cameraPerspective = 'drone_top_down',
    autoProcess = false
  ): Promise<{ video_id: string; duration_seconds: number; fps: number; width: number; height: number }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('event_id', eventId);
    formData.append('sample_fps', sampleFps.toString());
    formData.append('camera_perspective', cameraPerspective);
    formData.append('auto_process', autoProcess.toString());

    return this.request('/videos/upload', {
      method: 'POST',
      body: formData,
    });
  }

  async startProcessing(
    videoId: string,
    sampleFps = 2.0,
    layoutId?: string,
    perspective = 'drone_top_down'
  ): Promise<ProcessingJob> {
    return this.request<ProcessingJob>(`/videos/${videoId}/process`, {
      method: 'POST',
      body: JSON.stringify({
        sample_fps: sampleFps,
        layout_id: layoutId,
        camera_perspective: perspective,
      }),
    });
  }

  async getJobStatus(jobOrVideoId: string): Promise<ProcessingJob> {
    return this.request<ProcessingJob>(`/videos/jobs/${jobOrVideoId}`);
  }

  async stopProcessing(jobId: string): Promise<ProcessingJob> {
    return this.request<ProcessingJob>(`/videos/jobs/${jobId}/stop`, {
      method: 'POST',
    });
  }

  // --- Analytics & Predictions ---
  async getDetections(jobOrVideoId: string, ts?: number): Promise<DetectionSummary> {
    const query = ts !== undefined ? `?ts=${ts}` : '';
    return this.request<DetectionSummary>(`/analytics/detections/${jobOrVideoId}${query}`);
  }

  async getHeatmap(jobOrVideoId: string, ts?: number): Promise<HeatmapData> {
    const query = ts !== undefined ? `?ts=${ts}` : '';
    return this.request<HeatmapData>(`/analytics/heatmap/${jobOrVideoId}${query}`);
  }

  async getPredictions(jobOrVideoId: string, horizonSeconds?: number): Promise<PredictionItem[]> {
    const query = horizonSeconds !== undefined ? `?horizon_seconds=${horizonSeconds}` : '';
    return this.request<PredictionItem[]>(`/analytics/predictions/${jobOrVideoId}${query}`);
  }

  async getRisks(jobOrVideoId: string, ts?: number): Promise<RiskItem[]> {
    const query = ts !== undefined ? `?ts=${ts}` : '';
    return this.request<RiskItem[]>(`/analytics/risks?job_id=${jobOrVideoId}${query ? '&' + query.slice(1) : ''}`);
  }

  async getZoneSummary(eventId: string): Promise<EventZoneSummary> {
    return this.request<EventZoneSummary>(`/analytics/zones/${eventId}/summary`);
  }

  // --- Alerts ---
  async getAlerts(eventId?: string, status?: string): Promise<AlertItem[]> {
    const params = new URLSearchParams();
    if (eventId) params.append('event_id', eventId);
    if (status) params.append('status', status);
    return this.request<AlertItem[]>(`/alerts/?${params.toString()}`);
  }

  async updateAlertStatus(alertId: string, status: 'ACKNOWLEDGED' | 'RESOLVED'): Promise<AlertItem> {
    return this.request<AlertItem>(`/alerts/${alertId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  }

  // --- AI Chat ---
  async sendChatMessage(eventId: string, message: string): Promise<{
    event_id: string;
    response: string;
    timestamp: string;
    reasoning_steps?: string[];
    risk_evaluations?: Record<string, any>;
    recommendations?: string[];
  }> {
    return this.request('/chat/', {
      method: 'POST',
      body: JSON.stringify({ event_id: eventId, message }),
    });
  }

  // --- Layout Management Extensions ---
  async updateLayout(layoutId: string, data: any): Promise<VenueLayout> {
    return this.request<VenueLayout>(`/layouts/${layoutId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async duplicateLayout(layoutId: string): Promise<VenueLayout> {
    return this.request<VenueLayout>(`/layouts/${layoutId}/duplicate`, {
      method: 'POST',
    });
  }

  async deleteLayout(layoutId: string): Promise<void> {
    return this.request<void>(`/layouts/${layoutId}`, {
      method: 'DELETE',
    });
  }

  async validateGeometry(points: [number, number][]): Promise<{
    is_valid: boolean;
    errors: string[];
    vertex_count: number;
    warnings: string[];
  }> {
    return this.request('/validate-geometry', {
      method: 'POST',
      body: JSON.stringify({ polygon_points: points }),
    });
  }

  // --- Phase 1: Tasks System ---
  async getTasks(params?: { state?: string; search?: string }): Promise<TaskItem[]> {
    const searchParams = new URLSearchParams();
    if (params?.state && params.state !== 'ALL') searchParams.append('state', params.state);
    if (params?.search) searchParams.append('search', params.search);
    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return this.request<TaskItem[]>(`/tasks${query}`);
  }

  async getTask(id: string): Promise<TaskItem> {
    return this.request<TaskItem>(`/tasks/${id}`);
  }

  async createTask(data: {
    name: string;
    description?: string;
    location?: string;
    state?: string;
    layout_id?: string;
    layout_snapshot?: any;
    video_config?: any;
    analysis_settings?: any;
    notes?: string;
  }): Promise<TaskItem> {
    return this.request<TaskItem>('/tasks/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateTask(id: string, data: Partial<TaskItem>): Promise<TaskItem> {
    return this.request<TaskItem>(`/tasks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async duplicateTask(id: string): Promise<TaskItem> {
    return this.request<TaskItem>(`/tasks/${id}/duplicate`, {
      method: 'POST',
    });
  }

  async deleteTask(id: string): Promise<void> {
    return this.request<void>(`/tasks/${id}`, {
      method: 'DELETE',
    });
  }

  async changeTaskState(id: string, state: string, reason?: string): Promise<TaskItem> {
    return this.request<TaskItem>(`/tasks/${id}/state`, {
      method: 'POST',
      body: JSON.stringify({ state, reason }),
    });
  }

  async getTaskHistory(id: string): Promise<TaskHistoryItem[]> {
    return this.request<TaskHistoryItem[]>(`/tasks/${id}/history`);
  }

  async startTaskProcessing(taskId: string, payload?: {
    sample_fps?: number;
    camera_perspective?: string;
    video_id?: string;
    layout_id?: string;
  }): Promise<ProcessingJob> {
    return this.request<ProcessingJob>(`/tasks/${taskId}/process`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  }

  async pauseTaskProcessing(taskId: string): Promise<{ task_id: string; job_id?: string; status: string }> {
    return this.request(`/tasks/${taskId}/pause`, {
      method: 'POST',
    });
  }

  async resumeTaskProcessing(taskId: string): Promise<{ task_id: string; job_id?: string; status: string }> {
    return this.request(`/tasks/${taskId}/resume`, {
      method: 'POST',
    });
  }

  async stopTaskProcessing(taskId: string): Promise<{ task_id: string; job_id?: string; status: string }> {
    return this.request(`/tasks/${taskId}/stop`, {
      method: 'POST',
    });
  }

  async getTaskJob(taskId: string): Promise<ProcessingJob | null> {
    try {
      return await this.request<ProcessingJob>(`/tasks/${taskId}/job`);
    } catch {
      return null;
    }
  }

  async getTaskTelemetry(taskId: string, ts?: number): Promise<any> {
    const url = ts !== undefined
      ? `/tasks/${taskId}/telemetry?ts=${ts.toFixed(2)}`
      : `/tasks/${taskId}/telemetry`;
    return this.request(url);
  }

  // --- Phase 1: AI Copilot ---
  async getCopilotStatus(): Promise<{
    status: string;
    active_provider: string;
    is_llm_configured: boolean;
    fallback_mode: string;
    available_tools: any[];
    agent_service_connected: boolean;
  }> {
    return this.request('/copilot/status');
  }

  async queryCopilot(data: {
    task_id?: string;
    message: string;
    session_id?: string;
  }): Promise<CopilotQueryResponse> {
    return this.request<CopilotQueryResponse>('/copilot/query', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async validateCopilotAction(data: {
    action_type: string;
    parameters: any;
    task_id?: string;
  }): Promise<{
    is_valid: boolean;
    validation_errors: string[];
    simulated_impact?: string;
    can_execute: boolean;
  }> {
    return this.request('/copilot/validate-action', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async executeCopilotAction(data: {
    action_type: string;
    parameters: any;
    task_id?: string;
    confirmed_by?: string;
  }): Promise<{
    success: boolean;
    action_type: string;
    result: any;
    message: string;
    task_id?: string;
    timestamp: string;
  }> {
    return this.request('/copilot/execute-action', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getCopilotTools(): Promise<any[]> {
    return this.request('/copilot/tools');
  }

  async getAlertStats(eventId?: string): Promise<any> {
    const query = eventId ? `?event_id=${eventId}` : '';
    return this.request(`/alerts/stats${query}`);
  }

  async createAlert(data: {
    event_id: string;
    zone_id?: string;
    zone_name?: string;
    category?: string;
    severity?: string;
    title: string;
    description: string;
    supporting_measurements?: any;
    source?: string;
  }): Promise<AlertItem> {
    return this.request<AlertItem>('/alerts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getHistoricalAnalytics(params?: {
    task_id?: string;
    start_ts?: number;
    end_ts?: number;
  }): Promise<any> {
    const searchParams = new URLSearchParams();
    if (params?.task_id) searchParams.append('task_id', params.task_id);
    if (params?.start_ts !== undefined) searchParams.append('start_ts', params.start_ts.toString());
    if (params?.end_ts !== undefined) searchParams.append('end_ts', params.end_ts.toString());
    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return this.request(`/analytics/history${query}`);
  }

  // --- Reports ---
  async getReports(eventId?: string): Promise<ReportItem[]> {
    const query = eventId ? `?event_id=${eventId}` : '';
    return this.request<ReportItem[]>(`/reports/${query}`);
  }

  async generateReport(eventId: string, jobId?: string): Promise<ReportItem> {
    return this.request<ReportItem>('/reports/generate', {
      method: 'POST',
      body: JSON.stringify({ event_id: eventId, job_id: jobId }),
    });
  }

  async exportReportCsv(reportId: string): Promise<string> {
    return this.request<string>(`/reports/${reportId}/export.csv`);
  }
}

export const api = new ApiService();
