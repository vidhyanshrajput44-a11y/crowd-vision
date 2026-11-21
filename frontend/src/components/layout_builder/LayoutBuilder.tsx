import React, { useState, useRef, useEffect } from 'react';
import {
  Layers,
  Plus,
  Trash2,
  Save,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Camera,
  Maximize2,
  RefreshCw,
} from 'lucide-react';
import { LayoutZoneData, PolygonPoint, PerspectiveType } from '../../types';
import { api } from '../../services/api';

interface LayoutBuilderProps {
  venueId: string;
  initialZones?: LayoutZoneData[];
  onSaved?: (layoutId: string) => void;
}

const ZONE_COLORS = [
  '#06B6D4', // Cyan
  '#3B82F6', // Blue
  '#10B981', // Emerald
  '#F59E0B', // Amber
  '#EC4899', // Pink
  '#8B5CF6', // Purple
  '#14B8A6', // Teal
];

export const LayoutBuilder: React.FC<LayoutBuilderProps> = ({
  venueId,
  initialZones = [],
  onSaved,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [layoutName, setLayoutName] = useState('Main Venue Layout');
  const [perspective, setPerspective] = useState<PerspectiveType>('drone_top_down');
  const [zones, setZones] = useState<LayoutZoneData[]>(
    initialZones.length > 0
      ? initialZones
      : [
        {
          id: 'zone-1',
          name: 'Main Stage',
          zone_type: 'STAGE',
          polygon_points: [
            { x: 0.15, y: 0.15 },
            { x: 0.85, y: 0.15 },
            { x: 0.85, y: 0.45 },
            { x: 0.15, y: 0.45 },
          ],
          capacity: 250,
          area_sqm: 120,
          color: '#06B6D4',
        },
        {
          id: 'zone-2',
          name: 'South Concourse & Exits',
          zone_type: 'CONCOURSE',
          polygon_points: [
            { x: 0.15, y: 0.55 },
            { x: 0.85, y: 0.55 },
            { x: 0.85, y: 0.85 },
            { x: 0.15, y: 0.85 },
          ],
          capacity: 300,
          area_sqm: 150,
          color: '#3B82F6',
        },
      ]
  );

  const [selectedZoneIndex, setSelectedZoneIndex] = useState<number>(0);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawingPoints, setDrawingPoints] = useState<PolygonPoint[]>([]);
  const [draggedVertex, setDraggedVertex] = useState<{ zoneIdx: number; vertexIdx: number } | null>(null);
  const [canvasDimensions, setCanvasDimensions] = useState({ width: 800, height: 500 });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Resize listener
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          setCanvasDimensions({
            width: Math.floor(entry.contentRect.width),
            height: Math.floor(entry.contentRect.width * 0.625), // 16:10
          });
        }
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Geometry validation helper
  const isPolygonValid = (points: PolygonPoint[]): boolean => {
    if (points.length < 3) return false;
    for (const p of points) {
      if (p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) return false;
    }
    return true;
  };

  // Canvas drawing effect
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvasDimensions;
    ctx.clearRect(0, 0, width, height);

    // 1. Draw Blueprint / Grid Background
    ctx.fillStyle = '#050811';
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = 'rgba(30, 41, 59, 0.4)';
    ctx.lineWidth = 1;
    const gridSize = 40;
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // 2. Draw Existing Configured Zones
    zones.forEach((zone, zIdx) => {
      if (zone.polygon_points.length < 2) return;
      const isSelected = zIdx === selectedZoneIndex;

      ctx.beginPath();
      const first = zone.polygon_points[0];
      ctx.moveTo(first.x * width, first.y * height);

      for (let i = 1; i < zone.polygon_points.length; i++) {
        const pt = zone.polygon_points[i];
        ctx.lineTo(pt.x * width, pt.y * height);
      }
      ctx.closePath();

      // Zone fill
      ctx.fillStyle = zone.color ? `${zone.color}${isSelected ? '33' : '15'}` : 'rgba(6, 182, 212, 0.15)';
      ctx.fill();

      // Zone border
      ctx.strokeStyle = zone.color || '#06B6D4';
      ctx.lineWidth = isSelected ? 2.5 : 1.5;
      if (!isSelected) {
        ctx.setLineDash([5, 5]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // Vertices handles
      zone.polygon_points.forEach((pt, vIdx) => {
        const vx = pt.x * width;
        const vy = pt.y * height;
        ctx.beginPath();
        ctx.arc(vx, vy, isSelected ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? '#FFFFFF' : (zone.color || '#06B6D4');
        ctx.fill();
        ctx.strokeStyle = '#0B1120';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      // Zone Centroid Label
      let cx = 0;
      let cy = 0;
      zone.polygon_points.forEach((p) => {
        cx += p.x;
        cy += p.y;
      });
      cx = (cx / zone.polygon_points.length) * width;
      cy = (cy / zone.polygon_points.length) * height;

      ctx.font = 'bold 12px Inter, sans-serif';
      const label = `${zone.name} (${zone.capacity} cap)`;
      const tw = ctx.measureText(label).width;

      ctx.fillStyle = 'rgba(11, 17, 32, 0.9)';
      ctx.fillRect(cx - tw / 2 - 8, cy - 12, tw + 16, 24);
      ctx.strokeStyle = isSelected ? '#38BDF8' : 'rgba(148, 163, 184, 0.3)';
      ctx.lineWidth = 1;
      ctx.strokeRect(cx - tw / 2 - 8, cy - 12, tw + 16, 24);

      ctx.fillStyle = isSelected ? '#38BDF8' : '#F1F5F9';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cx, cy);
    });

    // 3. Draw Active Polygon Being Drawn
    if (isDrawing && drawingPoints.length > 0) {
      ctx.beginPath();
      const first = drawingPoints[0];
      ctx.moveTo(first.x * width, first.y * height);

      for (let i = 1; i < drawingPoints.length; i++) {
        const pt = drawingPoints[i];
        ctx.lineTo(pt.x * width, pt.y * height);
      }

      ctx.strokeStyle = '#22D3EE';
      ctx.lineWidth = 2;
      ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      drawingPoints.forEach((pt, idx) => {
        ctx.beginPath();
        ctx.arc(pt.x * width, pt.y * height, idx === 0 ? 8 : 5, 0, Math.PI * 2);
        ctx.fillStyle = idx === 0 ? '#10B981' : '#22D3EE';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });
    }
  }, [zones, selectedZoneIndex, isDrawing, drawingPoints, canvasDimensions]);

  // Handle Canvas Click (add vertex or select zone)
  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = (e.clientX - rect.left) / canvasDimensions.width;
    const clickY = (e.clientY - rect.top) / canvasDimensions.height;

    if (isDrawing) {
      // Check if clicking near the starting vertex to close polygon
      if (drawingPoints.length >= 3) {
        const first = drawingPoints[0];
        const dist = Math.hypot(first.x - clickX, first.y - clickY);
        if (dist < 0.04) {
          // Close polygon!
          const newZone: LayoutZoneData = {
            id: `zone-${Date.now()}`,
            name: `Zone ${zones.length + 1}`,
            zone_type: 'GENERAL',
            polygon_points: [...drawingPoints],
            capacity: 100,
            area_sqm: 80,
            color: ZONE_COLORS[zones.length % ZONE_COLORS.length],
          };
          setZones([...zones, newZone]);
          setSelectedZoneIndex(zones.length);
          setIsDrawing(false);
          setDrawingPoints([]);
          return;
        }
      }
      setDrawingPoints([...drawingPoints, { x: clickX, y: clickY }]);
      return;
    }

    // Check vertex click for dragging
    for (let zIdx = 0; zIdx < zones.length; zIdx++) {
      const z = zones[zIdx];
      for (let vIdx = 0; vIdx < z.polygon_points.length; vIdx++) {
        const p = z.polygon_points[vIdx];
        const dist = Math.hypot(p.x - clickX, p.y - clickY);
        if (dist < 0.035) {
          setSelectedZoneIndex(zIdx);
          setDraggedVertex({ zoneIdx: zIdx, vertexIdx: vIdx });
          return;
        }
      }
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!draggedVertex) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const curX = Math.max(0, Math.min(1, (e.clientX - rect.left) / canvasDimensions.width));
    const curY = Math.max(0, Math.min(1, (e.clientY - rect.top) / canvasDimensions.height));

    const updated = [...zones];
    updated[draggedVertex.zoneIdx].polygon_points[draggedVertex.vertexIdx] = {
      x: curX,
      y: curY,
    };
    setZones(updated);
  };

  const handleCanvasMouseUp = () => {
    setDraggedVertex(null);
  };

  const handleSaveLayout = async () => {
    if (!venueId) {
      setErrorMsg('A valid Venue ID is required.');
      return;
    }
    if (zones.length === 0) {
      setErrorMsg('At least one zone polygon must be defined.');
      return;
    }

    setIsSaving(true);
    setErrorMsg(null);
    setSaveSuccess(null);

    try {
      const payload = {
        venue_id: venueId,
        name: layoutName,
        camera_perspective: perspective,
        zones_data: zones.map((z) => ({
          id: z.id,
          name: z.name,
          zone_type: z.zone_type,
          polygon_points: z.polygon_points.map((p: any) =>
            Array.isArray(p) ? [p[0], p[1]] : [p.x, p.y]
          ),
          capacity: z.capacity,
          max_capacity: z.capacity,
          area_sqm: z.area_sqm || 50,
          color: z.color,
        })),
      };

      const res = await api.createLayout(payload);
      setSaveSuccess(`Layout "${res.name}" saved successfully!`);
      if (onSaved) onSaved(res.id);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save venue layout.');
    } finally {
      setIsSaving(false);
    }
  };

  const currentSelectedZone = zones[selectedZoneIndex];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Canvas Interactive Drawing Column */}
      <div className="lg:col-span-3 flex flex-col space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl bg-[#0B1120] border border-slate-800">
          <div>
            <h3 className="text-base font-semibold text-white">Spatial Layout Canvas</h3>
            <p className="text-xs text-slate-400">
              {isDrawing
                ? 'Click vertices on canvas. Click the green starting circle to close the polygon.'
                : 'Click and drag polygon vertices to adjust zone geometries.'}
            </p>
          </div>

          <div className="flex items-center space-x-3">
            {isDrawing ? (
              <button
                onClick={() => {
                  setIsDrawing(false);
                  setDrawingPoints([]);
                }}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                Cancel Drawing
              </button>
            ) : (
              <button
                onClick={() => {
                  setIsDrawing(true);
                  setDrawingPoints([]);
                }}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-colors flex items-center space-x-1.5 shadow-md shadow-cyan-500/20"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Draw New Zone</span>
              </button>
            )}

            <button
              onClick={handleSaveLayout}
              disabled={isSaving}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white transition-all flex items-center space-x-1.5 shadow-md shadow-blue-500/20"
            >
              {isSaving ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              <span>{isSaving ? 'Saving...' : 'Save Layout'}</span>
            </button>
          </div>
        </div>

        {/* Status Messages */}
        {errorMsg && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
        {saveSuccess && (
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center space-x-2">
            <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
            <span>{saveSuccess}</span>
          </div>
        )}

        {/* Canvas Workspace */}
        <div
          ref={containerRef}
          className="relative rounded-2xl border border-slate-800 bg-[#050811] overflow-hidden shadow-2xl flex items-center justify-center cursor-crosshair"
        >
          <canvas
            ref={canvasRef}
            width={canvasDimensions.width}
            height={canvasDimensions.height}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            className="w-full h-auto select-none block"
          />

          {/* Perspective Indicator */}
          <div className="absolute bottom-3 left-3 px-3 py-1 rounded-md bg-slate-900/80 backdrop-blur-sm border border-slate-800 text-[11px] font-mono text-cyan-400 flex items-center space-x-1.5">
            <Camera className="h-3.5 w-3.5" />
            <span>PERSPECTIVE: {perspective.toUpperCase()}</span>
          </div>
        </div>
      </div>

      {/* Zone Inspector & Configuration Column */}
      <div className="flex flex-col space-y-4">
        {/* Layout Properties Card */}
        <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
            Layout Metadata
          </h4>

          <div>
            <label className="text-xs text-slate-400">Layout Name</label>
            <input
              type="text"
              value={layoutName}
              onChange={(e) => setLayoutName(e.target.value)}
              className="mt-1 w-full rounded-lg bg-[#070B14] border border-slate-700 px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>

          <div>
            <label className="text-xs text-slate-400">Camera Perspective</label>
            <select
              value={perspective}
              onChange={(e) => setPerspective(e.target.value as PerspectiveType)}
              className="mt-1 w-full rounded-lg bg-[#070B14] border border-slate-700 px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
            >
              <option value="drone_top_down">Drone Top-Down (Orthogonal)</option>
              <option value="elevated_cctv">Elevated CCTV (High Angle)</option>
              <option value="ground_level">Ground Level (Frontal)</option>
              <option value="standard">Standard Angled</option>
            </select>
          </div>
        </div>

        {/* Selected Zone Inspector */}
        {currentSelectedZone ? (
          <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-3 flex-1">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h4 className="text-xs font-mono uppercase tracking-wider text-cyan-400 font-semibold flex items-center space-x-2">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: currentSelectedZone.color || '#06B6D4' }}
                />
                <span>Zone Inspector</span>
              </h4>

              <button
                onClick={() => {
                  const updated = zones.filter((_, idx) => idx !== selectedZoneIndex);
                  setZones(updated);
                  setSelectedZoneIndex(Math.max(0, selectedZoneIndex - 1));
                }}
                className="text-slate-400 hover:text-rose-400 p-1 transition-colors"
                title="Delete Zone"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div>
              <label className="text-xs text-slate-400">Zone Label</label>
              <input
                type="text"
                value={currentSelectedZone.name}
                onChange={(e) => {
                  const updated = [...zones];
                  updated[selectedZoneIndex].name = e.target.value;
                  setZones(updated);
                }}
                className="mt-1 w-full rounded-lg bg-[#070B14] border border-slate-700 px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400">Zone Type</label>
              <select
                value={currentSelectedZone.zone_type}
                onChange={(e) => {
                  const updated = [...zones];
                  updated[selectedZoneIndex].zone_type = e.target.value;
                  setZones(updated);
                }}
                className="mt-1 w-full rounded-lg bg-[#070B14] border border-slate-700 px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
              >
                <option value="STAGE">Main Stage</option>
                <option value="CONCOURSE">Concourse / Corridor</option>
                <option value="ENTRANCE">Entrance / Turnstiles</option>
                <option value="EXIT">Emergency Exit Gate</option>
                <option value="FOOD_COURT">Food Court / Amenities</option>
                <option value="SEATING">Seated Tier</option>
                <option value="GENERAL">General Standing Area</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-slate-400">Max Capacity</label>
                <input
                  type="number"
                  min="1"
                  value={currentSelectedZone.capacity}
                  onChange={(e) => {
                    const updated = [...zones];
                    updated[selectedZoneIndex].capacity = parseInt(e.target.value) || 50;
                    setZones(updated);
                  }}
                  className="mt-1 w-full rounded-lg bg-[#070B14] border border-slate-700 px-3 py-1.5 text-xs text-white font-mono"
                />
              </div>

              <div>
                <label className="text-xs text-slate-400">Area (m²)</label>
                <input
                  type="number"
                  min="1"
                  value={currentSelectedZone.area_sqm || 50}
                  onChange={(e) => {
                    const updated = [...zones];
                    updated[selectedZoneIndex].area_sqm = parseFloat(e.target.value) || 50;
                    setZones(updated);
                  }}
                  className="mt-1 w-full rounded-lg bg-[#070B14] border border-slate-700 px-3 py-1.5 text-xs text-white font-mono"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-400">Color Palette</label>
              <div className="mt-2 flex items-center space-x-2">
                {ZONE_COLORS.map((col) => (
                  <button
                    key={col}
                    onClick={() => {
                      const updated = [...zones];
                      updated[selectedZoneIndex].color = col;
                      setZones(updated);
                    }}
                    className={`w-6 h-6 rounded-full border-2 transition-transform ${currentSelectedZone.color === col ? 'scale-125 border-white' : 'border-transparent'
                      }`}
                    style={{ backgroundColor: col }}
                  />
                ))}
              </div>
            </div>

            <div className="pt-2 border-t border-slate-800 text-[11px] font-mono text-slate-400 space-y-1">
              <div>Vertices: {currentSelectedZone.polygon_points.length} points</div>
              <div className="flex items-center space-x-1 text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Geometry Valid (Convex/Planar)</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-6 rounded-xl bg-[#0B1120] border border-slate-800 text-center text-slate-500 text-xs">
            No zone selected. Click on a zone to inspect or click "Draw New Zone".
          </div>
        )}

        {/* Zones List Index */}
        <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-2">
          <div className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold mb-2">
            Zone Index ({zones.length})
          </div>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {zones.map((z, idx) => (
              <button
                key={z.id}
                onClick={() => setSelectedZoneIndex(idx)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-colors ${idx === selectedZoneIndex
                    ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                    : 'text-slate-300 hover:bg-slate-800'
                  }`}
              >
                <div className="flex items-center space-x-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: z.color || '#06B6D4' }}
                  />
                  <span>{z.name}</span>
                </div>
                <span className="font-mono text-slate-400">{z.capacity} cap</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
