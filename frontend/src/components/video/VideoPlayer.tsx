import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Maximize2,
  Eye,
  EyeOff,
  Flame,
  Layers,
  ArrowUpRight,
  Sliders,
} from 'lucide-react';
import { DetectionBox, LayoutZoneData } from '../../types';
import { HeatmapOverlay } from './HeatmapOverlay';

interface VideoPlayerProps {
  videoSrc?: string;
  detections?: DetectionBox[];
  zones?: LayoutZoneData[];
  heatmapGrid?: number[][];
  currentTime?: number;
  duration?: number;
  onTimeUpdate?: (time: number) => void;
  isLoading?: boolean;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  videoSrc,
  detections = [],
  zones = [],
  heatmapGrid,
  currentTime = 0,
  duration = 0,
  onTimeUpdate,
  isLoading = false,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [internalTime, setInternalTime] = useState(currentTime);
  const [videoDuration, setVideoDuration] = useState(duration || 10);
  const [dimensions, setDimensions] = useState({ width: 854, height: 480 });

  // Overlays toggle state
  const [showBoxes, setShowBoxes] = useState(true);
  const [showVectors, setShowVectors] = useState(true);
  const [showZones, setShowZones] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [heatmapOpacity, setHeatmapOpacity] = useState(0.65);

  // Resize observer to keep canvas matching video element exactly
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {
          setDimensions({
            width: Math.floor(entry.contentRect.width),
            height: Math.floor(entry.contentRect.height),
          });
        }
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Sync external currentTime
  useEffect(() => {
    if (currentTime !== undefined && Math.abs(internalTime - currentTime) > 0.5) {
      setInternalTime(currentTime);
      if (videoRef.current && Math.abs(videoRef.current.currentTime - currentTime) > 0.5) {
        videoRef.current.currentTime = currentTime;
      }
    }
  }, [currentTime]);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  const handleTimeUpdate = () => {
    if (!videoRef.current) return;
    const t = videoRef.current.currentTime;
    setInternalTime(t);
    if (onTimeUpdate) {
      onTimeUpdate(t);
    }
  };

  const handleLoadedMetadata = () => {
    if (!videoRef.current) return;
    setVideoDuration(videoRef.current.duration || duration || 10);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setInternalTime(val);
    if (videoRef.current) {
      videoRef.current.currentTime = val;
    }
    if (onTimeUpdate) {
      onTimeUpdate(val);
    }
  };

  // Draw Bounding Boxes, Velocity Vectors, and Zones on overlay canvas
  useEffect(() => {
    const canvas = overlayCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, dimensions.width, dimensions.height);

    const scaleX = dimensions.width;
    const scaleY = dimensions.height;

    // 1. Draw Zones Polygons
    if (showZones && zones && zones.length > 0) {
      zones.forEach((z) => {
        if (!z.polygon_points || z.polygon_points.length < 3) return;

        ctx.beginPath();
        const firstPt = z.polygon_points[0];
        ctx.moveTo(firstPt.x * scaleX, firstPt.y * scaleY);

        for (let i = 1; i < z.polygon_points.length; i++) {
          const pt = z.polygon_points[i];
          ctx.lineTo(pt.x * scaleX, pt.y * scaleY);
        }
        ctx.closePath();

        // Polygon styling
        ctx.fillStyle = z.color ? `${z.color}15` : 'rgba(6, 182, 212, 0.08)';
        ctx.fill();

        ctx.strokeStyle = z.color || '#06B6D4';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Zone Name Label at centroid
        let cx = 0;
        let cy = 0;
        z.polygon_points.forEach((p) => {
          cx += p.x;
          cy += p.y;
        });
        cx = (cx / z.polygon_points.length) * scaleX;
        cy = (cy / z.polygon_points.length) * scaleY;

        ctx.font = 'bold 11px Inter, sans-serif';
        const label = z.name || z.zone_name || 'Zone';
        const textWidth = ctx.measureText(label).width;

        ctx.fillStyle = 'rgba(11, 17, 32, 0.85)';
        ctx.fillRect(cx - textWidth / 2 - 6, cy - 10, textWidth + 12, 20);

        ctx.strokeStyle = 'rgba(6, 182, 212, 0.4)';
        ctx.lineWidth = 1;
        ctx.strokeRect(cx - textWidth / 2 - 6, cy - 10, textWidth + 12, 20);

        ctx.fillStyle = '#E2E8F0';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, cx, cy);
      });
    }

