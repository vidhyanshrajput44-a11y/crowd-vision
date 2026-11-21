import React, { useState } from 'react';
import {
  Upload,
  Video,
  Layers,
  Camera,
  Play,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { Modal } from '../components/common/Modal';
import { Venue, PerspectiveType } from '../types';
import { api } from '../services/api';

interface CreateTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  venues: Venue[];
  onTaskCreated: (eventId: string, videoId?: string) => void;
}

export const CreateTaskModal: React.FC<CreateTaskModalProps> = ({
  isOpen,
  onClose,
  venues,
  onTaskCreated,
}) => {
  const [taskName, setTaskName] = useState('');
  const [eventType, setEventType] = useState('CONCERT');
  const [selectedVenueId, setSelectedVenueId] = useState(venues[0]?.id || '');
  const [newVenueName, setNewVenueName] = useState('');
  const [isCreatingVenue, setIsCreatingVenue] = useState(false);
  const [perspective, setPerspective] = useState<PerspectiveType>('drone_top_down');
  const [sampleFps, setSampleFps] = useState(2.0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [autoProcess, setAutoProcess] = useState(true);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);

  React.useEffect(() => {
    if (!selectedVenueId && venues.length > 0) {
      setSelectedVenueId(venues[0].id);
    }
  }, [venues, selectedVenueId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskName.trim()) {
      setErrorMsg('Task / Event name is required.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setUploadProgress('Initializing event and venue records...');

    try {
      let venueId = selectedVenueId;
      if (isCreatingVenue && newVenueName.trim()) {
        const v = await api.createVenue({
          name: newVenueName.trim(),
          venue_type: eventType,
          total_capacity: 5000,
        });
        venueId = v.id;
      } else if (!venueId) {
        if (venues.length > 0) {
          venueId = venues[0].id;
        } else {
          const v = await api.createVenue({
            name: `${taskName.trim()} Arena`,
            venue_type: eventType,
            total_capacity: 5000,
          });
          venueId = v.id;
        }
      }

      // 1. Create Event Record
      const event = await api.createEvent({
        name: taskName.trim(),
        event_type: eventType,
        venue_id: venueId || undefined,
        expected_attendance: 2000,
      });

      let videoId: string | undefined = undefined;

      // 2. Upload Video if provided
      if (selectedFile) {
        setUploadProgress('Uploading video stream (OpenCV & YOLO ingestion)...');
        const uploadRes = await api.uploadVideo(
          event.id,
          selectedFile,
          sampleFps,
          perspective,
          autoProcess
        );
        videoId = uploadRes.video_id;
      }

      setUploadProgress(null);
      onTaskCreated(event.id, videoId);
      onClose();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to create task and upload video.');
      setUploadProgress(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Crowd Monitoring Task"
      subtitle="Configure event boundaries, camera perspective, and ingest CCTV or drone footage."
      maxWidth="max-w-2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        {errorMsg && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Task Name & Event Type */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-slate-300 font-medium">Task / Event Name *</label>
            <input
              type="text"
              required
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              placeholder="e.g. Summer Music Festival - Main Arena"
              className="mt-1 w-full rounded-xl bg-[#070B14] border border-slate-700/80 px-3.5 py-2 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500 text-xs"
            />
          </div>

          <div>
            <label className="text-slate-300 font-medium">Event Type</label>
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              className="mt-1 w-full rounded-xl bg-[#070B14] border border-slate-700/80 px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500 text-xs"
            >
              <option value="CONCERT">Concert / Music Festival</option>
              <option value="COLLEGE_FEST">College Festival / Campus Gathering</option>
              <option value="STADIUM">Stadium / Sports Arena</option>
              <option value="RELIGIOUS">Religious Gathering / Pilgrimage</option>
              <option value="EXHIBITION">Exhibition / Trade Fair</option>
              <option value="PUBLIC_EVENT">Public Event / Parade</option>
              <option value="AIRPORT">Airport Terminal</option>
              <option value="RAILWAY_STATION">Railway / Transit Station</option>
            </select>
          </div>
        </div>

        {/* Venue Selection */}
        <div className="p-3 rounded-xl bg-[#070B14] border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-slate-300 font-medium">Venue Association</label>
            <button
              type="button"
              onClick={() => setIsCreatingVenue(!isCreatingVenue)}
              className="text-cyan-400 hover:text-cyan-300 text-[11px] font-mono"
            >
              {isCreatingVenue ? 'Select Existing Venue' : '+ Create New Venue'}
            </button>
          </div>

          {isCreatingVenue ? (
            <input
              type="text"
              value={newVenueName}
              onChange={(e) => setNewVenueName(e.target.value)}
              placeholder="Enter new venue name (e.g. Grand Amphitheater)"
              className="w-full rounded-lg bg-[#0B1120] border border-slate-700 px-3 py-1.5 text-white text-xs"
            />
          ) : (
            <select
              value={selectedVenueId}
              onChange={(e) => setSelectedVenueId(e.target.value)}
              className="w-full rounded-lg bg-[#0B1120] border border-slate-700 px-3 py-1.5 text-white text-xs"
            >
              {venues.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} ({v.venue_type})
                </option>
              ))}
              {venues.length === 0 && <option value="">No existing venues (will create default)</option>}
            </select>
          )}
        </div>

        {/* Perspective and Sampling */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-slate-300 font-medium flex items-center space-x-1.5">
              <Camera className="h-3.5 w-3.5 text-cyan-400" />
              <span>Camera Perspective</span>
            </label>
            <select
              value={perspective}
              onChange={(e) => setPerspective(e.target.value as PerspectiveType)}
              className="mt-1 w-full rounded-xl bg-[#070B14] border border-slate-700/80 px-3 py-2 text-white text-xs"
            >
              <option value="drone_top_down">Drone Top-Down (Orthogonal View)</option>
              <option value="elevated_cctv">Elevated CCTV (High Angle View)</option>
              <option value="ground_level">Ground Level (Frontal Perspective)</option>
              <option value="standard">Standard Angled</option>
            </select>
          </div>

          <div>
            <label className="text-slate-300 font-medium">Video Sample Rate (FPS)</label>
            <input
              type="number"
              min="0.5"
              max="15"
              step="0.5"
              value={sampleFps}
              onChange={(e) => setSampleFps(parseFloat(e.target.value) || 2.0)}
              className="mt-1 w-full rounded-xl bg-[#070B14] border border-slate-700/80 px-3.5 py-2 text-white font-mono text-xs"
            />
          </div>
        </div>

        {/* Video Upload Dropzone */}
        <div>
          <label className="text-slate-300 font-medium flex items-center space-x-1.5 mb-1">
            <Video className="h-3.5 w-3.5 text-cyan-400" />
            <span>Upload CCTV or Drone Video Footage (MP4 / AVI / MOV)</span>
          </label>
          <div className="border-2 border-dashed border-slate-700 hover:border-cyan-500/50 rounded-xl p-5 bg-[#070B14] text-center cursor-pointer transition-colors relative">
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
            />
            <Upload className="h-7 w-7 text-cyan-400 mx-auto mb-2 opacity-80" />
            {selectedFile ? (
              <div className="text-white font-mono font-medium">
                {selectedFile.name} ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)
              </div>
            ) : (
              <div>
                <p className="text-slate-300 font-medium">Drag and drop video footage here</p>
                <p className="text-slate-500 text-[11px] mt-0.5">Or click to browse video files from disk</p>
              </div>
            )}
          </div>
        </div>

        {/* Auto-process Toggle */}
        <div className="flex items-center space-x-2 pt-1">
          <input
            type="checkbox"
            id="autoProcess"
            checked={autoProcess}
            onChange={(e) => setAutoProcess(e.target.checked)}
            className="w-4 h-4 accent-cyan-500 rounded bg-slate-800"
          />
          <label htmlFor="autoProcess" className="text-slate-300 cursor-pointer">
            Automatically launch person detection & ByteTrack tracking upon upload
          </label>
        </div>

        {/* Submit Actions */}
        <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
          <div className="text-[11px] font-mono text-cyan-400">
            {uploadProgress}
          </div>

          <div className="flex items-center space-x-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold transition-all shadow-lg shadow-cyan-500/25 flex items-center space-x-2 disabled:opacity-50"
            >
              {isSubmitting ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              <span>{isSubmitting ? 'Processing...' : 'Create & Monitor Task'}</span>
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
};
