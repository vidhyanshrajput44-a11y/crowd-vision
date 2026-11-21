import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Video,
  Flame,
  ShieldAlert,
  Play,
  Pause,
  Square,
  Layers,
  MapPin,
  Calendar,
  Activity,
  AlertTriangle,
  RefreshCw,
  Cpu,
  Sliders,
  CheckCircle2,
  Clock,
  Compass,
  TrendingUp,
  TrendingDown,
  Gauge,
  Maximize2,
  Volume2,
  VolumeX,
  Eye,
  EyeOff,
  Crosshair,
  Zap,
  Info,
} from 'lucide-react';
import { useTaskContext } from '../context/TaskContext';
import { LayoutZoneData, ProcessingJob, DetectionBox, RiskLevel } from '../types';
import { api } from '../services/api';

type WorkspaceViewMode = 'TRI_VIEW' | 'VIDEO' | 'HEATMAP' | 'ZONES';
type HeatmapHorizon = 'live' | 'accumulated' | '30s' | '60s' | '180s' | '300s';

interface TelemetryDetection {
  track_id: number;
  bbox: [number, number, number, number];
  norm_bbox?: [number, number, number, number];
  confidence: number;
  foot_point: [number, number];
  norm_point?: [number, number];
  zone_id?: string | null;
  zone_name?: string;
  vx: number;
  vy: number;
  speed?: number;
  trajectory?: [number, number][];
}

interface TelemetrySnapshot {
  zone_id: string;
  zone_name: string;
  people_count: number;
  capacity: number;
  occupancy_ratio: number;
  density_value: number;
  density_unit: string;
  inflow_rate: number;
  outflow_rate: number;
  net_flow: number;
  avg_speed: number;
  movement_direction: string;
  is_bottleneck: boolean;
  is_counterflow: boolean;
  crowd_increase_pct: number;
  capacity_utilization_pct: number;
}

interface TelemetryRisk {
  zone_id: string;
  risk_level: string;
  reason: string;
  monitoring_priority: string;
}

interface TelemetryPrediction {
  zone_id: string;
  horizon_seconds: number;
  predicted_occupancy: number;
  predicted_change_pct: number;
  estimated_trend: string;
  risk_category: string;
  confidence: number;
}

interface TelemetryData {
  frame_index: number;
  video_timestamp_sec: number;
  progress_pct: number;
  total_people: number;
  frame_w?: number;
  frame_h?: number;
  perspective?: string;
  detections: TelemetryDetection[];
  snapshots: TelemetrySnapshot[];
  heatmap_grid: number[][];
  accumulated_heatmap_grid?: number[][];
  predicted_heatmaps?: Record<string, number[][]>;
  risks: TelemetryRisk[];
  predictions: TelemetryPrediction[];
  alerts?: any[];
}

interface MonitoringWorkspaceProps {
  onOpenLayoutBuilder: () => void;
  onOpenCreateTask: () => void;
}

