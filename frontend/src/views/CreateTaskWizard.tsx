import React, { useState, useEffect } from 'react';
import {
  Check,
  ChevronRight,
  ChevronLeft,
  X,
  Layers,
  FileVideo,
  Radio,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Plus,
  Compass,
  FileText,
  MapPin,
  Calendar,
  Eye,
} from 'lucide-react';
import { SpatialLayoutBuilder } from '../components/layout_builder/SpatialLayoutBuilder';
import { VenueLayout, LayoutZoneData, VideoSourceType, TaskItem } from '../types';
import { api } from '../services/api';
import { useTaskContext } from '../context/TaskContext';

interface CreateTaskWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onTaskCreated: (task: TaskItem) => void;
}

const STEPS = [
  { id: 1, title: 'Task Info', desc: 'Identity & Location' },
  { id: 2, title: 'Layout', desc: 'Select or Create' },
  { id: 3, title: 'Zones', desc: 'Spatial Geometry' },
  { id: 4, title: 'Video Source', desc: 'Feed Configuration' },
  { id: 5, title: 'Review', desc: 'Verify & Confirm' },
];

const toArrayPoint = (p: any): [number, number] => {
  if (Array.isArray(p) && p.length >= 2) {
    return [Number(p[0]) || 0, Number(p[1]) || 0];
  }
  if (p && typeof p === 'object') {
    const x = p.x ?? p.lng ?? p[0] ?? 0;
    const y = p.y ?? p.lat ?? p[1] ?? 0;
    return [Number(x) || 0, Number(y) || 0];
  }
  return [0, 0];
};

const toObjPoint = (p: any): { x: number; y: number } => {
  if (Array.isArray(p) && p.length >= 2) {
    return { x: Number(p[0]) || 0, y: Number(p[1]) || 0 };
  }
  if (p && typeof p === 'object') {
    const x = p.x ?? p.lng ?? p[0] ?? 0;
    const y = p.y ?? p.lat ?? p[1] ?? 0;
    return { x: Number(x) || 0, y: Number(y) || 0 };
  }
  return { x: 0, y: 0 };
};

