import React, { useState, useEffect } from 'react';
import {
  Layers,
  Search,
  Plus,
  Edit3,
  Copy,
  Trash2,
  Eye,
  Maximize2,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  X,
  Play,
  ArrowRight,
} from 'lucide-react';
import { VenueLayout, LayoutZoneData } from '../types';
import { api } from '../services/api';

interface LayoutManagementViewProps {
  onOpenBuilderForLayout: (layoutId?: string, initialZones?: LayoutZoneData[]) => void;
  onCreateTaskWithLayout: (layoutId: string) => void;
}

export const LayoutManagementView: React.FC<LayoutManagementViewProps> = ({
  onOpenBuilderForLayout,
  onCreateTaskWithLayout,
}) => {
  const [layouts, setLayouts] = useState<VenueLayout[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Preview Modal
  const [previewLayout, setPreviewLayout] = useState<VenueLayout | null>(null);

  // Rename / Edit Modal
  const [editingLayout, setEditingLayout] = useState<VenueLayout | null>(null);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');

  // Delete Confirmation
  const [deletingLayoutId, setDeletingLayoutId] = useState<string | null>(null);

  const fetchLayouts = async () => {
    try {
      setIsLoading(true);
      setErrorMsg(null);
      const list = await api.getLayouts();
      setLayouts(list);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to fetch layouts');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLayouts();
  }, []);

  const handleDuplicate = async (layoutId: string) => {
    try {
      await api.duplicateLayout(layoutId);
      await fetchLayouts();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to duplicate layout');
    }
  };

  const handleDelete = async () => {
    if (!deletingLayoutId) return;
    try {
      await api.deleteLayout(deletingLayoutId);
      setDeletingLayoutId(null);
      await fetchLayouts();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to delete layout');
    }
  };

  const handleSaveRename = async () => {
    if (!editingLayout || !newName.trim()) return;
    try {
      await api.updateLayout(editingLayout.id, {
        name: newName.trim(),
        description: newDesc.trim(),
      });
      setEditingLayout(null);
      await fetchLayouts();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to rename layout');
    }
  };

  const filtered = layouts.filter((l) =>
    l.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (l.description && l.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-xl bg-[#0B1120] border border-slate-800 shadow-lg">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Spatial Layouts Library</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Reusable venue geometry, zone polygons, and capacity definitions for crowd surveillance.
          </p>
        </div>

        <button
          onClick={() => onOpenBuilderForLayout()}
          className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
        >
          <Plus className="h-4 w-4" />
          <span>Create New Layout</span>
        </button>
      </div>

      {/* Search & Stats Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-[#0B1120] border border-slate-800 text-xs">
        <div className="flex items-center space-x-2 bg-[#070B14] border border-slate-700/80 rounded-lg px-3 py-1.5 w-72">
          <Search className="h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search saved layouts..."
            className="bg-transparent text-white placeholder-slate-500 focus:outline-none w-full text-xs font-mono"
          />
        </div>

        <div className="text-[11px] font-mono text-slate-400">
          Showing <span className="text-cyan-400 font-bold">{filtered.length}</span> of {layouts.length} layouts
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 rounded-xl bg-red-950/60 border border-red-500/40 text-red-200 text-xs flex items-center space-x-2">
          <AlertTriangle className="h-4 w-4 text-red-400 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Layouts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {isLoading ? (
          <div className="col-span-3 p-12 text-center text-slate-500 font-mono text-xs">
            Loading spatial layouts library...
          </div>
        ) : filtered.length === 0 ? (
          <div className="col-span-3 p-12 text-center text-slate-500 font-sans text-xs">
            No layouts found. Click "Create New Layout" to draw a spatial venue plan.
          </div>
        ) : (
          filtered.map((layout) => {
            const zones = layout.zones_data || [];
            const totalCap = zones.reduce((s, z) => s + (z.capacity || 0), 0);

            return (
              <div
                key={layout.id}
                className="rounded-xl border border-slate-800 bg-[#0B1120] overflow-hidden flex flex-col justify-between hover:border-slate-700 transition-all shadow-lg hover:shadow-cyan-500/5"
              >
                <div>
                  {/* Miniature Vector SVG Preview */}
                  <div className="aspect-video bg-[#050811] border-b border-slate-800/80 relative overflow-hidden flex items-center justify-center">
                    {layout.background_image_url ? (
                      <img
                        src={layout.background_image_url}
                        alt={`${layout.name} Spatial Layout Reference`}
                        className="absolute inset-0 w-full h-full object-cover filter brightness-[0.4] contrast-[1.2]"
                      />
                    ) : (
                      <div className="absolute inset-0 bg-[#070B14]">
                        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:24px_24px] opacity-40" />
                      </div>
                    )}
                    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 1280 720">
                      {zones.map((zone) => {
                        if (!zone.polygon_points || zone.polygon_points.length < 3) return null;
                        const ptsStr = zone.polygon_points
                          .map((p: any) => {
                            const rawX = typeof p.x === 'number' ? p.x : Array.isArray(p) ? p[0] : 0;
                            const rawY = typeof p.y === 'number' ? p.y : Array.isArray(p) ? p[1] : 0;
                            const x = rawX <= 1.0 && rawY <= 1.0 ? rawX * 1280 : rawX;
                            const y = rawX <= 1.0 && rawY <= 1.0 ? rawY * 720 : rawY;
                            return `${x.toFixed(1)},${y.toFixed(1)}`;
                          })
                          .join(' ');
                        return (
                          <polygon
                            key={zone.id || Math.random()}
                            points={ptsStr}
                            fill={zone.color ? `${zone.color}40` : 'rgba(6, 182, 212, 0.35)'}
                            stroke={zone.color || '#06B6D4'}
                            strokeWidth="2.5"
                          />
                        );
                      })}
                    </svg>

                    <div className="absolute top-2 right-2 flex items-center space-x-1">
                      {layout.background_image_url ? (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-950/80 text-amber-300 border border-amber-700/60 backdrop-blur-sm">
                          IMAGE
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-700/60 backdrop-blur-sm">
                          GRID
                        </span>
                      )}
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-[#070B14]/80 text-slate-300 border border-slate-700 backdrop-blur-sm">
                        v{layout.version || 1}
                      </span>
                    </div>
                  </div>

                  {/* Layout Metadata */}
                  <div className="p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-white truncate max-w-[200px]" title={layout.name}>
                        {layout.name}
                      </h3>
                      <span className="text-[10px] font-mono text-slate-500">
                        {zones.length} zones
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                      {layout.description || 'Spatial venue layout for real-time crowd distribution.'}
                    </p>

                    <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-2 border-t border-slate-800">
                      <span>Total Cap: <span className="text-white">{totalCap.toLocaleString()}</span></span>
                      <span>Canvas: {layout.canvas_width}x{layout.canvas_height}</span>
                    </div>
                  </div>
                </div>

                {/* Card Actions Bar */}
                <div className="p-3 bg-[#070B14] border-t border-slate-800 flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-1">
                    <button
                      onClick={() => setPreviewLayout(layout)}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                      title="Inspect Geometry Preview"
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        setEditingLayout(layout);
                        setNewName(layout.name);
                        setNewDesc(layout.description || '');
                      }}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                      title="Rename / Edit Description"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => handleDuplicate(layout.id)}
                      className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                      title="Duplicate Layout"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => setDeletingLayoutId(layout.id)}
                      className="p-1.5 rounded hover:bg-red-950/50 text-slate-500 hover:text-red-400 transition-colors"
                      title="Delete Layout"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>

                  <div className="flex items-center space-x-1.5">
                    <button
                      onClick={() => onOpenBuilderForLayout(layout.id, layout.zones_data)}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => onCreateTaskWithLayout(layout.id)}
                      className="px-2.5 py-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-[11px] font-bold flex items-center space-x-1 transition-colors"
                    >
                      <span>Use in Task</span>
                      <ArrowRight className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Preview Modal */}
      {previewLayout && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-4xl bg-[#0B1120] border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col">
            <div className="h-14 border-b border-slate-800 px-6 flex items-center justify-between bg-[#070B14]">
              <div>
                <h3 className="text-sm font-bold text-white">{previewLayout.name} (Preview)</h3>
                <span className="text-[11px] text-slate-400 font-mono">
                  {previewLayout.zones_data?.length || 0} Zones • Canvas: {previewLayout.canvas_width}x{previewLayout.canvas_height}
                </span>
              </div>
              <button
                onClick={() => setPreviewLayout(null)}
                className="p-1.5 text-slate-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="aspect-video bg-[#050811] relative overflow-hidden flex items-center justify-center">
              {previewLayout.background_image_url ? (
                <img
                  src={previewLayout.background_image_url}
                  alt={`${previewLayout.name} Spatial Layout Reference`}
                  className="absolute inset-0 w-full h-full object-cover filter brightness-[0.45] contrast-[1.25]"
                />
              ) : (
                <div className="absolute inset-0 bg-[#070B14]">
                  <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:32px_32px] opacity-45" />
                </div>
              )}
              <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 1280 720">
                {previewLayout.zones_data?.map((z) => {
                  const ptsStr = z.polygon_points
                    .map((p: any) => {
                      const rawX = typeof p.x === 'number' ? p.x : Array.isArray(p) ? p[0] : 0;
                      const rawY = typeof p.y === 'number' ? p.y : Array.isArray(p) ? p[1] : 0;
                      const x = rawX <= 1.0 && rawY <= 1.0 ? rawX * 1280 : rawX;
                      const y = rawX <= 1.0 && rawY <= 1.0 ? rawY * 720 : rawY;
                      return `${x.toFixed(1)},${y.toFixed(1)}`;
                    })
                    .join(' ');
                  return (
                    <g key={z.id}>
                      <polygon
                        points={ptsStr}
                        fill={z.color ? `${z.color}45` : 'rgba(6, 182, 212, 0.35)'}
                        stroke={z.color || '#06B6D4'}
                        strokeWidth="3"
                      />
                    </g>
                  );
                })}
              </svg>
            </div>

            <div className="p-4 bg-[#070B14] border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setPreviewLayout(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename / Edit Modal */}
      {editingLayout && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md bg-[#0B1120] border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white">Edit Layout Metadata</h3>
              <button onClick={() => setEditingLayout(null)} className="p-1 text-slate-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 font-mono mb-1">Layout Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full bg-[#070B14] border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 font-mono mb-1">Description</label>
                <textarea
                  rows={3}
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full bg-[#070B14] border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setEditingLayout(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveRename}
                className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingLayoutId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-sm bg-[#0B1120] border border-red-500/40 rounded-2xl p-6 shadow-2xl space-y-4 text-center">
            <div className="w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 flex items-center justify-center mx-auto">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <h3 className="text-sm font-bold text-white">Delete Spatial Layout?</h3>
            <p className="text-xs text-slate-400">
              Note: Existing monitoring tasks that captured snapshots of this layout will remain unaffected.
            </p>
            <div className="flex items-center justify-center space-x-3 pt-2">
              <button
                onClick={() => setDeletingLayoutId(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white font-bold text-xs shadow-md shadow-red-500/20"
              >
                Delete Layout
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