export const MonitoringWorkspace: React.FC<MonitoringWorkspaceProps> = ({
  onOpenLayoutBuilder,
  onOpenCreateTask,
}) => {
  const { activeTask, activeZones, changeTaskState } = useTaskContext();

  const [viewMode, setViewMode] = useState<WorkspaceViewMode>('TRI_VIEW');
  const [activeJob, setActiveJob] = useState<ProcessingJob | null>(null);
  const [isActionPending, setIsActionPending] = useState(false);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [sampleFps, setSampleFps] = useState<number>(2.0);

  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [selectedHorizon, setSelectedHorizon] = useState<HeatmapHorizon>('live');

  // Overlay display toggles
  const [showBoxes, setShowBoxes] = useState(true);
  const [showTracks, setShowTracks] = useState(true);
  const [showVectors, setShowVectors] = useState(true);
  const [showFootPoints, setShowFootPoints] = useState(true);
  const [showTrails, setShowTrails] = useState(true);
  const [showHud, setShowHud] = useState(false);

  // Video player controls
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoContainerRef = useRef<HTMLDivElement | null>(null);
  const videoOverlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const heatmapCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [videoDimensions, setVideoDimensions] = useState({ width: 640, height: 360 });
  const [isPlaying, setIsPlaying] = useState(true);
  const [isMuted, setIsMuted] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [isLooping, setIsLooping] = useState(true);
  const [videoError, setVideoError] = useState(false);
  const [videoLoading, setVideoLoading] = useState(true);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const lastFetchedTsRef = useRef<number>(-1);
  const isFetchingRef = useRef<boolean>(false);

  // ResizeObserver for exact video overlay sizing
  useEffect(() => {
    const container = videoContainerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {
          setVideoDimensions({
            width: Math.floor(entry.contentRect.width),
            height: Math.floor(entry.contentRect.height),
          });
        }
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [viewMode]);

  // WebSocket real-time subscription
  useEffect(() => {
    if (!activeTask) return;

    const defaultWsHost = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
    const rawWs = (import.meta as any).env?.VITE_WS_BASE_URL || defaultWsHost;
    const baseWs = String(rawWs).replace(/\/$/, '');
    const wsUrl = `${baseWs}/ws/${activeTask.id}`;
    let ws: WebSocket | null = null;
    let pingInterval: any = null;
    let isCancelled = false;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (isCancelled) return;
        setWsConnected(true);
        pingInterval = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 15000);
      };

      ws.onmessage = (event) => {
        if (isCancelled) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'FRAME_UPDATE') {
            setTelemetry({
              frame_index: data.frame_index || 0,
              video_timestamp_sec: data.video_timestamp_sec || 0,
              progress_pct: data.progress_pct || 0,
              total_people: data.total_people || 0,
              detections: data.detections || [],
              snapshots: data.snapshots || [],
              heatmap_grid: data.heatmap_grid || [],
              predicted_heatmaps: data.predicted_heatmaps || {},
              risks: data.risks || [],
              predictions: data.predictions || [],
              alerts: data.alerts || [],
            });
          } else if (data.type === 'JOB_COMPLETED') {
            setActiveJob((prev) => (prev ? { ...prev, status: 'COMPLETED', progress_pct: 100 } : null));
          } else if (data.type === 'JOB_FAILED') {
            setEngineError(data.error || 'Video analysis pipeline encountered an error');
          }
        } catch {
          // ignore non-json messages
        }
      };

      ws.onclose = () => {
        if (!isCancelled) setWsConnected(false);
        clearInterval(pingInterval);
      };

      ws.onerror = () => {
        if (!isCancelled) setWsConnected(false);
      };
    } catch {
      setWsConnected(false);
    }

    return () => {
      isCancelled = true;
      clearInterval(pingInterval);
      if (ws) ws.close();
    };
  }, [activeTask?.id]);

  // Immediate & Synchronized Telemetry Loading
  useEffect(() => {
    if (!activeTask) return;

    let isMounted = true;
    lastFetchedTsRef.current = -1;

    const loadTaskTelemetry = async (targetTs?: number) => {
      try {
        const [j, t] = await Promise.allSettled([
          api.getTaskJob(activeTask.id),
          api.getTaskTelemetry(activeTask.id, targetTs),
        ]);

        if (!isMounted) return;

        if (j.status === 'fulfilled' && j.value) {
          setActiveJob(j.value);
        }

        if (t.status === 'fulfilled' && t.value && (t.value.type === 'FRAME_UPDATE' || t.value.total_people !== undefined)) {
          setTelemetry({
            frame_index: t.value.frame_index || 0,
            video_timestamp_sec: t.value.video_timestamp_sec || 0,
            progress_pct: t.value.progress_pct || 0,
            total_people: t.value.total_people || 0,
            frame_w: t.value.frame_w || 1280,
            frame_h: t.value.frame_h || 720,
            perspective: t.value.perspective || 'FIXED_CCTV',
            detections: t.value.detections || [],
            snapshots: t.value.snapshots || [],
            heatmap_grid: t.value.heatmap_grid || [],
            accumulated_heatmap_grid: t.value.accumulated_heatmap_grid || t.value.heatmap_grid || [],
            predicted_heatmaps: t.value.predicted_heatmaps || {},
            risks: t.value.risks || [],
            predictions: t.value.predictions || [],
            alerts: t.value.alerts || [],
          });
          setEngineError(null);
        }
      } catch {
        // Standby
      }
    };

    loadTaskTelemetry();
    const interval = setInterval(() => {
      api.getTaskJob(activeTask.id).then((j) => {
        if (isMounted && j) setActiveJob(j);
      }).catch(() => {});
    }, 4000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeTask?.id]);

  // Video Playback Synchronized Frame Scrubbing
  useEffect(() => {
    if (!activeTask) return;
    // When live inference engine is running via active WebSocket stream, WS handles frame pushes
    if (activeJob?.status === 'RUNNING' && wsConnected) return;

    const diff = Math.abs(currentTime - lastFetchedTsRef.current);
    if (diff >= 0.25 && !isFetchingRef.current) {
      lastFetchedTsRef.current = currentTime;
      isFetchingRef.current = true;
      api.getTaskTelemetry(activeTask.id, currentTime)
        .then((t) => {
          if (t && (t.type === 'FRAME_UPDATE' || t.total_people !== undefined)) {
            setTelemetry({
              frame_index: t.frame_index || 0,
              video_timestamp_sec: t.video_timestamp_sec || 0,
              progress_pct: t.progress_pct || 0,
              total_people: t.total_people || 0,
              frame_w: t.frame_w || 1280,
              frame_h: t.frame_h || 720,
              perspective: t.perspective || 'FIXED_CCTV',
              detections: t.detections || [],
              snapshots: t.snapshots || [],
              heatmap_grid: t.heatmap_grid || [],
              accumulated_heatmap_grid: t.accumulated_heatmap_grid || t.heatmap_grid || [],
              predicted_heatmaps: t.predicted_heatmaps || {},
              risks: t.risks || [],
              predictions: t.predictions || [],
              alerts: t.alerts || [],
            });
            setEngineError(null);
          }
        })
        .catch(() => {})
        .finally(() => {
          isFetchingRef.current = false;
        });
    }
  }, [currentTime, activeTask?.id, activeJob?.status, wsConnected]);

  // Video detection overlays drawing
  useEffect(() => {
    const canvas = videoOverlayCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, videoDimensions.width, videoDimensions.height);

    if (!telemetry || !telemetry.detections || telemetry.detections.length === 0) {
      return;
    }

    const frameW = telemetry.frame_w || 640.0;
    const frameH = telemetry.frame_h || 480.0;

    telemetry.detections.forEach((det) => {
      const [bx1, by1, bx2, by2] = det.bbox;
      let x: number, y: number, w: number, h: number;
      if (det.norm_bbox && det.norm_bbox.length === 4) {
        x = det.norm_bbox[0] * videoDimensions.width;
        y = det.norm_bbox[1] * videoDimensions.height;
        w = Math.max(6, (det.norm_bbox[2] - det.norm_bbox[0]) * videoDimensions.width);
        h = Math.max(10, (det.norm_bbox[3] - det.norm_bbox[1]) * videoDimensions.height);
      } else {
        x = (bx1 / frameW) * videoDimensions.width;
        y = (by1 / frameH) * videoDimensions.height;
        w = Math.max(6, ((bx2 - bx1) / frameW) * videoDimensions.width);
        h = Math.max(10, ((by2 - by1) / frameH) * videoDimensions.height);
      }

      // 1. Draw Motion Trail (Trajectory history)
      if (showTrails && det.trajectory && det.trajectory.length > 1) {
        ctx.beginPath();
        const startPt = det.trajectory[0];
        ctx.moveTo((startPt[0] / frameW) * videoDimensions.width, (startPt[1] / frameH) * videoDimensions.height);
        for (let i = 1; i < det.trajectory.length; i++) {
          const pt = det.trajectory[i];
          ctx.lineTo((pt[0] / frameW) * videoDimensions.width, (pt[1] / frameH) * videoDimensions.height);
        }
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.45)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // 2. Draw Bounding Box
      if (showBoxes) {
        ctx.strokeStyle = '#06b6d4';
        ctx.lineWidth = 1.8;
        ctx.strokeRect(x, y, w, h);

        // Box corner highlights
        const cornerLen = Math.min(6, w * 0.2);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2.5;

        // Top-left
        ctx.beginPath();
        ctx.moveTo(x, y + cornerLen);
        ctx.lineTo(x, y);
        ctx.lineTo(x + cornerLen, y);
        ctx.stroke();

        // Bottom-right
        ctx.beginPath();
        ctx.moveTo(x + w - cornerLen, y + h);
        ctx.lineTo(x + w, y + h);
        ctx.lineTo(x + w, y + h - cornerLen);
        ctx.stroke();
      }

      // 3. Draw Track Label Badge
      if (showTracks) {
        const label = `#${det.track_id} (${Math.round(det.confidence * 100)}%)`;
        ctx.font = 'bold 9px monospace';
        const textWidth = ctx.measureText(label).width;

        ctx.fillStyle = 'rgba(11, 17, 32, 0.85)';
        ctx.fillRect(x, Math.max(0, y - 14), textWidth + 8, 13);
        ctx.strokeStyle = '#06b6d4';
        ctx.lineWidth = 0.8;
        ctx.strokeRect(x, Math.max(0, y - 14), textWidth + 8, 13);

        ctx.fillStyle = '#38bdf8';
        ctx.fillText(label, x + 4, Math.max(10, y - 4));
      }

      // 4. Draw Foot Ground-Contact Point
      let fx: number, fy: number;
      if (det.norm_point && det.norm_point.length === 2) {
        fx = det.norm_point[0] * videoDimensions.width;
        fy = det.norm_point[1] * videoDimensions.height;
      } else if (det.foot_point && det.foot_point.length === 2) {
        fx = (det.foot_point[0] / frameW) * videoDimensions.width;
        fy = (det.foot_point[1] / frameH) * videoDimensions.height;
      } else {
        fx = x + w * 0.5;
        fy = y + h;
      }

      if (showFootPoints) {
        // Glowing halo
        ctx.beginPath();
        ctx.arc(fx, fy, 4.5, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(20, 184, 166, 0.3)';
        ctx.fill();

        // Solid center point
        ctx.beginPath();
        ctx.arc(fx, fy, 2.5, 0, 2 * Math.PI);
        ctx.fillStyle = '#14b8a6';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // 5. Draw Velocity Vector
      if (showVectors && (Math.abs(det.vx) > 0.3 || Math.abs(det.vy) > 0.3)) {
        const arrowScale = 2.0;
        const targetX = fx + det.vx * arrowScale;
        const targetY = fy + det.vy * arrowScale;

        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(targetX, targetY);
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 1.8;
        ctx.stroke();

        // Arrow head
        const angle = Math.atan2(det.vy, det.vx);
        ctx.beginPath();
        ctx.moveTo(targetX, targetY);
        ctx.lineTo(
          targetX - 5 * Math.cos(angle - Math.PI / 6),
          targetY - 5 * Math.sin(angle - Math.PI / 6)
        );
        ctx.lineTo(
          targetX - 5 * Math.cos(angle + Math.PI / 6),
          targetY - 5 * Math.sin(angle + Math.PI / 6)
        );
        ctx.fillStyle = '#f59e0b';
        ctx.fill();
      }
    });
  }, [telemetry, videoDimensions, showBoxes, showTracks, showVectors, showFootPoints, showTrails]);

  // Heatmap rendering
  useEffect(() => {
    const canvas = heatmapCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let gridToRender = telemetry?.heatmap_grid;
    if (selectedHorizon === 'accumulated') {
      gridToRender = telemetry?.accumulated_heatmap_grid || telemetry?.heatmap_grid;
    } else if (selectedHorizon !== 'live' && telemetry?.predicted_heatmaps) {
      gridToRender = telemetry.predicted_heatmaps[selectedHorizon] || telemetry.heatmap_grid;
    }

    if (!gridToRender || gridToRender.length === 0 || !gridToRender[0]) {
      // Draw idle calibration grid
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#050811';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
      ctx.lineWidth = 1;
      const step = 20;
      for (let x = 0; x < canvas.width; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y < canvas.height; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }
      return;
    }

    const rows = gridToRender.length;
    const cols = gridToRender[0].length;

    // Create offscreen image buffer
    const offscreen = document.createElement('canvas');
    offscreen.width = cols;
    offscreen.height = rows;
    const offCtx = offscreen.getContext('2d');
    if (!offCtx) return;

    const imgData = offCtx.createImageData(cols, rows);
    const data = imgData.data;

    let maxVal = 0.001;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (gridToRender[r][c] > maxVal) maxVal = gridToRender[r][c];
      }
    }

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = (r * cols + c) * 4;
        const norm = Math.min(Math.max(gridToRender[r][c] / maxVal, 0), 1);

        if (norm < 0.04) {
          data[idx] = 5;
          data[idx + 1] = 8;
          data[idx + 2] = 17;
          data[idx + 3] = 255;
        } else {
          // Jet/Thermal colormap
          let red = 0, green = 0, blue = 0;
          if (norm < 0.25) {
            const t = norm / 0.25;
            blue = 255;
            green = Math.floor(t * 220);
          } else if (norm < 0.5) {
            const t = (norm - 0.25) / 0.25;
            green = 255;
            blue = Math.floor((1 - t) * 255);
            red = Math.floor(t * 120);
          } else if (norm < 0.75) {
            const t = (norm - 0.5) / 0.25;
            red = Math.floor(120 + t * 135);
            green = 255;
            blue = 0;
          } else {
            const t = (norm - 0.75) / 0.25;
            red = 255;
            green = Math.floor((1 - t) * 210);
            blue = 0;
          }

          data[idx] = red;
          data[idx + 1] = green;
          data[idx + 2] = blue;
          data[idx + 3] = Math.floor(180 + norm * 75);
        }
      }
    }

    offCtx.putImageData(imgData, 0, 0);

    // Smooth upscale to canvas display
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(offscreen, 0, 0, canvas.width, canvas.height);
  }, [telemetry, selectedHorizon]);

  const zonesToDisplay: LayoutZoneData[] = useMemo(() => {
    if (!activeTask) return activeZones || [];
    return activeTask.layout_snapshot?.zones_data?.length
      ? activeTask.layout_snapshot.zones_data
      : activeZones;
  }, [activeTask, activeZones]);

  const totalVenueCapacity = useMemo(() => {
    return zonesToDisplay.reduce((sum, z) => sum + (z.capacity || 0), 0);
  }, [zonesToDisplay]);

  // Compute live zone metrics mapping from telemetry snapshots
  const snapshotsByZoneId = useMemo(() => {
    const map: Record<string, TelemetrySnapshot> = {};
    if (telemetry?.snapshots) {
      telemetry.snapshots.forEach((s) => {
        map[s.zone_id] = s;
      });
    }
    return map;
  }, [telemetry?.snapshots]);

  // Compute zone risks mapping
  const risksByZoneId = useMemo(() => {
    const map: Record<string, TelemetryRisk> = {};
    if (telemetry?.risks) {
      telemetry.risks.forEach((r) => {
        map[r.zone_id] = r;
      });
    }
    return map;
  }, [telemetry?.risks]);

  // Selected zone detailed telemetry
  const selectedSnapshot = selectedZoneId ? snapshotsByZoneId[selectedZoneId] : null;
  const selectedRisk = selectedZoneId ? risksByZoneId[selectedZoneId] : null;
  const selectedZoneData = zonesToDisplay.find((z) => z.id === selectedZoneId);

  // Handlers for task analysis lifecycle controls
  const handleStartAnalysis = async () => {
    if (!activeTask) return;
    try {
      setIsActionPending(true);
      setEngineError(null);
      const job = await api.startTaskProcessing(activeTask.id, {
        sample_fps: sampleFps,
        camera_perspective: activeTask.video_config?.camera_perspective || 'FIXED_CCTV',
      });
      setActiveJob(job);
      changeTaskState(activeTask.id, 'PROCESSING', 'Operator started live computer vision inference');
    } catch (err: any) {
      setEngineError(err.message || 'Failed to start video processing');
    } finally {
      setIsActionPending(false);
    }
  };

  const handlePauseAnalysis = async () => {
    if (!activeTask) return;
    try {
      setIsActionPending(true);
      await api.pauseTaskProcessing(activeTask.id);
      setActiveJob((prev) => (prev ? { ...prev, status: 'PAUSED' } : null));
      changeTaskState(activeTask.id, 'PAUSED', 'Operator paused video processing');
    } catch (err: any) {
      setEngineError(err.message || 'Failed to pause video processing');
    } finally {
      setIsActionPending(false);
    }
  };

  const handleResumeAnalysis = async () => {
    if (!activeTask) return;
    try {
      setIsActionPending(true);
      await api.resumeTaskProcessing(activeTask.id);
      setActiveJob((prev) => (prev ? { ...prev, status: 'RUNNING' } : null));
      changeTaskState(activeTask.id, 'PROCESSING', 'Operator resumed video processing');
    } catch (err: any) {
      setEngineError(err.message || 'Failed to resume video processing');
    } finally {
      setIsActionPending(false);
    }
  };

  const handleStopAnalysis = async () => {
    if (!activeTask) return;
    try {
      setIsActionPending(true);
      await api.stopTaskProcessing(activeTask.id);
      setActiveJob((prev) => (prev ? { ...prev, status: 'STOPPED' } : null));
      changeTaskState(activeTask.id, 'READY', 'Operator stopped video processing');
    } catch (err: any) {
      setEngineError(err.message || 'Failed to stop video processing');
    } finally {
      setIsActionPending(false);
    }
  };

  const videoSourceUrl = useMemo(() => {
    const rawApi = (import.meta as any).env?.VITE_API_BASE_URL || '';
    const apiPrefix = rawApi ? String(rawApi).replace(/\/$/, '') : '';
    if (!activeTask) return '';
    if (activeTask.id === 'task_railway_cctv_analysis') {
      return `${apiPrefix}/api/tasks/task_railway_cctv_analysis/video/stream`;
    }
    if (activeTask.video_config?.stream_url) {
      const u = activeTask.video_config.stream_url;
      return u.startsWith('/') ? `${apiPrefix}${u}` : u;
    }
    if (activeTask.id) {
      return `${apiPrefix}/api/tasks/${activeTask.id}/video/stream`;
    }
    if (activeTask.video_config?.stored_path) {
      const u = activeTask.video_config.stored_path;
      return u.startsWith('/') ? `${apiPrefix}${u}` : u;
    }
    if (activeTask.video_config?.filename) {
      return `${apiPrefix}/uploads/videos/${activeTask.video_config.filename}`;
    }
    return `${apiPrefix}/uploads/videos/sample_crowd_festival.mp4`;
  }, [activeTask?.id, activeTask?.video_config]);

  const handleTogglePlay = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const handleToggleMute = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const handleToggleLoop = () => {
    if (!videoRef.current) return;
    videoRef.current.loop = !isLooping;
    setIsLooping(!isLooping);
  };

  const handleSpeedChange = (speed: number) => {
    if (!videoRef.current) return;
    videoRef.current.playbackRate = speed;
    setPlaybackSpeed(speed);
  };

  const handleSeek = (newTime: number) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
    if (activeTask) {
      lastFetchedTsRef.current = newTime;
      api.getTaskTelemetry(activeTask.id, newTime).then((t) => {
        if (t && (t.type === 'FRAME_UPDATE' || t.total_people !== undefined)) {
          setTelemetry(t);
          setEngineError(null);
        }
      }).catch(() => {});
    }
  };

  const handleSkip = (seconds: number) => {
    if (!videoRef.current) return;
    const target = Math.max(0, Math.min(videoRef.current.currentTime + seconds, duration || 9999));
    videoRef.current.currentTime = target;
    setCurrentTime(target);
    if (activeTask) {
      lastFetchedTsRef.current = target;
      api.getTaskTelemetry(activeTask.id, target).then((t) => {
        if (t && (t.type === 'FRAME_UPDATE' || t.total_people !== undefined)) {
          setTelemetry(t);
          setEngineError(null);
        }
      }).catch(() => {});
    }
  };

  const handleRetryVideo = () => {
    if (!videoRef.current) return;
    setVideoError(false);
    setVideoLoading(true);
    const retrySrc = activeTask?.id === 'task_railway_cctv_analysis'
      ? `/api/tasks/task_railway_cctv_analysis/video/stream?t=${Date.now()}`
      : `${videoSourceUrl}${videoSourceUrl.includes('?') ? '&' : '?'}t=${Date.now()}`;
    videoRef.current.src = retrySrc;
    videoRef.current.load();
    videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
  };

  const formatVideoTime = (sec: number) => {
    if (isNaN(sec) || sec < 0) return '00:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  if (!activeTask) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8 bg-[#070B14] rounded-xl border border-slate-800">
        <Activity className="h-12 w-12 text-slate-600 mb-3" />
        <h2 className="text-base font-bold text-white">No Active Monitoring Task Selected</h2>
        <p className="text-xs text-slate-400 max-w-sm mt-1">
          Select an existing task from the Topbar task selector, or create a new monitoring task to begin.
        </p>
        <button
          onClick={onOpenCreateTask}
          className="mt-4 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-medium text-xs shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
        >
          Create New Task
        </button>
      </div>
    );
  }

  const isEngineRunning = activeJob?.status === 'RUNNING' || activeTask.state === 'PROCESSING';
  const isEnginePaused = activeJob?.status === 'PAUSED' || activeTask.state === 'PAUSED';

  return (
    <div className="space-y-4">
      {/* Dense Operational Header */}
      <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-wrap items-center justify-between gap-4 shadow-lg">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Video className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-bold text-white tracking-tight">{activeTask.name}</h1>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                  activeTask.state === 'READY'
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                    : isEngineRunning
                    ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 animate-pulse'
                    : isEnginePaused
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
              >
                {activeTask.state}
              </span>
              {wsConnected ? (
                <span className="flex items-center space-x-1 px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[9px] font-mono border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>LIVE WS</span>
                </span>
              ) : (
                <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 text-[9px] font-mono border border-slate-700">
                  STANDBY
                </span>
              )}
            </div>
            <div className="flex items-center space-x-3 text-[11px] text-slate-400 font-mono mt-0.5">
              <span className="flex items-center space-x-1">
                <MapPin className="h-3 w-3 text-slate-500" />
                <span>{activeTask.location || 'Site Location'}</span>
              </span>
              <span>•</span>
              <span>Source: {activeTask.video_config?.source_type || 'FILE'}</span>
              <span>•</span>
              <span>Zones: {zonesToDisplay.length}</span>
              <span>•</span>
              <span>Total Cap: {totalVenueCapacity.toLocaleString()}</span>
            </div>
          </div>
        </div>

        {/* View Mode Selectors & Engine Control */}
        <div className="flex items-center space-x-3">
          {/* Sample FPS Selector */}
          <div className="flex items-center space-x-1.5 px-2 py-1 rounded-lg bg-[#070B14] border border-slate-800 text-xs font-mono text-slate-400">
            <Sliders className="h-3.5 w-3.5 text-cyan-400" />
            <span>Rate:</span>
            <select
              value={sampleFps}
              onChange={(e) => setSampleFps(parseFloat(e.target.value))}
              disabled={isEngineRunning}
              className="bg-transparent text-cyan-400 font-bold focus:outline-none cursor-pointer"
            >
              <option value="0.5" className="bg-[#0B1120]">0.5 FPS</option>
              <option value="1.0" className="bg-[#0B1120]">1.0 FPS</option>
              <option value="2.0" className="bg-[#0B1120]">2.0 FPS</option>
              <option value="5.0" className="bg-[#0B1120]">5.0 FPS</option>
            </select>
          </div>

          {/* View Toggles */}
          <div className="flex items-center bg-[#070B14] border border-slate-800 rounded-lg p-0.5 font-mono text-xs">
            <button
              onClick={() => setViewMode('TRI_VIEW')}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === 'TRI_VIEW'
                  ? 'bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Tri-View
            </button>
            <button
              onClick={() => setViewMode('VIDEO')}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === 'VIDEO'
                  ? 'bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Video
            </button>
            <button
              onClick={() => setViewMode('HEATMAP')}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === 'HEATMAP'
                  ? 'bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Heatmap
            </button>
            <button
              onClick={() => setViewMode('ZONES')}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === 'ZONES'
                  ? 'bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Zone Risk
            </button>
          </div>

          {/* Operational Engine Lifecycle Actions */}
          {!isEngineRunning && !isEnginePaused && (
            <button
              onClick={handleStartAnalysis}
              disabled={isActionPending}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs shadow-md shadow-emerald-500/20 transition-all disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>Start Analysis</span>
            </button>
          )}

          {isEngineRunning && (
            <div className="flex items-center space-x-2">
              <button
                onClick={handlePauseAnalysis}
                disabled={isActionPending}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-medium text-xs shadow-md shadow-amber-500/20 transition-all disabled:opacity-50"
              >
                <Pause className="h-3.5 w-3.5" />
                <span>Pause</span>
              </button>
              <button
                onClick={handleStopAnalysis}
                disabled={isActionPending}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium text-xs shadow-md shadow-red-500/20 transition-all disabled:opacity-50"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                <span>Stop</span>
              </button>
            </div>
          )}

          {isEnginePaused && (
            <div className="flex items-center space-x-2">
              <button
                onClick={handleResumeAnalysis}
                disabled={isActionPending}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs shadow-md shadow-cyan-500/20 transition-all disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>Resume</span>
              </button>
              <button
                onClick={handleStopAnalysis}
                disabled={isActionPending}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium text-xs shadow-md shadow-red-500/20 transition-all disabled:opacity-50"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                <span>Stop</span>
              </button>
            </div>
          )}

          <button
            onClick={onOpenLayoutBuilder}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs transition-colors"
          >
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
            <span>Layout Builder</span>
          </button>
        </div>
      </div>

      {/* Engine Status & KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="p-3 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400 uppercase">Total Detected</span>
          <div className="flex items-baseline space-x-1.5 mt-1">
            <span className="text-xl font-bold font-mono text-white">
              {telemetry ? telemetry.total_people : 0}
            </span>
            <span className="text-[10px] text-cyan-400 font-mono">persons</span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400 uppercase">Active Tracks</span>
          <div className="flex items-baseline space-x-1.5 mt-1">
            <span className="text-xl font-bold font-mono text-cyan-400">
              {telemetry?.detections ? telemetry.detections.length : 0}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">ByteTrack</span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400 uppercase">Max Observed</span>
          <div className="flex items-baseline space-x-1.5 mt-1">
            <span className="text-xl font-bold font-mono text-amber-400">
              {activeJob?.max_people_detected || telemetry?.total_people || 0}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">peak</span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400 uppercase">Timecode / Frame</span>
          <div className="flex items-baseline space-x-1.5 mt-1 font-mono">
            <span className="text-sm font-bold text-white">
              {telemetry ? `${telemetry.video_timestamp_sec.toFixed(1)}s` : '00:00.0'}
            </span>
            <span className="text-[10px] text-slate-400">
              #{telemetry?.frame_index || 0}
            </span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400 uppercase">Processing Rate</span>
          <div className="flex items-baseline space-x-1.5 mt-1">
            <span className="text-sm font-bold font-mono text-emerald-400">
              {activeJob?.processing_fps || sampleFps} FPS
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              {activeJob?.avg_inference_ms ? `${Math.round(activeJob.avg_inference_ms)}ms` : 'fast'}
            </span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400 uppercase">Pipeline Status</span>
          <div className="flex items-center space-x-1.5 mt-1">
            <span
              className={`w-2 h-2 rounded-full ${
                isEngineRunning ? 'bg-emerald-400 animate-ping' : isEnginePaused ? 'bg-amber-400' : 'bg-slate-500'
              }`}
            />
            <span className="text-xs font-mono font-bold text-white uppercase">
              {isEngineRunning ? 'INFERENCE ACTIVE' : isEnginePaused ? 'PAUSED' : 'AWAITING ENGINE'}
            </span>
          </div>
        </div>
      </div>

      {engineError && (
        <div className="p-3 rounded-xl bg-red-950/40 border border-red-500/40 flex items-center justify-between text-xs text-red-300 font-mono">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
            <span>ERROR: {engineError}</span>
          </div>
          <button
            onClick={() => setEngineError(null)}
            className="text-slate-400 hover:text-white text-[11px]"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Monitoring Panels Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* PANEL 1: Original Video Footage with Live Detection Overlays */}
        {(viewMode === 'TRI_VIEW' || viewMode === 'VIDEO') && (
          <div className={`${viewMode === 'VIDEO' ? 'lg:col-span-3' : 'lg:col-span-1'} flex flex-col rounded-xl bg-[#0B1120] border border-slate-800 overflow-hidden shadow-lg`}>
            <div className="h-10 border-b border-slate-800 px-3 flex items-center justify-between bg-[#070B14]">
              <div className="flex items-center space-x-2 text-xs font-semibold text-white">
                <Video className="h-3.5 w-3.5 text-cyan-400" />
                <span>1. Original Video Footage</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <button
                  onClick={() => setShowBoxes(!showBoxes)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                    showBoxes ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                  title="Toggle Detection Bounding Boxes"
                >
                  Boxes
                </button>
                <button
                  onClick={() => setShowTracks(!showTracks)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                    showTracks ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                  title="Toggle Track IDs"
                >
                  Tracks
                </button>
                <button
                  onClick={() => setShowVectors(!showVectors)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                    showVectors ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                  title="Toggle Velocity Vectors"
                >
                  Vectors
                </button>
                <button
                  onClick={() => setShowFootPoints(!showFootPoints)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                    showFootPoints ? 'bg-teal-500/20 text-teal-300 border-teal-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                  title="Toggle Ground-Contact Points"
                >
                  Points
                </button>
                <button
                  onClick={() => setShowTrails(!showTrails)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                    showTrails ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                  title="Toggle Motion Trails"
                >
                  Trails
                </button>
                <button
                  onClick={() => setShowHud(!showHud)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border transition-colors ${
                    showHud ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                  title="Toggle Telemetry HUD"
                >
                  HUD
                </button>
              </div>
            </div>

            <div
              ref={videoContainerRef}
              className="aspect-video bg-[#050811] relative flex items-center justify-center overflow-hidden group"
            >
              {/* Background Video Element with full stream handling */}
              <video
                ref={videoRef}
                src={videoSourceUrl}
                autoPlay
                loop={isLooping}
                muted={isMuted}
                playsInline
                className="w-full h-full object-cover"
                onTimeUpdate={() => {
                  if (!isScrubbing && videoRef.current) {
                    setCurrentTime(videoRef.current.currentTime);
                  }
                }}
                onLoadedMetadata={() => {
                  if (videoRef.current) {
                    setDuration(videoRef.current.duration);
                    setVideoLoading(false);
                    setVideoError(false);
                  }
                }}
                onError={() => {
                  if (videoRef.current && activeTask?.id === 'task_railway_cctv_analysis' && !videoRef.current.src.includes('cctvfootagerailway.mp4')) {
                    videoRef.current.src = '/uploads/videos/cctvfootagerailway.mp4';
                    videoRef.current.load();
                    videoRef.current.play().catch(() => {});
                    return;
                  }
                  setVideoError(true);
                  setVideoLoading(false);
                }}
                onWaiting={() => setVideoLoading(true)}
                onCanPlay={() => setVideoLoading(false)}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
              />

              {/* Dynamic Canvas Overlay for Bounding Boxes, Tracks, Vectors, Foot Points */}
              <canvas
                ref={videoOverlayCanvasRef}
                width={videoDimensions.width}
                height={videoDimensions.height}
                className="absolute inset-0 pointer-events-none z-10"
              />

              {/* Debug HUD Overlay */}
              {showHud && (
                <div className="absolute top-2 left-2 p-2 rounded-lg bg-black/80 border border-slate-800 font-mono text-[9px] text-slate-300 space-y-0.5 z-20 backdrop-blur pointer-events-none">
                  <div className="text-cyan-400 font-bold border-b border-slate-800 pb-0.5 mb-1">
                    STREAM TELEMETRY HUD
                  </div>
                  <div>Native: {telemetry?.frame_w || 1920}x{telemetry?.frame_h || 1080}</div>
                  <div>Viewport: {videoDimensions.width}x{videoDimensions.height}</div>
                  <div>Detector: {activeJob?.detector_backend || 'YOLOv8 / OpenCV'}</div>
                  <div>Perspective: {activeTask.video_config?.camera_perspective || 'FIXED_CCTV'}</div>
                  <div>Visible Tracks: {telemetry?.detections?.length || 0}</div>
                  <div>Total Persons: {telemetry?.total_people || 0}</div>
                  <div>Timecode: {formatVideoTime(currentTime)} / {formatVideoTime(duration)}</div>
                </div>
              )}

              {/* Video Load Error Overlay */}
              {videoError && (
                <div className="absolute inset-0 bg-[#050811]/90 flex flex-col items-center justify-center p-4 text-center z-20">
                  <AlertTriangle className="h-8 w-8 text-amber-400 mb-2" />
                  <span className="text-xs font-bold text-white">Video Stream Unavailable</span>
                  <p className="text-[10px] text-slate-400 max-w-xs mt-1">
                    Could not stream video file from server. Verify backend video storage.
                  </p>
                  <button
                    onClick={handleRetryVideo}
                    className="mt-3 px-3 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] font-mono font-bold transition-all"
                  >
                    Retry Stream
                  </button>
                </div>
              )}

              {/* In-Video Bottom Status Line */}
              <div className="absolute top-2 right-2 flex items-center space-x-1.5 px-2 py-0.5 rounded-full bg-black/60 border border-slate-800 text-[9px] font-mono text-slate-300 backdrop-blur z-20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                <span className="text-cyan-400 font-bold">{telemetry?.detections?.length || 0}</span>
                <span>tracked</span>
              </div>
            </div>

            {/* Comprehensive Video Player Controls Bar */}
            <div className="p-2 bg-[#070B14] border-t border-slate-800 flex flex-col gap-1.5">
              {/* Scrubbing Timeline */}
              <div className="flex items-center space-x-2 px-1">
                <input
                  type="range"
                  min={0}
                  max={duration || 100}
                  step={0.1}
                  value={currentTime}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    setCurrentTime(val);
                    if (videoRef.current) videoRef.current.currentTime = val;
                  }}
                  onMouseDown={() => setIsScrubbing(true)}
                  onMouseUp={() => setIsScrubbing(false)}
                  className="w-full accent-cyan-400 h-1 bg-slate-800 rounded-lg cursor-pointer"
                  title="Seek video timeline"
                />
              </div>

              {/* Controls Strip */}
              <div className="flex items-center justify-between text-xs font-mono text-slate-300">
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleTogglePlay}
                    className="p-1 rounded hover:bg-slate-800 text-slate-200 hover:text-cyan-400 transition-colors"
                    title={isPlaying ? 'Pause' : 'Play'}
                  >
                    {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5 fill-current" />}
                  </button>

                  <button
                    onClick={() => handleSkip(-5)}
                    className="px-1.5 py-0.5 rounded hover:bg-slate-800 text-[10px] text-slate-400 hover:text-white transition-colors"
                    title="Rewind 5 seconds"
                  >
                    -5s
                  </button>

                  <button
                    onClick={() => handleSkip(5)}
                    className="px-1.5 py-0.5 rounded hover:bg-slate-800 text-[10px] text-slate-400 hover:text-white transition-colors"
                    title="Forward 5 seconds"
                  >
                    +5s
                  </button>

                  <span className="text-[11px] text-slate-400 pl-1">
                    {formatVideoTime(currentTime)} / {formatVideoTime(duration)}
                  </span>
                </div>

                <div className="flex items-center space-x-2">
                  {/* Speed Selector */}
                  <select
                    value={playbackSpeed}
                    onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
                    className="bg-[#0B1120] text-cyan-400 border border-slate-800 rounded px-1.5 py-0.5 text-[10px] focus:outline-none"
                    title="Playback Speed"
                  >
                    <option value="0.5">0.5x</option>
                    <option value="1.0">1.0x</option>
                    <option value="1.5">1.5x</option>
                    <option value="2.0">2.0x</option>
                  </select>

                  {/* Loop Toggle */}
                  <button
                    onClick={handleToggleLoop}
                    className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
                      isLooping ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'bg-slate-800 text-slate-500 border-slate-700'
                    }`}
                    title="Toggle Loop Playback"
                  >
                    Loop
                  </button>

                  {/* Mute Toggle */}
                  <button
                    onClick={handleToggleMute}
                    className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                    title={isMuted ? 'Unmute' : 'Mute'}
                  >
                    {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* PANEL 2: Real Crowd-Density Heatmap */}
        {(viewMode === 'TRI_VIEW' || viewMode === 'HEATMAP') && (
          <div className={`${viewMode === 'HEATMAP' ? 'lg:col-span-3' : 'lg:col-span-1'} flex flex-col rounded-xl bg-[#0B1120] border border-slate-800 overflow-hidden shadow-lg`}>
            <div className="h-10 border-b border-slate-800 px-3 flex items-center justify-between bg-[#070B14]">
              <div className="flex items-center space-x-2 text-xs font-semibold text-white">
                <Flame className="h-3.5 w-3.5 text-amber-400" />
                <span>2. Crowd-Density Heatmap</span>
              </div>
              <div className="flex items-center space-x-1 font-mono text-[9px]">
                {(['live', 'accumulated', '30s', '60s', '180s', '300s'] as HeatmapHorizon[]).map((hz) => (
                  <button
                    key={hz}
                    onClick={() => setSelectedHorizon(hz)}
                    className={`px-1.5 py-0.5 rounded uppercase transition-colors ${
                      selectedHorizon === hz
                        ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                        : 'bg-slate-800/60 text-slate-400 hover:text-white border border-slate-700/60'
                    }`}
                  >
                    {hz === 'live' ? 'LIVE' : hz === 'accumulated' ? 'ACCUM' : hz}
                  </button>
                ))}
              </div>
            </div>

            <div className="aspect-video bg-[#050811] relative flex items-center justify-center overflow-hidden">
              {/* Thermal Heatmap Display Canvas */}
              <canvas
                ref={heatmapCanvasRef}
                width={videoDimensions.width}
                height={videoDimensions.height}
                className="w-full h-full object-cover"
              />

              {/* Heatmap Legend & Overlay Specs */}
              <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between text-[10px] font-mono text-slate-300 bg-[#0B1120]/85 px-2 py-1.5 rounded-lg border border-slate-800 backdrop-blur-sm z-10">
                <div className="flex items-center space-x-2">
                  <span className="text-slate-400">Density:</span>
                  <div className="w-16 h-2 rounded-full bg-gradient-to-r from-blue-600 via-emerald-400 via-amber-400 to-red-600" />
                  <span className="text-slate-400">0 → 1.0</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-amber-400 font-bold">
                    {selectedHorizon === 'live'
                      ? 'LIVE KDE'
                      : selectedHorizon === 'accumulated'
                      ? 'ACCUMULATED'
                      : `HORIZON +${selectedHorizon.toUpperCase()}`}
                  </span>
                  <span>•</span>
                  <span>16:9 Matrix</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* PANEL 3: User-Defined Zone Risk Map */}
        {(viewMode === 'TRI_VIEW' || viewMode === 'ZONES') && (
          <div className={`${viewMode === 'ZONES' ? 'lg:col-span-3' : 'lg:col-span-1'} flex flex-col rounded-xl bg-[#0B1120] border border-slate-800 overflow-hidden shadow-lg`}>
            <div className="h-10 border-b border-slate-800 px-3 flex items-center justify-between bg-[#070B14]">
              <div className="flex items-center space-x-2 text-xs font-semibold text-white">
                <ShieldAlert className="h-3.5 w-3.5 text-teal-400" />
                <span>3. User-Defined Zone Risk Map</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-[10px] font-mono text-cyan-400 font-semibold bg-cyan-950/60 border border-cyan-800/50 px-2 py-0.5 rounded">
                  {zonesToDisplay.length} Zones Active
                </span>
              </div>
            </div>

            <div className="aspect-video bg-[#050811] relative flex items-center justify-center overflow-hidden select-none">
              {/* Ground-Truth Spatial Reference Background or Default Neutral Grid */}
              {(() => {
                const layoutBg = activeTask?.layout_snapshot?.background_image_url || (activeTask?.id === 'task_railway_cctv_analysis' ? '/railway_cctv_reference.jpg' : null);
                if (layoutBg) {
                  return (
                    <>
                      <img
                        src={layoutBg}
                        alt="Spatial Reference Background"
                        className="absolute inset-0 w-full h-full object-cover filter brightness-[0.46] contrast-[1.25] saturate-[0.80]"
                      />
                      {videoSourceUrl && (
                        <video
                          src={videoSourceUrl}
                          autoPlay
                          loop={isLooping}
                          muted
                          playsInline
                          className="absolute inset-0 w-full h-full object-cover opacity-20 mix-blend-screen pointer-events-none"
                        />
                      )}
                    </>
                  );
                }
                return (
                  <div className="absolute inset-0 bg-[#070B14]">
                    <div className="absolute inset-0 bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:28px_28px] opacity-25 pointer-events-none" />
                  </div>
                );
              })()}

              {/* Spatial Surveillance HUD Tactical Grid Overlay */}
              <div className="absolute inset-0 bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:28px_28px] opacity-20 pointer-events-none" />

              {/* Scalable Vector SVG Map Matched to 1280x720 Ground-Truth Coordinate Space */}
              <svg
                className="absolute inset-0 w-full h-full pointer-events-auto"
                viewBox="0 0 1280 720"
                preserveAspectRatio="xMidYMid slice"
              >
                <defs>
                  {/* Glowing Risk Shadow Filters */}
                  <filter id="zoneGlowCritical" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="8" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                  <filter id="zoneGlowHigh" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="6" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                  <filter id="zoneGlowSelected" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="10" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>

                {zonesToDisplay.map((zone) => {
                  if (!zone.polygon_points || zone.polygon_points.length < 3) return null;

                  // Parse points to 1280x720 video canvas coordinates
                  const canvasW = 1280;
                  const canvasH = 720;
                  let sumX = 0;
                  let sumY = 0;

                  const scaledPoints = zone.polygon_points.map((p: any) => {
                    const rawX = typeof p.x === 'number' ? p.x : Array.isArray(p) ? p[0] : 0;
                    const rawY = typeof p.y === 'number' ? p.y : Array.isArray(p) ? p[1] : 0;
                    const x = rawX <= 1.0 && rawY <= 1.0 ? rawX * canvasW : rawX;
                    const y = rawX <= 1.0 && rawY <= 1.0 ? rawY * canvasH : rawY;
                    sumX += x;
                    sumY += y;
                    return `${x.toFixed(1)},${y.toFixed(1)}`;
                  });

                  const ptsString = scaledPoints.join(' ');
                  const cx = sumX / zone.polygon_points.length;
                  const cy = sumY / zone.polygon_points.length;

                  const isSelected = selectedZoneId === zone.id;
                  const snap = snapshotsByZoneId[zone.id];
                  const riskInfo = risksByZoneId[zone.id];
                  const riskLevel = riskInfo?.risk_level || 'LOW';

                  // Dynamic risk coloring
                  let fillColor = 'rgba(16, 185, 129, 0.22)';
                  let strokeColor = '#10b981';
                  let filterUrl = '';

                  if (riskLevel === 'CRITICAL') {
                    fillColor = 'rgba(239, 68, 68, 0.45)';
                    strokeColor = '#ef4444';
                    filterUrl = 'url(#zoneGlowCritical)';
                  } else if (riskLevel === 'HIGH') {
                    fillColor = 'rgba(249, 115, 22, 0.35)';
                    strokeColor = '#f97316';
                    filterUrl = 'url(#zoneGlowHigh)';
                  } else if (riskLevel === 'MODERATE') {
                    fillColor = 'rgba(234, 179, 8, 0.28)';
                    strokeColor = '#eab308';
                  }

                  const liveCount = snap ? snap.people_count : 0;
                  const cap = zone.capacity || snap?.capacity || 50;
                  const utilPct = snap ? Math.round(snap.capacity_utilization_pct) : Math.round((liveCount / cap) * 100);
                  const hasActiveAlert = riskLevel === 'CRITICAL' || zone.id === 'zone-boarding-edge';

                  return (
                    <g
                      key={zone.id}
                      onClick={() => setSelectedZoneId(isSelected ? null : zone.id)}
                      className="cursor-pointer transition-all duration-300 group"
                    >
                      {/* Zone Spatial Polygon Boundary */}
                      <polygon
                        points={ptsString}
                        fill={fillColor}
                        stroke={isSelected ? '#ffffff' : strokeColor}
                        strokeWidth={isSelected ? 4.0 : 2.2}
                        filter={isSelected ? 'url(#zoneGlowSelected)' : filterUrl}
                        className={riskLevel === 'CRITICAL' ? 'animate-pulse' : 'transition-colors'}
                      />

                      {/* Vertex Highlight Dots */}
                      {zone.polygon_points.map((p: any, idx: number) => {
                        const rawX = typeof p.x === 'number' ? p.x : Array.isArray(p) ? p[0] : 0;
                        const rawY = typeof p.y === 'number' ? p.y : Array.isArray(p) ? p[1] : 0;
                        const vx = rawX <= 1.0 && rawY <= 1.0 ? rawX * canvasW : rawX;
                        const vy = rawX <= 1.0 && rawY <= 1.0 ? rawY * canvasH : rawY;
                        return (
                          <circle
                            key={idx}
                            cx={vx}
                            cy={vy}
                            r={isSelected ? 3.5 : 2.5}
                            fill={isSelected ? '#ffffff' : strokeColor}
                            stroke="#0B1120"
                            strokeWidth={1}
                          />
                        );
                      })}

                      {/* Centroid Tactical Telemetry Badge */}
                      <g transform={`translate(${cx}, ${cy})`}>
                        {/* Incident Alert Badge if Critical */}
                        {hasActiveAlert && (
                          <g transform="translate(0, -32)">
                            <rect
                              x="-65"
                              y="-10"
                              width="130"
                              height="20"
                              rx="4"
                              fill="rgba(239, 68, 68, 0.95)"
                              stroke="#ffffff"
                              strokeWidth="1"
                              className="animate-pulse"
                            />
                            <text
                              x="0"
                              y="4"
                              fill="#ffffff"
                              fontSize="9"
                              fontWeight="bold"
                              fontFamily="monospace"
                              textAnchor="middle"
                            >
                              ⚠ CRITICAL INCIDENT
                            </text>
                          </g>
                        )}

                        {/* Main Centroid Glass Card */}
                        <rect
                          x="-75"
                          y="-20"
                          width="150"
                          height="42"
                          rx="8"
                          fill="rgba(7, 11, 20, 0.94)"
                          stroke={isSelected ? '#38bdf8' : strokeColor}
                          strokeWidth={isSelected ? 2.5 : 1.2}
                          className="shadow-2xl"
                        />

                        {/* Zone Name Label */}
                        <text
                          x="0"
                          y="-5"
                          fill="#ffffff"
                          fontSize="10"
                          fontWeight="bold"
                          textAnchor="middle"
                        >
                          {zone.name.length > 22 ? `${zone.name.substring(0, 20)}…` : zone.name}
                        </text>

                        {/* Live Headcount & Utilization Display */}
                        <text
                          x="0"
                          y="12"
                          fill={riskLevel === 'CRITICAL' ? '#f87171' : riskLevel === 'HIGH' ? '#fb923c' : riskLevel === 'MODERATE' ? '#fde047' : '#38bdf8'}
                          fontSize="10"
                          fontFamily="monospace"
                          fontWeight="bold"
                          textAnchor="middle"
                        >
                          {liveCount}/{cap} ({utilPct}%) • {riskLevel}
                        </text>
                      </g>
                    </g>
                  );
                })}
              </svg>

              {/* Map Footer HUD Information Bar */}
              <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between text-[10px] font-mono text-slate-300 bg-[#0B1120]/90 px-3 py-1.5 rounded-lg border border-slate-800 backdrop-blur-md z-10">
                <div className="flex items-center space-x-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                  <span className="text-slate-400">Map Mode:</span>
                  <span className="text-white font-bold">SPATIAL CCTV GROUND-TRUTH</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-teal-400 font-bold">
                    {selectedZoneId ? `Selected: ${selectedZoneData?.name || selectedZoneId}` : 'Click any zone polygon to inspect'}
                  </span>
                  <span>•</span>
                  <span className="text-slate-400">1280x720 HD Widescreen</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Selected Zone Deep Dive Telemetry Inspector */}
      {selectedZoneId && selectedZoneData && (
        <div className="p-4 rounded-xl bg-[#0B1120] border border-cyan-500/40 shadow-xl space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Crosshair className="h-4 w-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                Zone Telemetry Deep Dive: {selectedZoneData.name} ({selectedZoneData.zone_type})
              </h3>
            </div>
            <button
              onClick={() => setSelectedZoneId(null)}
              className="text-xs font-mono text-slate-400 hover:text-white"
            >
              Close Inspector ✕
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
            <div className="p-2.5 rounded-lg bg-[#070B14] border border-slate-800">
              <span className="text-slate-400 text-[10px]">Headcount / Capacity</span>
              <div className="text-sm font-bold text-cyan-400 mt-1">
                {selectedSnapshot ? selectedSnapshot.people_count : 0} / {selectedZoneData.capacity || 50}
                <span className="text-[10px] text-slate-400 ml-1">
                  ({selectedSnapshot ? Math.round(selectedSnapshot.capacity_utilization_pct) : 0}%)
                </span>
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-[#070B14] border border-slate-800">
              <span className="text-slate-400 text-[10px]">Inflow / Outflow Rate</span>
              <div className="text-sm font-bold text-white mt-1">
                +{selectedSnapshot?.inflow_rate.toFixed(1) || 0.0} / -{selectedSnapshot?.outflow_rate.toFixed(1) || 0.0}
                <span className="text-[10px] text-slate-400 ml-1">p/min</span>
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-[#070B14] border border-slate-800">
              <span className="text-slate-400 text-[10px]">Movement & Flow Velocity</span>
              <div className="text-sm font-bold text-white mt-1">
                {selectedSnapshot?.movement_direction || 'STATIONARY'}
                <span className="text-[10px] text-slate-400 ml-1">
                  ({selectedSnapshot?.avg_speed.toFixed(2) || 0} px/s)
                </span>
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-[#070B14] border border-slate-800">
              <span className="text-slate-400 text-[10px]">Evaluated Risk Level</span>
              <div className="text-sm font-bold mt-1">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    selectedRisk?.risk_level === 'CRITICAL'
                      ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                      : selectedRisk?.risk_level === 'HIGH'
                      ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40'
                      : selectedRisk?.risk_level === 'MODERATE'
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                      : 'bg-teal-500/20 text-teal-400 border border-teal-500/40'
                  }`}
                >
                  {selectedRisk?.risk_level || 'LOW'}
                </span>
              </div>
            </div>
          </div>

          {selectedRisk?.reason && (
            <div className="p-2.5 rounded-lg bg-[#070B14] border border-slate-800 text-xs font-mono text-slate-300">
              <div className="text-[10px] text-slate-400 uppercase font-bold mb-0.5">Risk Reason & Explainability</div>
              <p>{selectedRisk.reason}</p>
            </div>
          )}
        </div>
      )}

      {/* Spatial Zones & Real-Time Telemetry Summary Table */}
      <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 shadow-lg space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Layers className="h-4 w-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              Live Zone Risk & Flow Telemetry ({zonesToDisplay.length})
            </h3>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Layout: {activeTask.layout_snapshot?.name || 'Custom Spatial Layout'}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#070B14] border-b border-slate-800 text-slate-400 uppercase text-[10px]">
              <tr>
                <th className="p-3">Zone Identifier</th>
                <th className="p-3">Live Count</th>
                <th className="p-3">Capacity</th>
                <th className="p-3">Utilization</th>
                <th className="p-3">Flow Dynamics</th>
                <th className="p-3">Movement</th>
                <th className="p-3">Anomalies</th>
                <th className="p-3">Risk Assessment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {zonesToDisplay.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-slate-500">
                    No spatial zones configured for this task. Open the Layout Builder to add zones.
                  </td>
                </tr>
              )}
              {zonesToDisplay.map((zone) => {
                const snap = snapshotsByZoneId[zone.id];
                const risk = risksByZoneId[zone.id];
                const count = snap ? snap.people_count : 0;
                const cap = zone.capacity || snap?.capacity || 50;
                const utilPct = snap ? Math.round(snap.capacity_utilization_pct) : Math.round((count / cap) * 100);
                const isSelected = selectedZoneId === zone.id;
                const riskLevel = risk?.risk_level || 'LOW';

                return (
                  <tr
                    key={zone.id}
                    onClick={() => setSelectedZoneId(zone.id)}
                    className={`hover:bg-slate-800/40 transition-colors cursor-pointer ${
                      isSelected ? 'bg-slate-800/60 text-white' : 'text-slate-300'
                    }`}
                  >
                    <td className="p-3 font-bold flex items-center space-x-2">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: zone.color || '#06B6D4' }} />
                      <span>{zone.name}</span>
                    </td>
                    <td className="p-3 text-cyan-400 font-bold">{count}</td>
                    <td className="p-3 text-slate-400">{cap}</td>
                    <td className="p-3">
                      <div className="flex items-center space-x-2">
                        <div className="w-16 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                          <div
                            className={`h-full ${
                              utilPct >= 90 ? 'bg-red-500' : utilPct >= 70 ? 'bg-amber-500' : 'bg-cyan-500'
                            }`}
                            style={{ width: `${Math.min(100, utilPct)}%` }}
                          />
                        </div>
                        <span className="text-[10px] text-slate-400">{utilPct}%</span>
                      </div>
                    </td>
                    <td className="p-3 text-slate-300">
                      {snap ? (
                        <span>
                          {snap.net_flow >= 0 ? `+${snap.net_flow.toFixed(1)}` : snap.net_flow.toFixed(1)} p/m
                        </span>
                      ) : (
                        '0.0 p/m'
                      )}
                    </td>
                    <td className="p-3">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400">
                        {snap?.movement_direction || 'STATIONARY'}
                      </span>
                    </td>
                    <td className="p-3">
                      {snap?.is_bottleneck ? (
                        <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 text-[10px] font-bold">
                          BOTTLENECK
                        </span>
                      ) : snap?.is_counterflow ? (
                        <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 text-[10px] font-bold">
                          COUNTERFLOW
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500">Normal</span>
                      )}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          riskLevel === 'CRITICAL'
                            ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                            : riskLevel === 'HIGH'
                            ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40'
                            : riskLevel === 'MODERATE'
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                            : 'bg-teal-500/20 text-teal-400 border border-teal-500/40'
                        }`}
                      >
                        {riskLevel}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
