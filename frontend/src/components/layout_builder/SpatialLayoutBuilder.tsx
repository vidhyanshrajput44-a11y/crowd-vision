import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Square,
  Pentagon,
  MousePointer,
  Move,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Grid,
  Undo2,
  Redo2,
  Save,
  Trash2,
  Copy,
  Eye,
  EyeOff,
  AlertTriangle,
  CheckCircle2,
  Layers,
  Settings,
  HelpCircle,
  Plus,
  Lock,
  ImagePlus,
  RefreshCw,
} from 'lucide-react';
import { LayoutZoneData, PolygonPoint, VenueLayout } from '../../types';
import { api } from '../../services/api';

export type BuilderTool = 'SELECT' | 'RECTANGLE' | 'POLYGON' | 'VERTEX_EDIT' | 'PAN';

const ZONE_PALETTE = [
  '#06B6D4', // Cyan
  '#3B82F6', // Blue
  '#10B981', // Emerald
  '#F59E0B', // Amber
  '#EF4444', // Red
  '#8B5CF6', // Purple
  '#EC4899', // Pink
  '#14B8A6', // Teal
];

const ZONE_TYPES = [
  'STAGE',
  'CONCOURSE',
  'ENTRANCE',
  'EXIT',
  'EMERGENCY_EXIT',
  'SEATING',
  'BUFFER',
  'QUEUE',
  'GENERAL',
];

interface SpatialLayoutBuilderProps {
  layoutId?: string;
  initialName?: string;
  initialZones?: LayoutZoneData[];
  initialBackgroundImageUrl?: string | null;
  onSaved?: (layout: VenueLayout) => void;
  readOnly?: boolean;
}