export const CreateTaskWizard: React.FC<CreateTaskWizardProps> = ({
  isOpen,
  onClose,
  onTaskCreated,
}) => {
  const { createTask } = useTaskContext();

  const [currentStep, setCurrentStep] = useState<number>(1);

  // Step 1: Task Information
  const [taskName, setTaskName] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [notes, setNotes] = useState('');

  // Step 2: Layout Selection
  const [savedLayouts, setSavedLayouts] = useState<VenueLayout[]>([]);
  const [layoutMode, setLayoutMode] = useState<'EXISTING' | 'NEW'>('EXISTING');
  const [selectedLayoutId, setSelectedLayoutId] = useState<string>('');
  const [newLayoutName, setNewLayoutName] = useState('');

  // Step 3: Zone Configuration
  const [currentZones, setCurrentZones] = useState<LayoutZoneData[]>([]);

  // Step 4: Video Configuration
  const [sourceType, setSourceType] = useState<VideoSourceType>('FILE');
  const [sourceUri, setSourceUri] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [cameraPerspective, setCameraPerspective] = useState<string>('DRONE_TOPDOWN');
  const [sampleFps, setSampleFps] = useState<number>(2.0);

  // Step 5 & 6: State & Status
  const [initialState, setInitialState] = useState<'DRAFT' | 'READY'>('READY');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [stepError, setStepError] = useState<string | null>(null);
  const [successTask, setSuccessTask] = useState<TaskItem | null>(null);

  // Load existing layouts when wizard opens
  useEffect(() => {
    if (isOpen) {
      api.getLayouts()
        .then((layouts) => {
          setSavedLayouts(layouts);
          if (layouts.length > 0) {
            setSelectedLayoutId(layouts[0].id);
            if (layouts[0].zones_data) {
              setCurrentZones(layouts[0].zones_data.map((z: any) => ({
                ...z,
                capacity: z.capacity ?? z.max_capacity ?? 100,
                polygon_points: (z.polygon_points || []).map(toObjPoint),
              })));
            }
          } else {
            setLayoutMode('NEW');
            setNewLayoutName('Main Venue Layout');
          }
        })
        .catch(() => {
          setLayoutMode('NEW');
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Step 1 Validation
  const validateStep1 = (): boolean => {
    if (!taskName.trim()) {
      setStepError('Task name is required.');
      return false;
    }
    if (!location.trim()) {
      setStepError('Monitoring location is required.');
      return false;
    }
    setStepError(null);
    return true;
  };

  // Step 2 Validation
  const validateStep2 = (): boolean => {
    if (layoutMode === 'EXISTING' && !selectedLayoutId) {
      setStepError('Please select a saved spatial layout.');
      return false;
    }
    if (layoutMode === 'NEW' && !newLayoutName.trim()) {
      setStepError('New layout name is required.');
      return false;
    }
    setStepError(null);
    return true;
  };

  // Step 3 Validation
  const validateStep3 = (): boolean => {
    if (currentZones.length === 0) {
      setStepError('At least one spatial zone must be configured before proceeding.');
      return false;
    }
    setStepError(null);
    return true;
  };

  // Step 4 Validation
  const validateStep4 = (): boolean => {
    if (sourceType === 'CCTV_STREAM' && !sourceUri.trim()) {
      setStepError('RTSP or HTTP stream URI is required for live CCTV.');
      return false;
    }
    setStepError(null);
    return true;
  };

  const handleNext = () => {
    if (currentStep === 1 && !validateStep1()) return;
    if (currentStep === 2 && !validateStep2()) return;
    if (currentStep === 3 && !validateStep3()) return;
    if (currentStep === 4 && !validateStep4()) return;

    setStepError(null);
    setCurrentStep((s) => Math.min(5, s + 1));
  };

  const handleBack = () => {
    setStepError(null);
    setCurrentStep((s) => Math.max(1, s - 1));
  };

  // Save Task
  const handleSaveTask = async () => {
    setIsSubmitting(true);
    setStepError(null);

    try {
      let layoutIdToUse = layoutMode === 'EXISTING' ? selectedLayoutId : undefined;

      // If user created a new layout, persist it to library first
      if (layoutMode === 'NEW') {
        const createdLayout = await api.createLayout({
          name: newLayoutName.trim(),
          description: `Generated during creation of task ${taskName.trim()}`,
          zones_data: currentZones.map((z) => ({
            id: z.id,
            name: z.name,
            zone_type: z.zone_type,
            capacity: z.capacity ?? z.max_capacity ?? 100,
            color: z.color || '#0d9488',
            polygon_points: (z.polygon_points || []).map(toArrayPoint),
          })),
        });
        layoutIdToUse = createdLayout.id;
      }

      // Snapshot is frozen copy of current zones
      const selectedL = savedLayouts.find((l) => l.id === selectedLayoutId);
      const layoutSnapshot = {
        layout_id: layoutIdToUse,
        name: layoutMode === 'NEW' ? newLayoutName.trim() : (selectedL?.name || 'Custom Layout'),
        background_image_url: layoutMode === 'NEW' ? null : (selectedL?.background_image_url || null),
        zones_count: currentZones.length,
        zones_data: currentZones.map((z) => ({
          ...z,
          capacity: z.capacity ?? z.max_capacity ?? 100,
          polygon_points: (z.polygon_points || []).map(toArrayPoint),
        })),
        snapshot_created_at: new Date().toISOString(),
      };

      const videoConfig = {
        source_type: sourceType,
        source_uri: sourceUri.trim() || undefined,
        camera_perspective: cameraPerspective,
        sample_fps: sampleFps,
        filename: selectedFile ? selectedFile.name : undefined,
      };

      const newTask = await createTask({
        name: taskName.trim(),
        description: description.trim() || undefined,
        location: location.trim(),
        state: initialState,
        layout_id: layoutIdToUse,
        layout_snapshot: layoutSnapshot,
        video_config: videoConfig,
        analysis_settings: {
          detector: 'yolov8m',
          confidence_threshold: 0.35,
          density_method: 'gaussian',
          risk_hysteresis: true,
        },
        notes: notes.trim() || undefined,
      });

      // If video file is present, upload it to the backend
      if (selectedFile) {
        try {
          await api.uploadVideo(newTask.id, selectedFile, sampleFps, cameraPerspective, false);
        } catch {
          // Task still created
        }
      }

      setSuccessTask(newTask);
      onTaskCreated(newTask);
    } catch (err: any) {
      setStepError(err.message || 'Failed to persist monitoring task.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-5xl h-[88vh] bg-[#0B1120] border border-slate-800 rounded-2xl flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="h-16 border-b border-slate-800 px-6 flex items-center justify-between flex-shrink-0 bg-[#070B14]">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center">
              <Plus className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-tight">Create Monitoring Task</h2>
              <p className="text-[11px] text-slate-400">Configure surveillance task, spatial zones, and video telemetry</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Stepper Progress Bar */}
        <div className="border-b border-slate-800/80 bg-[#070B14]/60 px-6 py-3 flex items-center justify-between flex-shrink-0">
          {STEPS.map((step, idx) => {
            const isDone = currentStep > step.id;
            const isCurrent = currentStep === step.id;
            return (
              <React.Fragment key={step.id}>
                <div className="flex items-center space-x-2">
                  <div
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono font-bold transition-colors ${
                      isDone
                        ? 'bg-emerald-500 text-black'
                        : isCurrent
                        ? 'bg-cyan-500 text-black ring-2 ring-cyan-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {isDone ? <Check className="h-3 w-3 stroke-[3]" /> : step.id}
                  </div>
                  <div className="hidden sm:block">
                    <div className={`text-xs font-semibold leading-none ${isCurrent ? 'text-cyan-400' : 'text-slate-300'}`}>
                      {step.title}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">{step.desc}</div>
                  </div>
                </div>
                {idx < STEPS.length - 1 && (
                  <div className={`flex-1 h-[1px] mx-3 ${currentStep > idx + 1 ? 'bg-cyan-500/50' : 'bg-slate-800'}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Wizard Body Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-[#070B14]">
          {stepError && (
            <div className="mb-4 flex items-center space-x-2 p-3 rounded-xl bg-red-950/60 border border-red-500/40 text-red-200 text-xs">
              <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
              <span>{stepError}</span>
            </div>
          )}

          {/* Success Screen */}
          {successTask ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <h3 className="text-lg font-bold text-white">Monitoring Task Created Successfully!</h3>
              <p className="text-xs text-slate-400 max-w-md">
                Task <span className="text-cyan-400 font-mono">{successTask.name}</span> has been saved with a frozen snapshot of {successTask.layout_snapshot?.zones_data?.length || 0} spatial zones.
              </p>
              <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 text-left font-mono text-xs text-slate-300 space-y-1 w-full max-w-md">
                <div>ID: <span className="text-slate-400">{successTask.id}</span></div>
                <div>Location: <span className="text-slate-400">{successTask.location}</span></div>
                <div>State: <span className="text-cyan-400">{successTask.state}</span></div>
                <div>Source: <span className="text-slate-400">{successTask.video_config?.source_type}</span></div>
              </div>
              <button
                onClick={onClose}
                className="mt-4 px-6 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-lg shadow-cyan-500/25 transition-all"
              >
                Done
              </button>
            </div>
          ) : (
            <>
              {/* STEP 1: Task Information */}
              {currentStep === 1 && (
                <div className="max-w-xl mx-auto space-y-4">
                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1">
                      Task Name <span className="text-cyan-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={taskName}
                      onChange={(e) => setTaskName(e.target.value)}
                      placeholder="e.g., North Gate Entry Monitoring"
                      className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1">
                      Monitoring Location <span className="text-cyan-400">*</span>
                    </label>
                    <div className="relative">
                      <MapPin className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-3" />
                      <input
                        type="text"
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        placeholder="e.g., Olympic Stadium - Concourse Level 2"
                        className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl pl-9 pr-3 py-2.5 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1">Description</label>
                    <textarea
                      rows={3}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="Operational purpose of this monitoring session..."
                      className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1">Operational Notes</label>
                    <textarea
                      rows={2}
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Special instructions, gate opening times, emergency contacts..."
                      className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
              )}

              {/* STEP 2: Layout Selection */}
              {currentStep === 2 && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4 max-w-xl mx-auto">
                    <button
                      type="button"
                      onClick={() => setLayoutMode('EXISTING')}
                      className={`p-4 rounded-xl border text-left transition-all ${
                        layoutMode === 'EXISTING'
                          ? 'bg-cyan-500/10 border-cyan-500 text-white shadow-lg shadow-cyan-500/10'
                          : 'bg-[#0B1120] border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      <Layers className="h-5 w-5 mb-2 text-cyan-400" />
                      <div className="text-xs font-bold text-white">Select Saved Layout</div>
                      <div className="text-[10px] text-slate-400 mt-1">Reuse pre-calibrated venue zones</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setLayoutMode('NEW')}
                      className={`p-4 rounded-xl border text-left transition-all ${
                        layoutMode === 'NEW'
                          ? 'bg-cyan-500/10 border-cyan-500 text-white shadow-lg shadow-cyan-500/10'
                          : 'bg-[#0B1120] border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      <Plus className="h-5 w-5 mb-2 text-cyan-400" />
                      <div className="text-xs font-bold text-white">Create New Layout</div>
                      <div className="text-[10px] text-slate-400 mt-1">Draw fresh custom spatial boundaries</div>
                    </button>
                  </div>

                  {layoutMode === 'EXISTING' ? (
                    <div className="mt-6">
                      <div className="text-xs font-mono text-slate-400 mb-3 uppercase tracking-wider">
                        Available Spatial Layouts ({savedLayouts.length})
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {savedLayouts.map((l) => {
                          const isSel = selectedLayoutId === l.id;
                          return (
                            <div
                              key={l.id}
                              onClick={() => {
                                setSelectedLayoutId(l.id);
                                if (l.zones_data) {
                                  setCurrentZones(l.zones_data.map((z: any) => ({
                                    ...z,
                                    capacity: z.capacity ?? z.max_capacity ?? 100,
                                    polygon_points: (z.polygon_points || []).map(toObjPoint),
                                  })));
                                }
                              }}
                              className={`p-4 rounded-xl border cursor-pointer transition-all ${
                                isSel
                                  ? 'bg-[#0B1120] border-cyan-400 shadow-md shadow-cyan-500/10 ring-1 ring-cyan-400'
                                  : 'bg-[#0B1120] border-slate-800/80 hover:border-slate-700'
                              }`}
                            >
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-xs font-bold text-white truncate">{l.name}</span>
                                <div className="flex items-center space-x-1">
                                  {l.background_image_url ? (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-700/60">
                                      IMAGE
                                    </span>
                                  ) : (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-700/60">
                                      GRID
                                    </span>
                                  )}
                                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400">
                                    v{l.version || 1}
                                  </span>
                                </div>
                              </div>
                              <div className="text-[11px] text-slate-400 mb-3 line-clamp-2">
                                {l.description || 'Pre-configured surveillance layout'}
                              </div>
                              <div className="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800 pt-2">
                                <span>{l.zones_data?.length || 0} zones</span>
                                <span>{l.canvas_width}x{l.canvas_height}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="max-w-xl mx-auto space-y-3 mt-6">
                      <div>
                        <label className="block text-xs font-mono text-slate-300 mb-1">
                          New Layout Name <span className="text-cyan-400">*</span>
                        </label>
                        <input
                          type="text"
                          value={newLayoutName}
                          onChange={(e) => setNewLayoutName(e.target.value)}
                          placeholder="e.g., Festival West Concourse Layout"
                          className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-white text-xs focus:outline-none focus:border-cyan-500"
                        />
                      </div>
                      <p className="text-[11px] text-slate-400">
                        In the next step, you will use the Spatial Layout Builder to draw rectangle and polygon zones.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* STEP 3: Zone Configuration */}
              {currentStep === 3 && (
                <div className="h-[65vh] flex flex-col">
                  <div className="mb-2 text-xs text-slate-400 flex items-center justify-between">
                    <span>Draw or inspect zones. Minimum 1 zone required to proceed.</span>
                    <span className="font-mono text-cyan-400 font-bold">{currentZones.length} Zones Defined</span>
                  </div>
                  <div className="flex-1 rounded-xl overflow-hidden border border-slate-800">
                    <SpatialLayoutBuilder
                      layoutId={layoutMode === 'EXISTING' ? selectedLayoutId : undefined}
                      initialName={layoutMode === 'NEW' ? newLayoutName : 'Task Layout'}
                      initialZones={currentZones}
                      initialBackgroundImageUrl={layoutMode === 'EXISTING' ? (savedLayouts.find((l) => l.id === selectedLayoutId)?.background_image_url || null) : null}
                      onSaved={(layout) => {
                        if (layout.zones_data) {
                          setCurrentZones(layout.zones_data.map((z: any) => ({
                            ...z,
                            capacity: z.capacity ?? z.max_capacity ?? 100,
                            polygon_points: (z.polygon_points || []).map(toObjPoint),
                          })));
                        }
                      }}
                    />
                  </div>
                </div>
              )}

              {/* STEP 4: Video Configuration */}
              {currentStep === 4 && (
                <div className="max-w-xl mx-auto space-y-4">
                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-2">Video Feed Ingestion Source</label>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { id: 'FILE', label: 'Video File', icon: FileVideo, desc: 'MP4, AVI, MOV recording' },
                        { id: 'CCTV_STREAM', label: 'CCTV Stream', icon: Radio, desc: 'Live RTSP or HLS stream' },
                        { id: 'DRONE_RECORDING', label: 'Drone Footage', icon: Compass, desc: 'Overhead aerial feed' },
                      ].map((item) => {
                        const isSel = sourceType === item.id;
                        const Icon = item.icon;
                        return (
                          <div
                            key={item.id}
                            onClick={() => setSourceType(item.id as VideoSourceType)}
                            className={`p-3 rounded-xl border cursor-pointer transition-all ${
                              isSel
                                ? 'bg-cyan-500/10 border-cyan-400 text-white shadow-md'
                                : 'bg-[#0B1120] border-slate-800 text-slate-400 hover:text-white'
                            }`}
                          >
                            <Icon className="h-4 w-4 mb-1 text-cyan-400" />
                            <div className="text-xs font-bold text-white">{item.label}</div>
                            <div className="text-[10px] text-slate-400 mt-0.5">{item.desc}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {sourceType === 'FILE' && (
                    <div className="p-4 rounded-xl border border-dashed border-slate-700 bg-[#0B1120] text-center space-y-2">
                      <FileVideo className="h-8 w-8 mx-auto text-slate-500" />
                      <div className="text-xs text-slate-300 font-semibold">
                        {selectedFile ? selectedFile.name : 'Choose a video recording file'}
                      </div>
                      <div className="text-[10px] text-slate-500">Supported: MP4, AVI, MOV, MKV, WebM (Max 500MB)</div>
                      <label className="inline-block px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium cursor-pointer transition-colors">
                        Browse Files
                        <input
                          type="file"
                          accept="video/*"
                          onChange={(e) => {
                            if (e.target.files && e.target.files[0]) {
                              setSelectedFile(e.target.files[0]);
                            }
                          }}
                          className="hidden"
                        />
                      </label>
                    </div>
                  )}

                  {sourceType === 'CCTV_STREAM' && (
                    <div>
                      <label className="block text-xs font-mono text-slate-300 mb-1">RTSP / HLS Stream URI</label>
                      <input
                        type="text"
                        value={sourceUri}
                        onChange={(e) => setSourceUri(e.target.value)}
                        placeholder="rtsp://admin:pass@192.168.1.100:554/ch0/main"
                        className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-white text-xs font-mono focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  )}

                  {sourceType === 'DRONE_RECORDING' && (
                    <div>
                      <label className="block text-xs font-mono text-slate-300 mb-1">Drone Telemetry / Stream Reference</label>
                      <input
                        type="text"
                        value={sourceUri}
                        onChange={(e) => setSourceUri(e.target.value)}
                        placeholder="e.g., Drone Flight #04 — Sector B Overhead"
                        className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-white text-xs focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  )}

                  {/* Camera Perspective */}
                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1">Camera Perspective</label>
                    <select
                      value={cameraPerspective}
                      onChange={(e) => setCameraPerspective(e.target.value)}
                      className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl px-3.5 py-2 text-white text-xs focus:outline-none focus:border-cyan-500"
                    >
                      <option value="DRONE_TOPDOWN">Top-Down Orthogonal (Drone / Overhead Ceiling)</option>
                      <option value="FIXED_CCTV">Fixed CCTV (Angled Pole / Wall Mount)</option>
                      <option value="ELEVATED_OBLIQUE">Elevated Oblique (Stadium Grandstand)</option>
                    </select>
                  </div>

                  {/* Sampling Rate */}
                  <div>
                    <div className="flex justify-between text-xs font-mono text-slate-300 mb-1">
                      <span>Inference Sampling Rate</span>
                      <span className="text-cyan-400 font-bold">{sampleFps} FPS</span>
                    </div>
                    <input
                      type="range"
                      min="0.5"
                      max="5.0"
                      step="0.5"
                      value={sampleFps}
                      onChange={(e) => setSampleFps(parseFloat(e.target.value))}
                      className="w-full accent-cyan-500 cursor-pointer"
                    />
                    <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                      <span>0.5 FPS (Low Load)</span>
                      <span>2.0 FPS (Standard)</span>
                      <span>5.0 FPS (High Precision)</span>
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 5: Review */}
              {currentStep === 5 && (
                <div className="max-w-2xl mx-auto space-y-4">
                  <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-3">
                    <div className="text-xs font-mono text-cyan-400 uppercase tracking-wider font-bold">
                      Task Configuration Summary
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <span className="text-slate-500 block text-[10px] font-mono">TASK NAME</span>
                        <span className="font-bold text-white">{taskName}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] font-mono">LOCATION</span>
                        <span className="text-white">{location}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] font-mono">LAYOUT REFERENCE</span>
                        <span className="text-white">
                          {layoutMode === 'NEW' ? newLayoutName : (savedLayouts.find((l) => l.id === selectedLayoutId)?.name || 'Custom')}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] font-mono">ZONES IN SNAPSHOT</span>
                        <span className="text-cyan-400 font-bold">{currentZones.length} configured</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] font-mono">VIDEO SOURCE</span>
                        <span className="text-white">{sourceType} {selectedFile ? `(${selectedFile.name})` : ''}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] font-mono">PERSPECTIVE / FPS</span>
                        <span className="text-white">{cameraPerspective} @ {sampleFps} FPS</span>
                      </div>
                    </div>
                  </div>

                  {/* Configured Zones Preview Table */}
                  <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800">
                    <div className="text-xs font-mono text-slate-400 mb-2 uppercase">Configured Spatial Zones</div>
                    <div className="space-y-1.5 max-h-36 overflow-y-auto">
                      {currentZones.map((z) => (
                        <div key={z.id} className="p-2 rounded-lg bg-[#070B14] border border-slate-800 flex items-center justify-between text-xs">
                          <div className="flex items-center space-x-2">
                            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: z.color || '#06B6D4' }} />
                            <span className="font-medium text-white">{z.name}</span>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">{z.zone_type}</span>
                          </div>
                          <span className="text-[11px] font-mono text-cyan-400">{z.capacity} max capacity</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Initial Lifecycle State Choice */}
                  <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-bold text-white">Initial Lifecycle State</div>
                      <div className="text-[11px] text-slate-400">Choose whether to mark task READY or keep as DRAFT</div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        onClick={() => setInitialState('DRAFT')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                          initialState === 'DRAFT'
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50 font-bold'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        DRAFT
                      </button>
                      <button
                        type="button"
                        onClick={() => setInitialState('READY')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                          initialState === 'READY'
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50 font-bold'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        READY
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Wizard Footer Controls */}
        {!successTask && (
          <div className="h-16 border-t border-slate-800 px-6 flex items-center justify-between flex-shrink-0 bg-[#070B14]">
            <button
              onClick={handleBack}
              disabled={currentStep === 1 || isSubmitting}
              className="flex items-center space-x-1 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium disabled:opacity-30 disabled:pointer-events-none transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              <span>Back</span>
            </button>

            {currentStep < 5 ? (
              <button
                onClick={handleNext}
                className="flex items-center space-x-1 px-5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-bold shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
              >
                <span>Continue</span>
                <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleSaveTask}
                disabled={isSubmitting}
                className="flex items-center space-x-1.5 px-6 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-xs font-bold shadow-lg shadow-cyan-500/25 active:scale-95 transition-all"
              >
                <CheckCircle2 className="h-4 w-4" />
                <span>{isSubmitting ? 'Persisting Task...' : 'Save & Initialize Task'}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