    // 2. Draw Detections & Tracking Boxes
    if (showBoxes && detections && detections.length > 0) {
      detections.forEach((det) => {
        const [x1, y1, x2, y2] = det.bbox;
        // Check if normalized or pixel coords
        const bx1 = x1 <= 1.0 ? x1 * scaleX : (x1 / 640) * scaleX;
        const by1 = y1 <= 1.0 ? y1 * scaleY : (y1 / 480) * scaleY;
        const bx2 = x2 <= 1.0 ? x2 * scaleX : (x2 / 640) * scaleX;
        const by2 = y2 <= 1.0 ? y2 * scaleY : (y2 / 480) * scaleY;

        const bw = bx2 - bx1;
        const bh = by2 - by1;

        // Bounding Box
        ctx.strokeStyle = '#22D3EE';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(bx1, by1, bw, bh);

        // Track ID Tag
        const tagText = `#${det.track_id}`;
        ctx.font = 'bold 9px monospace';
        const tw = ctx.measureText(tagText).width;

        ctx.fillStyle = '#0891B2';
        ctx.fillRect(bx1, Math.max(by1 - 14, 0), tw + 6, 14);

        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(tagText, bx1 + 3, Math.max(by1 - 7, 7));

        // Ground Contact Dot
        if (det.ground_contact) {
          const [gx, gy] = det.ground_contact;
          const px = gx <= 1.0 ? gx * scaleX : (gx / 640) * scaleX;
          const py = gy <= 1.0 ? gy * scaleY : (gy / 480) * scaleY;

          ctx.beginPath();
          ctx.arc(px, py, 3, 0, Math.PI * 2);
          ctx.fillStyle = '#10B981';
          ctx.fill();
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 1;
          ctx.stroke();

          // 3. Velocity Vectors
          if (showVectors && det.velocity) {
            const [vx, vy] = det.velocity;
            if (Math.abs(vx) > 0.1 || Math.abs(vy) > 0.1) {
              const arrowLen = 15;
              const angle = Math.atan2(vy, vx);
              const tx = px + Math.cos(angle) * arrowLen;
              const ty = py + Math.sin(angle) * arrowLen;

              ctx.beginPath();
              ctx.moveTo(px, py);
              ctx.lineTo(tx, ty);
              ctx.strokeStyle = '#38BDF8';
              ctx.lineWidth = 2;
              ctx.stroke();

              // Arrow head
              ctx.beginPath();
              ctx.arc(tx, ty, 2, 0, Math.PI * 2);
              ctx.fillStyle = '#38BDF8';
              ctx.fill();
            }
          }
        }
      });
    }
  }, [dimensions, detections, zones, showBoxes, showVectors, showZones]);

  return (
    <div className="flex flex-col rounded-2xl border border-slate-800 bg-[#0B1120] overflow-hidden shadow-2xl">
      {/* Top Toolbar / Overlays Toggle Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2.5 bg-[#070B14] border-b border-slate-800 text-xs">
        <div className="flex items-center space-x-2">
          <span className="font-mono text-cyan-400 font-semibold uppercase tracking-wider flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping inline-block" />
            <span>Continuous Spatial Stream</span>
          </span>
          <span className="text-slate-500">|</span>
          <span className="text-slate-400 font-mono">
            Tracks: <strong className="text-white">{detections.length}</strong>
          </span>
        </div>

        {/* Overlay Switches */}
        <div className="flex items-center space-x-2 mt-2 sm:mt-0">
          <button
            onClick={() => setShowBoxes(!showBoxes)}
            className={`px-2.5 py-1 rounded-md flex items-center space-x-1 font-mono transition-colors ${
              showBoxes
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                : 'text-slate-400 hover:bg-slate-800'
            }`}
            title="Toggle Bounding Boxes"
          >
            {showBoxes ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            <span>Boxes</span>
          </button>

          <button
            onClick={() => setShowVectors(!showVectors)}
            className={`px-2.5 py-1 rounded-md flex items-center space-x-1 font-mono transition-colors ${
              showVectors
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
                : 'text-slate-400 hover:bg-slate-800'
            }`}
            title="Toggle Velocity Vectors"
          >
            <ArrowUpRight className="h-3.5 w-3.5" />
            <span>Vectors</span>
          </button>

          <button
            onClick={() => setShowZones(!showZones)}
            className={`px-2.5 py-1 rounded-md flex items-center space-x-1 font-mono transition-colors ${
              showZones
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-400 hover:bg-slate-800'
            }`}
            title="Toggle Zones"
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Zones</span>
          </button>

          <button
            onClick={() => setShowHeatmap(!showHeatmap)}
            className={`px-2.5 py-1 rounded-md flex items-center space-x-1 font-mono transition-colors ${
              showHeatmap
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                : 'text-slate-400 hover:bg-slate-800'
            }`}
            title="Toggle Heatmap"
          >
            <Flame className="h-3.5 w-3.5" />
            <span>KDE Heatmap</span>
          </button>

          {showHeatmap && (
            <div className="flex items-center space-x-1.5 pl-2 border-l border-slate-800">
              <Sliders className="h-3 w-3 text-slate-500" />
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={heatmapOpacity}
                onChange={(e) => setHeatmapOpacity(parseFloat(e.target.value))}
                className="w-16 accent-cyan-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                title={`Heatmap Opacity: ${Math.round(heatmapOpacity * 100)}%`}
              />
            </div>
          )}
        </div>
      </div>

      {/* Main Single Continuous Viewport */}
      <div
        ref={containerRef}
        className="relative w-full aspect-video bg-[#050810] flex items-center justify-center overflow-hidden"
      >
        {videoSrc ? (
          <video
            ref={videoRef}
            src={videoSrc}
            className="w-full h-full object-contain"
            loop
            muted={isMuted}
            playsInline
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-b from-slate-950 via-[#0B1120] to-slate-950 text-slate-500 p-8">
            <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
              <Layers className="h-8 w-8 text-cyan-400" />
            </div>
            <p className="text-sm font-medium text-slate-300">Continuous Spatial Grid Standby</p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm text-center">
              Active tracks, polygon boundaries, and density distributions are computed in real-time.
            </p>
          </div>
        )}

        {/* Heatmap Layer */}
        {showHeatmap && heatmapGrid && (
          <HeatmapOverlay
            grid={heatmapGrid}
            opacity={heatmapOpacity}
            width={dimensions.width}
            height={dimensions.height}
          />
        )}

        {/* Geometric Overlays Canvas (Boxes, Vectors, Zones) */}
        <canvas
          ref={overlayCanvasRef}
          width={dimensions.width}
          height={dimensions.height}
          className="pointer-events-none absolute inset-0"
        />

        {/* Live Timestamp Watermark */}
        <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/70 backdrop-blur-md border border-slate-700/60 font-mono text-[11px] text-cyan-400 pointer-events-none">
          TIME: {internalTime.toFixed(1)}s / {videoDuration.toFixed(1)}s
        </div>
      </div>

      {/* Video Playback Controls Bar */}
      <div className="p-3 bg-[#070B14] border-t border-slate-800 flex items-center space-x-3">
        <button
          onClick={togglePlay}
          className="p-2 rounded-lg bg-cyan-500 text-slate-950 font-bold hover:bg-cyan-400 transition-colors shadow-md shadow-cyan-500/20"
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>

        {/* Scrubber */}
        <div className="flex-1 flex items-center space-x-2">
          <input
            type="range"
            min="0"
            max={videoDuration || 10}
            step="0.1"
            value={internalTime}
            onChange={handleSeek}
            className="w-full accent-cyan-400 bg-slate-800 h-2 rounded-lg cursor-pointer"
          />
        </div>

        <div className="font-mono text-xs text-slate-400 min-w-[80px] text-right">
          {internalTime.toFixed(1)}s / {videoDuration.toFixed(1)}s
        </div>

        <button
          onClick={() => setIsMuted(!isMuted)}
          className="p-1.5 text-slate-400 hover:text-white rounded transition-colors"
        >
          {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
};