export const SpatialLayoutBuilder: React.FC<SpatialLayoutBuilderProps> = ({
  layoutId,
  initialName = 'Spatial Venue Layout',
  initialZones = [],
  initialBackgroundImageUrl = null,
  onSaved,
  readOnly = false,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Layout metadata
  const [layoutName, setLayoutName] = useState(initialName);
  const [description, setDescription] = useState('Standard crowd surveillance and spatial risk grid');
  const [canvasResolution, setCanvasResolution] = useState<{ width: number; height: number }>({
    width: 1920,
    height: 1080,
  });

  // Background Image & Mode State (Default Grid vs Image Background)
  const [backgroundImageUrl, setBackgroundImageUrl] = useState<string | null>(initialBackgroundImageUrl || null);
  const [bgImageElement, setBgImageElement] = useState<HTMLImageElement | null>(null);
  const [showGridOverlayOnImage, setShowGridOverlayOnImage] = useState<boolean>(false);
  const [isUploadingBg, setIsUploadingBg] = useState<boolean>(false);
  const bgFileInputRef = useRef<HTMLInputElement | null>(null);

  // Tools & Viewport
  const [activeTool, setActiveTool] = useState<BuilderTool>('SELECT');
  const [zoom, setZoom] = useState<number>(1.0);
  const [panOffset, setPanOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [gridSize, setGridSize] = useState<number>(40);
  const [snapToGrid, setSnapToGrid] = useState<boolean>(false);
  const [previewMode, setPreviewMode] = useState<boolean>(false);

  const normalizeZoneList = useCallback((rawList: any[]): LayoutZoneData[] => {
    return rawList.map((z: any) => ({
      ...z,
      capacity: z.capacity ?? z.max_capacity ?? 100,
      polygon_points: (z.polygon_points || []).map((p: any) => {
        if (Array.isArray(p) && p.length >= 2) {
          return { x: Number(p[0]) || 0, y: Number(p[1]) || 0 };
        }
        return { x: Number(p?.x ?? 0) || 0, y: Number(p?.y ?? 0) || 0 };
      }),
    }));
  }, []);

  // Preload and cache background image element when URL changes
  useEffect(() => {
    if (!backgroundImageUrl) {
      setBgImageElement(null);
      return;
    }
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      setBgImageElement(img);
    };
    img.onerror = () => {
      console.warn('Could not load background image:', backgroundImageUrl);
    };
    img.src = backgroundImageUrl;
  }, [backgroundImageUrl]);

  // Load layout details from backend when editing an existing saved layout
  useEffect(() => {
    if (!layoutId) {
      if (initialBackgroundImageUrl !== undefined) {
        setBackgroundImageUrl(initialBackgroundImageUrl);
      }
      return;
    }
    let isCancelled = false;
    const fetchLayout = async () => {
      try {
        const layout = await api.getLayout(layoutId);
        if (isCancelled || !layout) return;
        if (layout.name) setLayoutName(layout.name);
        if (layout.description) setDescription(layout.description);
        if (layout.canvas_width && layout.canvas_height) {
          setCanvasResolution({ width: layout.canvas_width, height: layout.canvas_height });
        }
        setBackgroundImageUrl(layout.background_image_url || null);
        if (layout.zones_data && layout.zones_data.length > 0) {
          const normalized = normalizeZoneList(layout.zones_data);
          setZones(normalized);
          setHistory([normalized]);
          setHistoryIndex(0);
        }
      } catch (err) {
        console.warn('Failed to load layout details from server:', err);
      }
    };
    fetchLayout();
    return () => {
      isCancelled = true;
    };
  }, [layoutId, initialBackgroundImageUrl, normalizeZoneList]);

  // Zones & History stack
  const [zones, setZones] = useState<LayoutZoneData[]>(() => {
    if (initialZones.length > 0) return normalizeZoneList(initialZones);
    return [
      {
        id: 'zone-entry-a',
        name: 'Gate A Turnstiles',
        zone_type: 'ENTRANCE',
        polygon_points: [
          { x: 0.08, y: 0.12 },
          { x: 0.38, y: 0.12 },
          { x: 0.38, y: 0.42 },
          { x: 0.08, y: 0.42 },
        ],
        capacity: 150,
        area_sqm: 90,
        color: '#06B6D4',
      },
      {
        id: 'zone-main-stage',
        name: 'Main Stage Floor',
        zone_type: 'STAGE',
        polygon_points: [
          { x: 0.45, y: 0.12 },
          { x: 0.92, y: 0.12 },
          { x: 0.92, y: 0.65 },
          { x: 0.45, y: 0.65 },
        ],
        capacity: 400,
        area_sqm: 240,
        color: '#3B82F6',
      },
    ];
  });

  useEffect(() => {
    if (initialZones && initialZones.length > 0) {
      const normalized = normalizeZoneList(initialZones);
      setZones(normalized);
      setHistory([normalized]);
      setHistoryIndex(0);
    }
  }, [initialZones, normalizeZoneList]);

  const [history, setHistory] = useState<LayoutZoneData[][]>([zones]);
  const [historyIndex, setHistoryIndex] = useState<number>(0);

  const [selectedZoneIndex, setSelectedZoneIndex] = useState<number | null>(0);

  // Drawing state
  const [drawStart, setDrawStart] = useState<PolygonPoint | null>(null);
  const [currentMouseNorm, setCurrentMouseNorm] = useState<PolygonPoint | null>(null);
  const [polyDraftPoints, setPolyDraftPoints] = useState<PolygonPoint[]>([]);

  // Moving / Resizing / Vertex editing state
  const [dragAction, setDragAction] = useState<
    | { type: 'MOVE_ZONE'; zoneIdx: number; startNorm: PolygonPoint; origPoints: PolygonPoint[] }
    | { type: 'MOVE_VERTEX'; zoneIdx: number; vertexIdx: number }
    | { type: 'RESIZE_ZONE'; zoneIdx: number; handle: string; origBox: { minX: number; minY: number; maxX: number; maxY: number }; startNorm: PolygonPoint }
    | null
  >(null);

  // Status & Feedback
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Push to undo stack
  const pushHistory = useCallback((newZones: LayoutZoneData[]) => {
    setHistory((prev) => {
      const sliced = prev.slice(0, historyIndex + 1);
      return [...sliced, newZones];
    });
    setHistoryIndex((prev) => prev + 1);
  }, [historyIndex]);

  const handleUndo = () => {
    if (historyIndex > 0) {
      const newIdx = historyIndex - 1;
      setHistoryIndex(newIdx);
      setZones(history[newIdx]);
      setSelectedZoneIndex(null);
    }
  };

  const handleRedo = () => {
    if (historyIndex < history.length - 1) {
      const newIdx = historyIndex + 1;
      setHistoryIndex(newIdx);
      setZones(history[newIdx]);
      setSelectedZoneIndex(null);
    }
  };

  // Convert canvas pixel mouse coordinate to normalized [0, 1]
  const screenToNorm = (clientX: number, clientY: number): PolygonPoint | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();

    // Accounts for panOffset and zoom
    const rawX = clientX - rect.left;
    const rawY = clientY - rect.top;

    const canvasX = (rawX - panOffset.x) / zoom;
    const canvasY = (rawY - panOffset.y) / zoom;

    let nx = canvasX / canvasResolution.width;
    let ny = canvasY / canvasResolution.height;

    if (snapToGrid) {
      const stepX = gridSize / canvasResolution.width;
      const stepY = gridSize / canvasResolution.height;
      nx = Math.round(nx / stepX) * stepX;
      ny = Math.round(ny / stepY) * stepY;
    }

    return {
      x: Math.max(0, Math.min(1, parseFloat(nx.toFixed(4)))),
      y: Math.max(0, Math.min(1, parseFloat(ny.toFixed(4)))),
    };
  };

  // Self-intersection check
  const checkSelfIntersection = (pts: PolygonPoint[]): boolean => {
    const n = pts.length;
    if (n < 4) return false;
    for (let i = 0; i < n; i++) {
      const a1 = pts[i];
      const a2 = pts[(i + 1) % n];
      for (let j = i + 2; j < n; j++) {
        if (i === 0 && j === n - 1) continue;
        const b1 = pts[j];
        const b2 = pts[(j + 1) % n];

        // Segments intersect?
        const ccw = (p1: PolygonPoint, p2: PolygonPoint, p3: PolygonPoint) =>
          (p2.x - p1.x) * (p3.y - p1.y) - (p2.y - p1.y) * (p3.x - p1.x);

        const d1 = ccw(b1, b2, a1);
        const d2 = ccw(b1, b2, a2);
        const d3 = ccw(a1, a2, b1);
        const d4 = ccw(a1, a2, b2);

        if (((d1 > 1e-5 && d2 < -1e-5) || (d1 < -1e-5 && d2 > 1e-5)) &&
            ((d3 > 1e-5 && d4 < -1e-5) || (d3 < -1e-5 && d4 > 1e-5))) {
          return true;
        }
      }
    }
    return false;
  };

  // Render Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    ctx.save();
    ctx.clearRect(0, 0, width, height);

    // Apply viewport transform (pan & zoom)
    ctx.translate(panOffset.x, panOffset.y);
    ctx.scale(zoom, zoom);

    // 1. Canvas Floor Background
    ctx.fillStyle = previewMode ? '#030712' : '#070B14';
    ctx.fillRect(0, 0, canvasResolution.width, canvasResolution.height);

    // 1b. Render Locked Background Image if configured (Floor plan, aerial photo, or CCTV reference)
    if (bgImageElement) {
      try {
        ctx.drawImage(bgImageElement, 0, 0, canvasResolution.width, canvasResolution.height);
      } catch (err) {
        console.error('Error rendering locked background image layer:', err);
      }
    }

    // Canvas boundary stroke
    ctx.strokeStyle = '#1E293B';
    ctx.lineWidth = 2 / zoom;
    ctx.strokeRect(0, 0, canvasResolution.width, canvasResolution.height);

    // 2. Grid lines (Default grid canvas, or optional tactical overlay on image)
    const shouldDrawGrid = !previewMode && (bgImageElement ? showGridOverlayOnImage : showGrid);
    if (shouldDrawGrid) {
      ctx.strokeStyle = bgImageElement ? 'rgba(255, 255, 255, 0.15)' : 'rgba(30, 41, 59, 0.4)';
      ctx.lineWidth = 1 / zoom;
      for (let x = 0; x <= canvasResolution.width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvasResolution.height);
        ctx.stroke();
      }
      for (let y = 0; y <= canvasResolution.height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvasResolution.width, y);
        ctx.stroke();
      }
    }

    // 3. Render Finished Zones
    zones.forEach((zone, zIdx) => {
      if (zone.polygon_points.length < 2) return;
      const isSelected = selectedZoneIndex === zIdx;

      ctx.beginPath();
      const first = zone.polygon_points[0];
      ctx.moveTo(first.x * canvasResolution.width, first.y * canvasResolution.height);
      for (let i = 1; i < zone.polygon_points.length; i++) {
        const pt = zone.polygon_points[i];
        ctx.lineTo(pt.x * canvasResolution.width, pt.y * canvasResolution.height);
      }
      ctx.closePath();

      // Fill with calibrated transparency
      ctx.fillStyle = zone.color ? `${zone.color}${isSelected ? '35' : '18'}` : 'rgba(6, 182, 212, 0.18)';
      ctx.fill();

      // Stroke
      ctx.strokeStyle = isSelected ? '#FFFFFF' : (zone.color || '#06B6D4');
      ctx.lineWidth = (isSelected ? 2.5 : 1.5) / zoom;
      ctx.stroke();

      // Draw Vertices when Selected
      if (isSelected && !previewMode) {
        zone.polygon_points.forEach((pt) => {
          const vx = pt.x * canvasResolution.width;
          const vy = pt.y * canvasResolution.height;
          ctx.beginPath();
          ctx.arc(vx, vy, 5 / zoom, 0, Math.PI * 2);
          ctx.fillStyle = '#FFFFFF';
          ctx.fill();
          ctx.strokeStyle = zone.color || '#06B6D4';
          ctx.lineWidth = 1.5 / zoom;
          ctx.stroke();
        });

        // Bounding Box with Resize Handles
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        zone.polygon_points.forEach((p) => {
          minX = Math.min(minX, p.x * canvasResolution.width);
          minY = Math.min(minY, p.y * canvasResolution.height);
          maxX = Math.max(maxX, p.x * canvasResolution.width);
          maxY = Math.max(maxY, p.y * canvasResolution.height);
        });

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.setLineDash([4 / zoom, 4 / zoom]);
        ctx.lineWidth = 1 / zoom;
        ctx.strokeRect(minX - 4, minY - 4, maxX - minX + 8, maxY - minY + 8);
        ctx.setLineDash([]);

        // Corner handles for resize
        const handles = [
          [minX - 4, minY - 4],
          [maxX + 4, minY - 4],
          [maxX + 4, maxY + 4],
          [minX - 4, maxY + 4],
        ];
        handles.forEach(([hx, hy]) => {
          ctx.fillStyle = '#38BDF8';
          ctx.fillRect(hx - 3 / zoom, hy - 3 / zoom, 6 / zoom, 6 / zoom);
        });
      }

      // Zone Label Badge
      let cx = 0, cy = 0;
      zone.polygon_points.forEach((p) => {
        cx += p.x;
        cy += p.y;
      });
      cx = (cx / zone.polygon_points.length) * canvasResolution.width;
      cy = (cy / zone.polygon_points.length) * canvasResolution.height;

      ctx.font = `bold ${Math.max(10, Math.min(14, 12 / zoom))}px Inter, sans-serif`;
      const label = `${zone.name} [${zone.capacity} max]`;
      const textMetrics = ctx.measureText(label);
      const tw = textMetrics.width;
      const th = 18 / zoom;

      ctx.fillStyle = 'rgba(11, 17, 32, 0.88)';
      ctx.fillRect(cx - tw / 2 - 6 / zoom, cy - th / 2, tw + 12 / zoom, th);
      ctx.strokeStyle = zone.color || '#06B6D4';
      ctx.lineWidth = 1 / zoom;
      ctx.strokeRect(cx - tw / 2 - 6 / zoom, cy - th / 2, tw + 12 / zoom, th);

      ctx.fillStyle = isSelected ? '#FFFFFF' : '#E2E8F0';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cx, cy);
    });

    // 4. Draw Active Dragging / Drawing
    if (activeTool === 'RECTANGLE' && drawStart && currentMouseNorm) {
      const x1 = Math.min(drawStart.x, currentMouseNorm.x) * canvasResolution.width;
      const y1 = Math.min(drawStart.y, currentMouseNorm.y) * canvasResolution.height;
      const w = Math.abs(currentMouseNorm.x - drawStart.x) * canvasResolution.width;
      const h = Math.abs(currentMouseNorm.y - drawStart.y) * canvasResolution.height;

      ctx.fillStyle = 'rgba(6, 182, 212, 0.2)';
      ctx.fillRect(x1, y1, w, h);
      ctx.strokeStyle = '#22D3EE';
      ctx.lineWidth = 2 / zoom;
      ctx.strokeRect(x1, y1, w, h);
    }

    if (activeTool === 'POLYGON' && polyDraftPoints.length > 0) {
      ctx.beginPath();
      const first = polyDraftPoints[0];
      ctx.moveTo(first.x * canvasResolution.width, first.y * canvasResolution.height);
      for (let i = 1; i < polyDraftPoints.length; i++) {
        const pt = polyDraftPoints[i];
        ctx.lineTo(pt.x * canvasResolution.width, pt.y * canvasResolution.height);
      }
      if (currentMouseNorm) {
        ctx.lineTo(currentMouseNorm.x * canvasResolution.width, currentMouseNorm.y * canvasResolution.height);
      }

      ctx.strokeStyle = '#22D3EE';
      ctx.setLineDash([3 / zoom, 3 / zoom]);
      ctx.lineWidth = 2 / zoom;
      ctx.stroke();
      ctx.setLineDash([]);

      // Vertices
      polyDraftPoints.forEach((pt, idx) => {
        const vx = pt.x * canvasResolution.width;
        const vy = pt.y * canvasResolution.height;
        ctx.beginPath();
        ctx.arc(vx, vy, (idx === 0 ? 6 : 4) / zoom, 0, Math.PI * 2);
        ctx.fillStyle = idx === 0 ? '#10B981' : '#22D3EE';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 1 / zoom;
        ctx.stroke();
      });
    }

    ctx.restore();
  }, [
    zones,
    selectedZoneIndex,
    activeTool,
    drawStart,
    currentMouseNorm,
    polyDraftPoints,
    zoom,
    panOffset,
    showGrid,
    gridSize,
    canvasResolution,
    previewMode,
    bgImageElement,
    showGridOverlayOnImage,
  ]);

  // Mouse Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (readOnly) return;

    if (e.button === 1 || activeTool === 'PAN') {
      setIsPanning(true);
      setPanStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
      return;
    }

    const norm = screenToNorm(e.clientX, e.clientY);
    if (!norm) return;

    if (activeTool === 'RECTANGLE') {
      setDrawStart(norm);
      return;
    }

    if (activeTool === 'POLYGON') {
      if (polyDraftPoints.length >= 3) {
        const first = polyDraftPoints[0];
        const dist = Math.hypot(first.x - norm.x, first.y - norm.y);
        if (dist < 0.035) {
          // Close polygon
          finishPolygonDraft();
          return;
        }
      }
      setPolyDraftPoints((prev) => [...prev, norm]);
      return;
    }

    if (activeTool === 'SELECT' || activeTool === 'VERTEX_EDIT') {
      // 1. Check if clicking on vertex of selected zone
      if (selectedZoneIndex !== null && zones[selectedZoneIndex]) {
        const selZone = zones[selectedZoneIndex];
        for (let vIdx = 0; vIdx < selZone.polygon_points.length; vIdx++) {
          const pt = selZone.polygon_points[vIdx];
          const dist = Math.hypot(pt.x - norm.x, pt.y - norm.y);
          if (dist < 0.03) {
            setDragAction({ type: 'MOVE_VERTEX', zoneIdx: selectedZoneIndex, vertexIdx: vIdx });
            return;
          }
        }
      }

      // 2. Check if clicking inside any zone
      for (let zIdx = zones.length - 1; zIdx >= 0; zIdx--) {
        const z = zones[zIdx];
        if (isPointInsidePolygon(norm, z.polygon_points)) {
          setSelectedZoneIndex(zIdx);
          setDragAction({
            type: 'MOVE_ZONE',
            zoneIdx: zIdx,
            startNorm: norm,
            origPoints: z.polygon_points.map((p) => ({ ...p })),
          });
          return;
        }
      }

      // Clicked empty canvas
      setSelectedZoneIndex(null);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning) {
      setPanOffset({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y,
      });
      return;
    }

    const norm = screenToNorm(e.clientX, e.clientY);
    if (!norm) return;
    setCurrentMouseNorm(norm);

    if (dragAction) {
      if (dragAction.type === 'MOVE_VERTEX') {
        const nextZones = [...zones];
        const z = nextZones[dragAction.zoneIdx];
        z.polygon_points[dragAction.vertexIdx] = norm;
        setZones(nextZones);
      } else if (dragAction.type === 'MOVE_ZONE') {
        const dx = norm.x - dragAction.startNorm.x;
        const dy = norm.y - dragAction.startNorm.y;
        const nextZones = [...zones];
        const z = nextZones[dragAction.zoneIdx];
        z.polygon_points = dragAction.origPoints.map((p) => ({
          x: Math.max(0, Math.min(1, parseFloat((p.x + dx).toFixed(4)))),
          y: Math.max(0, Math.min(1, parseFloat((p.y + dy).toFixed(4)))),
        }));
        setZones(nextZones);
      }
    }
  };

  const handleMouseUp = () => {
    if (isPanning) {
      setIsPanning(false);
      return;
    }

    if (activeTool === 'RECTANGLE' && drawStart && currentMouseNorm) {
      const minX = Math.min(drawStart.x, currentMouseNorm.x);
      const maxX = Math.max(drawStart.x, currentMouseNorm.x);
      const minY = Math.min(drawStart.y, currentMouseNorm.y);
      const maxY = Math.max(drawStart.y, currentMouseNorm.y);

      if (maxX - minX > 0.02 && maxY - minY > 0.02) {
        const newZone: LayoutZoneData = {
          id: `zone-${Date.now().toString(36)}`,
          name: `Zone ${zones.length + 1}`,
          zone_type: 'GENERAL',
          polygon_points: [
            { x: minX, y: minY },
            { x: maxX, y: minY },
            { x: maxX, y: maxY },
            { x: minX, y: maxY },
          ],
          capacity: 100,
          area_sqm: Math.round((maxX - minX) * (maxY - minY) * 1000),
          color: ZONE_PALETTE[zones.length % ZONE_PALETTE.length],
        };
        const updated = [...zones, newZone];
        setZones(updated);
        pushHistory(updated);
        setSelectedZoneIndex(zones.length);
        setActiveTool('SELECT');
      }
      setDrawStart(null);
      return;
    }

    if (dragAction) {
      pushHistory(zones);
      setDragAction(null);
    }
  };

  const finishPolygonDraft = () => {
    if (polyDraftPoints.length >= 3) {
      if (checkSelfIntersection(polyDraftPoints)) {
        setValidationError('Polygon edges cannot self-intersect. Please adjust vertices.');
        return;
      }
      setValidationError(null);
      const newZone: LayoutZoneData = {
        id: `zone-${Date.now().toString(36)}`,
        name: `Zone ${zones.length + 1}`,
        zone_type: 'GENERAL',
        polygon_points: [...polyDraftPoints],
        capacity: 120,
        area_sqm: 100,
        color: ZONE_PALETTE[zones.length % ZONE_PALETTE.length],
      };
      const updated = [...zones, newZone];
      setZones(updated);
      pushHistory(updated);
      setSelectedZoneIndex(zones.length);
      setPolyDraftPoints([]);
      setActiveTool('SELECT');
    }
  };

  const isPointInsidePolygon = (pt: PolygonPoint, poly: PolygonPoint[]): boolean => {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const xi = poly[i].x, yi = poly[i].y;
      const xj = poly[j].x, yj = poly[j].y;
      const intersect = yi > pt.y !== yj > pt.y && pt.x < ((xj - xi) * (pt.y - yi)) / (yj - yi) + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  };

  // Add a vertex to selected zone by clicking on an edge
  const handleAddVertexToSelected = () => {
    if (selectedZoneIndex === null || !zones[selectedZoneIndex]) return;
    const z = zones[selectedZoneIndex];
    const pts = [...z.polygon_points];
    if (pts.length < 2) return;
    // Insert midpoint between vertex 0 and 1
    const p1 = pts[0];
    const p2 = pts[1];
    const mid = { x: parseFloat(((p1.x + p2.x) / 2).toFixed(4)), y: parseFloat(((p1.y + p2.y) / 2).toFixed(4)) };
    pts.splice(1, 0, mid);
    const updated = [...zones];
    updated[selectedZoneIndex].polygon_points = pts;
    setZones(updated);
    pushHistory(updated);
  };

  // Delete selected zone
  const handleDeleteZone = (zIdx: number) => {
    const updated = zones.filter((_, i) => i !== zIdx);
    setZones(updated);
    pushHistory(updated);
    setSelectedZoneIndex(null);
  };

  // Duplicate selected zone
  const handleDuplicateZone = (zIdx: number) => {
    const src = zones[zIdx];
    const clone: LayoutZoneData = {
      ...src,
      id: `zone-${Date.now().toString(36)}`,
      name: `${src.name} (Copy)`,
      polygon_points: src.polygon_points.map((p) => ({
        x: Math.min(1, p.x + 0.05),
        y: Math.min(1, p.y + 0.05),
      })),
    };
    const updated = [...zones, clone];
    setZones(updated);
    pushHistory(updated);
    setSelectedZoneIndex(zones.length);
  };

  // Background Image Handlers
  const handleImageFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploadingBg(true);
    setValidationError(null);

    try {
      // Upload image to backend
      const res = await api.uploadLayoutBackground(file);
      if (res && res.image_url) {
        setBackgroundImageUrl(res.image_url);
        if (res.width && res.height) {
          setCanvasResolution({ width: res.width, height: res.height });
        }
        setSaveSuccess(`Background image "${file.name}" locked successfully.`);
      }
    } catch (err: any) {
      console.warn('Backend image upload failed, falling back to local file reader:', err);
      // Fallback: Read as base64 data URL locally so builder functions even without backend
      const reader = new FileReader();
      reader.onload = (loadEvt) => {
        const dataUrl = loadEvt.target?.result as string;
        if (dataUrl) {
          const testImg = new window.Image();
          testImg.onload = () => {
            if (testImg.naturalWidth && testImg.naturalHeight) {
              setCanvasResolution({ width: testImg.naturalWidth, height: testImg.naturalHeight });
            }
            setBackgroundImageUrl(dataUrl);
            setSaveSuccess(`Background image "${file.name}" locked successfully.`);
          };
          testImg.src = dataUrl;
        }
      };
      reader.readAsDataURL(file);
    } finally {
      setIsUploadingBg(false);
      if (bgFileInputRef.current) {
        bgFileInputRef.current.value = '';
      }
    }
  };

  const handleClearBackground = () => {
    setBackgroundImageUrl(null);
    setBgImageElement(null);
    setShowGridOverlayOnImage(false);
    setSaveSuccess('Background reverted to default spatial grid.');
  };

  // Save / Update Layout to Backend
  const handleSaveLayout = async () => {
    if (zones.length === 0) {
      setValidationError('At least one zone must be defined before saving.');
      return;
    }

    setIsSaving(true);
    setValidationError(null);
    setSaveSuccess(null);

    try {
      const payload: any = {
        name: layoutName.trim(),
        description: description.trim(),
        canvas_width: canvasResolution.width,
        canvas_height: canvasResolution.height,
        background_image_url: backgroundImageUrl || null,
        zones_data: zones.map((z) => ({
          id: z.id,
          name: z.name,
          zone_type: z.zone_type,
          capacity: z.capacity || 100,
          area_sqm: z.area_sqm || 50,
          color: z.color || '#06B6D4',
          polygon_points: (z.polygon_points || []).map((p: any) => {
            if (Array.isArray(p) && p.length >= 2) {
              return [Number(p[0]) || 0, Number(p[1]) || 0];
            }
            return [Number(p?.x ?? 0) || 0, Number(p?.y ?? 0) || 0];
          }),
        })),
      };

      let result: VenueLayout;
      if (layoutId) {
        result = await api.updateLayout(layoutId, payload);
      } else {
        result = await api.createLayout(payload);
      }

      setSaveSuccess(`Layout "${result.name}" persisted successfully (v${result.version || 1})!`);
      if (onSaved) onSaved(result);
    } catch (err: any) {
      setValidationError(err.message || 'Failed to save layout.');
    } finally {
      setIsSaving(false);
    }
  };

  const selectedZone = selectedZoneIndex !== null ? zones[selectedZoneIndex] : null;

  return (
    <div className="flex flex-col h-full bg-[#070B14] text-slate-100 rounded-xl border border-slate-800 overflow-hidden shadow-2xl">
      {/* Top Operations Header */}
      <div className="h-14 border-b border-slate-800/80 bg-[#0B1120] px-4 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center space-x-3">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <input
              type="text"
              value={layoutName}
              disabled={readOnly}
              onChange={(e) => setLayoutName(e.target.value)}
              className="bg-transparent text-sm font-bold text-white border-b border-transparent hover:border-slate-700 focus:border-cyan-500 focus:outline-none px-1"
              title="Layout Name"
            />
            <div className="text-[10px] text-slate-400 font-mono px-1">
              Canvas: {canvasResolution.width}x{canvasResolution.height} • {zones.length} Zones Defined
            </div>
          </div>
        </div>

        {/* Global Action Toolbar */}
        <div className="flex items-center space-x-2">
          {/* Undo / Redo */}
          <div className="flex items-center bg-[#070B14] border border-slate-800 rounded-lg p-0.5">
            <button
              onClick={handleUndo}
              disabled={historyIndex === 0 || readOnly}
              className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30 disabled:pointer-events-none rounded transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Undo2 className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleRedo}
              disabled={historyIndex >= history.length - 1 || readOnly}
              className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30 disabled:pointer-events-none rounded transition-colors"
              title="Redo (Ctrl+Y)"
            >
              <Redo2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Grid & Zoom controls */}
          <div className="flex items-center space-x-1 bg-[#070B14] border border-slate-800 rounded-lg p-0.5">
            <button
              onClick={() => setShowGrid(!showGrid)}
              className={`p-1.5 rounded transition-colors ${showGrid ? 'bg-cyan-500/20 text-cyan-400' : 'text-slate-400 hover:text-white'}`}
              title="Toggle Grid"
            >
              <Grid className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setZoom((z) => Math.min(2.5, z + 0.15))}
              className="p-1.5 text-slate-400 hover:text-white rounded transition-colors"
              title="Zoom In"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <span className="text-[10px] font-mono px-1 text-slate-400 min-w-[36px] text-center">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom((z) => Math.max(0.4, z - 0.15))}
              className="p-1.5 text-slate-400 hover:text-white rounded transition-colors"
              title="Zoom Out"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => { setZoom(1.0); setPanOffset({ x: 0, y: 0 }); }}
              className="p-1.5 text-slate-400 hover:text-white rounded transition-colors"
              title="Reset View"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Background Mode & Upload Controls */}
          <div className="flex items-center space-x-1.5 bg-[#070B14] border border-slate-800 rounded-lg px-2 py-1">
            {backgroundImageUrl ? (
              <div className="flex items-center space-x-1.5">
                <span className="flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950/70 text-amber-300 border border-amber-800/60">
                  <Lock className="h-2.5 w-2.5" />
                  <span>IMAGE (LOCKED)</span>
                </span>
                <button
                  type="button"
                  onClick={() => setShowGridOverlayOnImage(!showGridOverlayOnImage)}
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors border ${
                    showGridOverlayOnImage
                      ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                      : 'text-slate-400 border-slate-800 hover:text-white'
                  }`}
                  title="Toggle Tactical Grid Overlay on Background Image"
                >
                  Grid: {showGridOverlayOnImage ? 'ON' : 'OFF'}
                </button>
                <button
                  type="button"
                  onClick={() => bgFileInputRef.current?.click()}
                  disabled={readOnly}
                  className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
                  title="Replace Background Image"
                >
                  Replace
                </button>
                <button
                  type="button"
                  onClick={handleClearBackground}
                  disabled={readOnly}
                  className="px-2 py-0.5 rounded text-[10px] font-medium bg-red-950/40 hover:bg-red-900/50 text-red-300 border border-red-800/40 transition-colors"
                  title="Remove Background Image & Return to Default Grid"
                >
                  Reset to Grid
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-1.5">
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950/70 text-cyan-300 border border-cyan-800/60">
                  GRID
                </span>
                <button
                  type="button"
                  onClick={() => bgFileInputRef.current?.click()}
                  disabled={isUploadingBg || readOnly}
                  className="flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-colors"
                  title="Upload Custom Image Background (Floor plan, aerial photo, CAD schematic, or CCTV frame)"
                >
                  <ImagePlus className="h-3 w-3" />
                  <span>{isUploadingBg ? 'Uploading...' : 'Add Image Background'}</span>
                </button>
              </div>
            )}
            <input
              ref={bgFileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/webp"
              onChange={handleImageFileUpload}
              className="hidden"
            />
          </div>

          {/* Preview Toggle */}
          <button
            onClick={() => setPreviewMode(!previewMode)}
            className={`flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              previewMode
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-white'
            }`}
          >
            {previewMode ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            <span>{previewMode ? 'Exit Preview' : 'Preview'}</span>
          </button>

          {/* Save Button */}
          {!readOnly && (
            <button
              onClick={handleSaveLayout}
              disabled={isSaving}
              className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-md shadow-cyan-500/20 active:scale-95 transition-all"
            >
              <Save className="h-3.5 w-3.5" />
              <span>{isSaving ? 'Saving...' : 'Save Layout'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Workspace Row */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Vertical Tool Palette */}
        {!readOnly && !previewMode && (
          <div className="w-14 border-r border-slate-800/80 bg-[#0B1120] flex flex-col items-center py-3 space-y-2 z-10 flex-shrink-0">
            <button
              onClick={() => setActiveTool('SELECT')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTool === 'SELECT'
                  ? 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/30 font-bold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
              title="Select / Move Zone"
            >
              <MousePointer className="h-4 w-4" />
            </button>

            <button
              onClick={() => { setActiveTool('RECTANGLE'); setDrawStart(null); }}
              className={`p-2.5 rounded-xl transition-all ${
                activeTool === 'RECTANGLE'
                  ? 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/30 font-bold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
              title="Rectangle Tool (Click & Drag)"
            >
              <Square className="h-4 w-4" />
            </button>

            <button
              onClick={() => { setActiveTool('POLYGON'); setPolyDraftPoints([]); }}
              className={`p-2.5 rounded-xl transition-all ${
                activeTool === 'POLYGON'
                  ? 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/30 font-bold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
              title="Polygon Tool (Click Vertices, Close near Start)"
            >
              <Pentagon className="h-4 w-4" />
            </button>

            <button
              onClick={() => setActiveTool('VERTEX_EDIT')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTool === 'VERTEX_EDIT'
                  ? 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/30 font-bold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
              title="Vertex Edit Tool (Drag Points)"
            >
              <Move className="h-4 w-4" />
            </button>

            <div className="w-8 border-b border-slate-800 my-1" />

            <button
              onClick={() => setActiveTool('PAN')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTool === 'PAN'
                  ? 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/30 font-bold'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
              title="Pan Tool (or Hold Space)"
            >
              <Move className="h-4 w-4 rotate-45" />
            </button>
          </div>
        )}

        {/* Center Canvas Area */}
        <div ref={containerRef} className="flex-1 bg-[#050811] relative overflow-hidden flex items-center justify-center">
          <canvas
            ref={canvasRef}
            width={1280}
            height={720}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            className={`w-full h-full block touch-none ${
              activeTool === 'PAN' ? 'cursor-grab' : activeTool === 'SELECT' ? 'cursor-default' : 'cursor-crosshair'
            }`}
          />

          {/* Validation & Feedback Overlay */}
          {validationError && (
            <div className="absolute top-4 left-4 z-20 flex items-center space-x-2 px-3 py-2 rounded-lg bg-red-950/90 border border-red-500/50 text-red-200 text-xs shadow-xl animate-fade-in">
              <AlertTriangle className="h-4 w-4 text-red-400 flex-shrink-0" />
              <span>{validationError}</span>
            </div>
          )}

          {saveSuccess && (
            <div className="absolute top-4 left-4 z-20 flex items-center space-x-2 px-3 py-2 rounded-lg bg-emerald-950/90 border border-emerald-500/50 text-emerald-200 text-xs shadow-xl animate-fade-in">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
              <span>{saveSuccess}</span>
            </div>
          )}

          {/* Polygon Drawing Helper Bar */}
          {activeTool === 'POLYGON' && polyDraftPoints.length > 0 && (
            <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 z-20 flex items-center space-x-3 px-4 py-2 rounded-xl bg-[#0B1120]/95 border border-cyan-500/40 text-xs font-mono text-cyan-300 shadow-2xl backdrop-blur-md">
              <span>{polyDraftPoints.length} vertices placed</span>
              <button
                onClick={finishPolygonDraft}
                disabled={polyDraftPoints.length < 3}
                className="px-2.5 py-1 rounded bg-cyan-500 text-black font-bold disabled:opacity-40"
              >
                Close Polygon
              </button>
              <button
                onClick={() => setPolyDraftPoints([])}
                className="text-slate-400 hover:text-white"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* Right Zone Properties & Zones List Inspector */}
        <div className="w-80 border-l border-slate-800/80 bg-[#0B1120] flex flex-col z-10 flex-shrink-0">
          <div className="p-3 border-b border-slate-800 text-xs font-semibold text-slate-300 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Settings className="h-3.5 w-3.5 text-cyan-400" />
              <span>Zone Properties</span>
            </div>
            {selectedZone && (
              <span className="text-[10px] font-mono text-slate-500">ID: {selectedZone.id}</span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-sans">
            {selectedZone && selectedZoneIndex !== null ? (
              <div className="space-y-4">
                {/* Name */}
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">Zone Name</label>
                  <input
                    type="text"
                    value={selectedZone.name}
                    disabled={readOnly}
                    onChange={(e) => {
                      const updated = [...zones];
                      updated[selectedZoneIndex].name = e.target.value;
                      setZones(updated);
                    }}
                    className="w-full bg-[#070B14] border border-slate-700 rounded-lg px-2.5 py-1.5 text-white text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>

                {/* Type */}
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">Zone Type</label>
                  <select
                    value={selectedZone.zone_type}
                    disabled={readOnly}
                    onChange={(e) => {
                      const updated = [...zones];
                      updated[selectedZoneIndex].zone_type = e.target.value;
                      setZones(updated);
                    }}
                    className="w-full bg-[#070B14] border border-slate-700 rounded-lg px-2.5 py-1.5 text-white text-xs focus:outline-none focus:border-cyan-500"
                  >
                    {ZONE_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>

                {/* Color Palette */}
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1.5">Zone Border & Accent</label>
                  <div className="flex items-center space-x-2">
                    {ZONE_PALETTE.map((c) => (
                      <button
                        key={c}
                        onClick={() => {
                          const updated = [...zones];
                          updated[selectedZoneIndex].color = c;
                          setZones(updated);
                        }}
                        style={{ backgroundColor: c }}
                        className={`w-5 h-5 rounded-full transition-transform ${
                          selectedZone.color === c ? 'scale-125 ring-2 ring-white' : 'hover:scale-110'
                        }`}
                      />
                    ))}
                  </div>
                </div>

                {/* Capacity */}
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">Design Capacity (Persons)</label>
                  <input
                    type="number"
                    min="1"
                    max="50000"
                    value={selectedZone.capacity}
                    disabled={readOnly}
                    onChange={(e) => {
                      const val = Math.max(1, parseInt(e.target.value) || 1);
                      const updated = [...zones];
                      updated[selectedZoneIndex].capacity = val;
                      setZones(updated);
                    }}
                    className="w-full bg-[#070B14] border border-slate-700 rounded-lg px-2.5 py-1.5 text-white text-xs font-mono focus:outline-none focus:border-cyan-500"
                  />
                </div>

                {/* Geometry Stats */}
                <div className="p-3 rounded-lg bg-[#070B14] border border-slate-800 space-y-1.5 text-[11px] font-mono text-slate-400">
                  <div className="flex justify-between">
                    <span>Vertices:</span>
                    <span className="text-white">{selectedZone.polygon_points.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Est. Area:</span>
                    <span className="text-white">{selectedZone.area_sqm || 60} m²</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Warning Level (70%):</span>
                    <span className="text-amber-400">{Math.round(selectedZone.capacity * 0.7)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Critical Level (90%):</span>
                    <span className="text-red-400">{Math.round(selectedZone.capacity * 0.9)}</span>
                  </div>
                </div>

                {/* Zone Manipulation Actions */}
                {!readOnly && (
                  <div className="space-y-2 pt-2 border-t border-slate-800">
                    <button
                      onClick={handleAddVertexToSelected}
                      className="w-full flex items-center justify-center space-x-1.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      <span>Add Vertex to Edge</span>
                    </button>

                    <button
                      onClick={() => handleDuplicateZone(selectedZoneIndex)}
                      className="w-full flex items-center justify-center space-x-1.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      <span>Duplicate Zone</span>
                    </button>

                    <button
                      onClick={() => handleDeleteZone(selectedZoneIndex)}
                      className="w-full flex items-center justify-center space-x-1.5 py-1.5 rounded-lg bg-red-950/40 hover:bg-red-900/60 border border-red-500/30 text-red-300 text-xs transition-colors"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span>Delete Zone</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-40 flex flex-col items-center justify-center text-center text-slate-500">
                <MousePointer className="h-8 w-8 mb-2 opacity-30" />
                <p className="text-xs">No zone selected</p>
                <p className="text-[10px] mt-1 text-slate-600">Click on any zone or choose a drawing tool to create one</p>
              </div>
            )}

            {/* Configured Zones List */}
            <div className="pt-4 border-t border-slate-800">
              <div className="text-[11px] font-mono text-slate-400 mb-2 uppercase tracking-wider">
                Configured Zones ({zones.length})
              </div>
              <div className="space-y-1.5">
                {zones.map((z, idx) => (
                  <div
                    key={z.id}
                    onClick={() => setSelectedZoneIndex(idx)}
                    className={`p-2 rounded-lg border text-xs cursor-pointer flex items-center justify-between transition-colors ${
                      selectedZoneIndex === idx
                        ? 'bg-slate-800 border-cyan-500/80 text-white'
                        : 'bg-[#070B14] border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <div className="flex items-center space-x-2 truncate">
                      <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: z.color || '#06B6D4' }} />
                      <span className="truncate">{z.name}</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-500 ml-2">{z.capacity} cap</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
