import React, { useState, useEffect } from 'react';
import {
  Video,
  Play,
  Square,
  RefreshCw,
  Camera,
  Layers,
  Activity,
  AlertOctagon,
  Clock,
  Sparkles,
} from 'lucide-react';
import { VideoPlayer } from '../components/video/VideoPlayer';
import { ZoneTelemetryCard } from '../components/zones/ZoneTelemetryCard';
import { PredictionViewer } from '../components/predictions/PredictionViewer';
import { RiskPill } from '../components/common/RiskPill';
import {
  EventItem,
  ProcessingJob,
  DetectionSummary,
  HeatmapData,
  PredictionItem,
  RiskItem,
  LayoutZoneData,
  ZoneTelemetry,
  EventZoneSummary,
} from '../types';
import { api } from '../services/api';

interface TaskAnalysisViewProps {
  event: EventItem;
  zones: LayoutZoneData[];
  onOpenLayoutBuilder: () => void;
  onOpenChat: () => void;
}

export const TaskAnalysisView: React.FC<TaskAnalysisViewProps> = ({
  event,
  zones,
  onOpenLayoutBuilder,
  onOpenChat,
}) => {
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [detections, setDetections] = useState<DetectionSummary | null>(null);
  const [heatmapData, setHeatmapData] = useState<HeatmapData | null>(null);
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [zoneSummary, setZoneSummary] = useState<EventZoneSummary | null>(null);
  const [selectedHorizon, setSelectedHorizon] = useState<number>(60);
  const [isStartingJob, setIsStartingJob] = useState(false);
  const [isLoadingAnalytics, setIsLoadingAnalytics] = useState(false);

  // Poll active processing job status for the event
  const fetchJobStatus = async () => {
    try {
      const j = await api.getJobStatus(event.id);
      if (j && j.id) {
        setJob(j);
      }
    } catch {
      // ignore
    }
  };

  // Fetch frame analytics at current timestamp
  const fetchAnalyticsAtTimestamp = async (ts: number) => {
    if (!job && !event.id) return;
    const identifier = job?.id || event.id;

    try {
      const [det, hm, pred, rk, summary] = await Promise.all([
        api.getDetections(identifier, ts).catch(() => null),
        api.getHeatmap(identifier, ts).catch(() => null),
        api.getPredictions(identifier).catch(() => []),
        api.getRisks(identifier, ts).catch(() => []),
        api.getZoneSummary(event.id).catch(() => null),
      ]);

      if (det) setDetections(det);
      if (hm) setHeatmapData(hm);
      if (pred && pred.length > 0) setPredictions(pred);
      if (rk && rk.length > 0) setRisks(rk);
      if (summary) setZoneSummary(summary);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchJobStatus();
    const interval = setInterval(() => {
      fetchJobStatus();
    }, 3000);
    return () => clearInterval(interval);
  }, [event.id]);

  useEffect(() => {
    fetchAnalyticsAtTimestamp(currentTime);
  }, [currentTime, job?.id, event.id]);

  // Determine which heatmap grid to display: current vs predicted horizon
  const activeHeatmapGrid =
    selectedHorizon > 0 && heatmapData?.predicted
      ? heatmapData.predicted[selectedHorizon.toString()] ||
        heatmapData.predicted[`${selectedHorizon}s`] ||
        heatmapData.current
      : heatmapData?.current;

  // Synthesize Zone Telemetry list
  const activeZoneTelemetries: ZoneTelemetry[] = zones.map((z) => {
    const matchingSummary = zoneSummary?.zones?.find((sz) => sz.zone_id === z.id || sz.zone_name === z.name);
    const matchingRisk = risks.find((r) => r.zone_id === z.id);

    if (matchingSummary) {
      return {
        ...matchingSummary,
        risk_level: matchingRisk?.risk_level || matchingSummary.risk_level || 'NORMAL',
      };
    }

    return {
      zone_id: z.id,
      zone_name: z.name,
      people_count: 0,
      occupancy_ratio: 0.0,
      capacity_utilization_pct: 0.0,
      density_value: 0.0,
      inflow_rate: 0.0,
      outflow_rate: 0.0,
      net_flow: 0.0,
      risk_level: matchingRisk?.risk_level || 'NORMAL',
      is_bottleneck: false,
      is_counterflow: false,
      video_timestamp_sec: currentTime,
    };
  });

  return (
    <div className="space-y-6">
      {/* Workspace Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-[#0B1120] border border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-lg font-bold text-white tracking-tight">{event.name}</h2>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
              {event.event_type}
            </span>
          </div>
          <div className="text-xs text-slate-400 font-mono mt-1 flex items-center space-x-3">
            <span className="flex items-center space-x-1">
              <Camera className="h-3.5 w-3.5 text-cyan-400" />
              <span>Perspective: {job?.camera_perspective || 'drone_top_down'}</span>
            </span>
            <span>|</span>
            <span className="flex items-center space-x-1">
              <Clock className="h-3.5 w-3.5 text-blue-400" />
              <span>FPS: {job?.sample_fps || 2.0}</span>
            </span>
            {job?.processing_fps && (
              <>
                <span>|</span>
                <span className="text-emerald-400">Processing: {job.processing_fps} FPS</span>
              </>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-3">
          {job && (
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-[#070B14] border border-slate-800 text-xs font-mono">
              <span
                className={`w-2 h-2 rounded-full ${
                  job.status === 'RUNNING'
                    ? 'bg-cyan-400 animate-ping'
                    : job.status === 'COMPLETED'
                    ? 'bg-emerald-400'
                    : 'bg-amber-400'
                }`}
              />
              <span className="text-white font-semibold">JOB: {job.status}</span>
              {job.progress_pct !== undefined && job.status === 'RUNNING' && (
                <span className="text-cyan-400">({job.progress_pct}%)</span>
              )}
            </div>
          )}

          <button
            onClick={onOpenLayoutBuilder}
            className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors flex items-center space-x-1.5"
          >
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
            <span>Edit Layout Polygons</span>
          </button>

          <button
            onClick={onOpenChat}
            className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white transition-all shadow-md shadow-cyan-500/20 flex items-center space-x-1.5"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Ask Crowd Analyst</span>
          </button>
        </div>
      </div>

      {/* Main Single Continuous Video Analysis Viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col space-y-6">
          <VideoPlayer
            detections={detections?.detections || []}
            zones={zones}
            heatmapGrid={activeHeatmapGrid}
            currentTime={currentTime}
            duration={job?.total_sampled_frames ? job.total_sampled_frames / (job.sample_fps || 2) : 20}
            onTimeUpdate={(t) => setCurrentTime(t)}
          />

          {/* Predictions Across Horizons */}
          <PredictionViewer
            predictions={predictions}
            selectedHorizon={selectedHorizon}
            onSelectHorizon={(hz) => setSelectedHorizon(hz)}
          />
        </div>

        {/* Live Zone Telemetry Matrix Column */}
        <div className="flex flex-col space-y-4">
          <div className="flex items-center justify-between p-3.5 rounded-xl bg-[#0B1120] border border-slate-800">
            <div>
              <h3 className="text-sm font-semibold text-white">Zone Telemetry Matrix</h3>
              <p className="text-[11px] text-slate-400">
                Live density, flow velocities, and capacity limits.
              </p>
            </div>
            <span className="px-2 py-0.5 rounded font-mono text-xs bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              {activeZoneTelemetries.length} Zones
            </span>
          </div>

          <div className="space-y-3 overflow-y-auto max-h-[720px] pr-1">
            {activeZoneTelemetries.map((zt) => {
              const matchedZone = zones.find((z) => z.id === zt.zone_id || z.name === zt.zone_name);
              return (
                <ZoneTelemetryCard
                  key={zt.zone_id}
                  telemetry={zt}
                  maxCapacity={matchedZone?.capacity || 100}
                />
              );
            })}

            {activeZoneTelemetries.length === 0 && (
              <div className="p-8 rounded-xl bg-[#0B1120] border border-slate-800 text-center text-slate-500 text-xs">
                No spatial zones configured yet. Click "Edit Layout Polygons" above to draw custom zone boundaries.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
