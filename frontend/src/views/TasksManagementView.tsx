import React, { useState } from 'react';
import {
  Layers,
  Search,
  PlusCircle,
  Video,
  Play,
  Pause,
  Square,
  Edit2,
  Copy,
  Trash2,
  Clock,
  MapPin,
  CheckCircle,
  AlertTriangle,
  History,
  X,
  ArrowRight,
  Filter,
} from 'lucide-react';
import { useTaskContext } from '../context/TaskContext';
import { TaskItem, TaskHistoryItem } from '../types';
import { api } from '../services/api';

interface TasksManagementViewProps {
  onOpenCreateTask: () => void;
  onNavigateToMonitoring: () => void;
}

export const TasksManagementView: React.FC<TasksManagementViewProps> = ({
  onOpenCreateTask,
  onNavigateToMonitoring,
}) => {
  const {
    tasks,
    activeTask,
    selectTask,
    updateTask,
    duplicateTask,
    deleteTask,
    changeTaskState,
  } = useTaskContext();

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Edit Task Modal State
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null);
  const [editName, setEditName] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editNotes, setEditNotes] = useState('');

  // History Modal State
  const [historyTask, setHistoryTask] = useState<TaskItem | null>(null);
  const [historyItems, setHistoryItems] = useState<TaskHistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Delete Confirmation State
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);

  // Filter tasks
  const filteredTasks = tasks.filter((t) => {
    const matchSearch =
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (t.location && t.location.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (t.description && t.description.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchStatus = statusFilter === 'ALL' || t.state === statusFilter;
    return matchSearch && matchStatus;
  });

  const handleOpenEdit = (task: TaskItem) => {
    setEditingTask(task);
    setEditName(task.name);
    setEditLocation(task.location || '');
    setEditDescription(task.description || '');
    setEditNotes(task.notes || '');
  };

  const handleSaveEdit = async () => {
    if (!editingTask || !editName.trim()) return;
    try {
      await updateTask(editingTask.id, {
        name: editName.trim(),
        location: editLocation.trim(),
        description: editDescription.trim(),
        notes: editNotes.trim(),
      });
      setEditingTask(null);
    } catch {
      // handled in context
    }
  };

  const handleOpenHistory = async (task: TaskItem) => {
    setHistoryTask(task);
    setLoadingHistory(true);
    try {
      const items = await api.getTaskHistory(task.id);
      setHistoryItems(items);
    } catch {
      setHistoryItems([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingTaskId) return;
    try {
      await deleteTask(deletingTaskId);
      setDeletingTaskId(null);
    } catch {
      // handled
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-xl bg-[#0B1120] border border-slate-800 shadow-lg">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Crowd Vision Tasks Management</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Manage surveillance sessions, spatial layout snapshots, and video ingestion lifecycles.
          </p>
        </div>

        <button
          onClick={onOpenCreateTask}
          className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-lg shadow-cyan-500/25 active:scale-95 transition-all"
        >
          <PlusCircle className="h-4 w-4" />
          <span>New Monitoring Task</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-[#0B1120] border border-slate-800 text-xs">
        <div className="flex items-center space-x-2 bg-[#070B14] border border-slate-700/80 rounded-lg px-3 py-1.5 w-72">
          <Search className="h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tasks, locations, notes..."
            className="bg-transparent text-white placeholder-slate-500 focus:outline-none w-full text-xs font-mono"
          />
        </div>

        <div className="flex items-center space-x-1 font-mono overflow-x-auto">
          {['ALL', 'DRAFT', 'CONFIGURING', 'READY', 'PROCESSING', 'LIVE', 'PAUSED', 'COMPLETED'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                statusFilter === st
                  ? 'bg-slate-800 text-cyan-400 font-bold border border-slate-700'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Tasks Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#0B1120] shadow-xl">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-[#070B14] border-b border-slate-800 text-slate-400 uppercase text-[10px]">
            <tr>
              <th className="p-3.5">Task Name & Location</th>
              <th className="p-3.5">Lifecycle State</th>
              <th className="p-3.5">Layout & Zones</th>
              <th className="p-3.5">Video Source</th>
              <th className="p-3.5">Created Date</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filteredTasks.length === 0 && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500 font-sans">
                  No matching tasks found. Click "New Monitoring Task" to create one.
                </td>
              </tr>
            )}
            {filteredTasks.map((task) => {
              const isActive = activeTask?.id === task.id;
              const zonesCount = task.layout_snapshot?.zones_data?.length || 0;

              return (
                <tr
                  key={task.id}
                  className={`hover:bg-slate-800/40 transition-colors ${
                    isActive ? 'bg-cyan-950/20' : ''
                  }`}
                >
                  <td className="p-3.5">
                    <div className="flex items-center space-x-2">
                      {isActive && (
                        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse flex-shrink-0" />
                      )}
                      <div>
                        <div className="font-bold text-white text-xs">{task.name}</div>
                        <div className="text-[10px] text-slate-400 flex items-center space-x-1 mt-0.5 font-sans">
                          <MapPin className="h-3 w-3 text-slate-500" />
                          <span>{task.location || 'Location Not Specified'}</span>
                        </div>
                      </div>
                    </div>
                  </td>

                  <td className="p-3.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase inline-block ${
                        task.state === 'READY'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : task.state === 'LIVE' || task.state === 'PROCESSING'
                          ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 animate-pulse'
                          : task.state === 'PAUSED'
                          ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                          : 'bg-slate-800 text-slate-400 border border-slate-700'
                      }`}
                    >
                      {task.state}
                    </span>
                  </td>

                  <td className="p-3.5">
                    <div className="text-white text-xs">
                      {task.layout_snapshot?.name || 'Custom Layout'}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {zonesCount} spatial zones
                    </div>
                  </td>

                  <td className="p-3.5 text-slate-300">
                    <div className="text-xs uppercase">{task.video_config?.source_type || 'FILE'}</div>
                    <div className="text-[10px] text-slate-500">
                      {task.video_config?.camera_perspective || 'DRONE_TOPDOWN'}
                    </div>
                  </td>

                  <td className="p-3.5 text-slate-400 text-[11px]">
                    {new Date(task.created_at).toLocaleDateString()}
                  </td>

                  <td className="p-3.5 text-right">
                    <div className="flex items-center justify-end space-x-1.5">
                      {/* Select & Switch */}
                      <button
                        onClick={async () => {
                          await selectTask(task.id);
                          onNavigateToMonitoring();
                        }}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-400 text-[11px] font-bold transition-colors flex items-center space-x-1"
                        title="Open in Monitoring Workspace"
                      >
                        <Video className="h-3 w-3" />
                        <span>Monitor</span>
                      </button>

                      {/* State transition toggles */}
                      {task.state === 'READY' && (
                        <button
                          onClick={() => changeTaskState(task.id, 'PROCESSING', 'Started from tasks management')}
                          className="p-1.5 rounded bg-emerald-950/60 border border-emerald-500/30 hover:bg-emerald-900/60 text-emerald-400"
                          title="Start Inference"
                        >
                          <Play className="h-3.5 w-3.5 fill-current" />
                        </button>
                      )}

                      {task.state === 'PROCESSING' && (
                        <button
                          onClick={() => changeTaskState(task.id, 'PAUSED', 'Paused from tasks management')}
                          className="p-1.5 rounded bg-amber-950/60 border border-amber-500/30 hover:bg-amber-900/60 text-amber-400"
                          title="Pause Inference"
                        >
                          <Pause className="h-3.5 w-3.5" />
                        </button>
                      )}

                      {task.state === 'PAUSED' && (
                        <button
                          onClick={() => changeTaskState(task.id, 'PROCESSING', 'Resumed from tasks management')}
                          className="p-1.5 rounded bg-cyan-950/60 border border-cyan-500/30 hover:bg-cyan-900/60 text-cyan-400"
                          title="Resume Inference"
                        >
                          <Play className="h-3.5 w-3.5 fill-current" />
                        </button>
                      )}

                      {/* Edit */}
                      <button
                        onClick={() => handleOpenEdit(task)}
                        className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                        title="Edit Task Details"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </button>

                      {/* Duplicate */}
                      <button
                        onClick={() => duplicateTask(task.id)}
                        className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                        title="Duplicate Task"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </button>

                      {/* Audit History */}
                      <button
                        onClick={() => handleOpenHistory(task)}
                        className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                        title="View Task Audit Trail"
                      >
                        <History className="h-3.5 w-3.5" />
                      </button>

                      {/* Delete */}
                      <button
                        onClick={() => setDeletingTaskId(task.id)}
                        className="p-1.5 rounded hover:bg-red-950/50 text-slate-500 hover:text-red-400 transition-colors"
                        title="Delete Task"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Edit Task Modal */}
      {editingTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg bg-[#0B1120] border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white">Edit Task Configuration</h3>
              <button
                onClick={() => setEditingTask(null)}
                className="p-1 text-slate-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 font-mono mb-1">Task Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-[#070B14] border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 font-mono mb-1">Location</label>
                <input
                  type="text"
                  value={editLocation}
                  onChange={(e) => setEditLocation(e.target.value)}
                  className="w-full bg-[#070B14] border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 font-mono mb-1">Description</label>
                <textarea
                  rows={2}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="w-full bg-[#070B14] border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 font-mono mb-1">Operational Notes</label>
                <textarea
                  rows={2}
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                  className="w-full bg-[#070B14] border border-slate-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setEditingTask(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs shadow-md shadow-cyan-500/20"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Task Audit History Modal */}
      {historyTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-xl bg-[#0B1120] border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-shrink-0">
              <div className="flex items-center space-x-2">
                <History className="h-4 w-4 text-cyan-400" />
                <h3 className="text-sm font-bold text-white">
                  Audit History: {historyTask.name}
                </h3>
              </div>
              <button
                onClick={() => setHistoryTask(null)}
                className="p-1 text-slate-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs font-mono">
              {loadingHistory ? (
                <div className="p-8 text-center text-slate-500">Loading audit trail...</div>
              ) : historyItems.length === 0 ? (
                <div className="p-8 text-center text-slate-500">No events recorded for this task yet.</div>
              ) : (
                historyItems.map((h) => (
                  <div
                    key={h.id}
                    className="p-3 rounded-xl bg-[#070B14] border border-slate-800 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-cyan-400 uppercase text-[11px]">{h.event_type}</span>
                      <span className="text-[10px] text-slate-500">
                        {new Date(h.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <pre className="text-[11px] text-slate-400 whitespace-pre-wrap font-mono">
                      {JSON.stringify(h.details, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </div>

            <div className="pt-2 border-t border-slate-800 flex justify-end flex-shrink-0">
              <button
                onClick={() => setHistoryTask(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingTaskId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-sm bg-[#0B1120] border border-red-500/40 rounded-2xl p-6 shadow-2xl space-y-4 text-center">
            <div className="w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 flex items-center justify-center mx-auto">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <h3 className="text-sm font-bold text-white">Permanently Delete Task?</h3>
            <p className="text-xs text-slate-400">
              This will remove the task, its layout snapshot reference, and all audit logs. This action cannot be undone.
            </p>
            <div className="flex items-center justify-center space-x-3 pt-2">
              <button
                onClick={() => setDeletingTaskId(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white font-bold text-xs shadow-md shadow-red-500/20"
              >
                Yes, Delete Task
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
