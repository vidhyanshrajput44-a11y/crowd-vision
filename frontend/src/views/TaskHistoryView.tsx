import React, { useState, useEffect } from 'react';
import {
  History,
  Clock,
  MapPin,
  CheckCircle2,
  Calendar,
  Layers,
  Filter,
  Search,
  ArrowRight,
} from 'lucide-react';
import { useTaskContext } from '../context/TaskContext';
import { TaskHistoryItem, TaskItem } from '../types';
import { api } from '../services/api';

export const TaskHistoryView: React.FC = () => {
  const { tasks, activeTask } = useTaskContext();
  const [selectedTaskId, setSelectedTaskId] = useState<string>(activeTask?.id || '');
  const [historyItems, setHistoryItems] = useState<TaskHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (activeTask && !selectedTaskId) {
      setSelectedTaskId(activeTask.id);
    }
  }, [activeTask, selectedTaskId]);

  useEffect(() => {
    if (!selectedTaskId) {
      setHistoryItems([]);
      return;
    }
    setIsLoading(true);
    api.getTaskHistory(selectedTaskId)
      .then(setHistoryItems)
      .catch(() => setHistoryItems([]))
      .finally(() => setIsLoading(false));
  }, [selectedTaskId]);

  const currentTask = tasks.find((t) => t.id === selectedTaskId);

  const filteredHistory = historyItems.filter((item) =>
    item.event_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
    JSON.stringify(item.details).toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-xl bg-[#0B1120] border border-slate-800 shadow-lg">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Monitoring & Task Audit History</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Immutable chronological record of task state transitions, layout attachments, and configuration events.
          </p>
        </div>

        {/* Task Selector */}
        <div className="flex items-center space-x-2">
          <span className="text-xs font-mono text-slate-400">Select Task:</span>
          <select
            value={selectedTaskId}
            onChange={(e) => setSelectedTaskId(e.target.value)}
            className="bg-[#070B14] border border-slate-700 text-white text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500"
          >
            {tasks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.state})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Task Context Card */}
      {currentTask && (
        <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold">
              ID
            </div>
            <div>
              <div className="text-white font-bold">{currentTask.name}</div>
              <div className="text-[10px] text-slate-500">ID: {currentTask.id} • Location: {currentTask.location}</div>
            </div>
          </div>

          <div className="flex items-center space-x-3 text-[11px]">
            <span className="px-2 py-0.5 rounded bg-slate-800 text-cyan-400 border border-slate-700">
              State: {currentTask.state}
            </span>
            <span className="text-slate-400">
              Created: {new Date(currentTask.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      )}

      {/* Filter / Search */}
      <div className="flex items-center space-x-2 bg-[#0B1120] border border-slate-800 rounded-xl px-3.5 py-2 text-xs">
        <Search className="h-3.5 w-3.5 text-slate-500" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Filter audit events by type or content..."
          className="bg-transparent text-white placeholder-slate-500 focus:outline-none w-full font-mono text-xs"
        />
      </div>

      {/* History Timeline */}
      <div className="rounded-xl border border-slate-800 bg-[#0B1120] p-6 shadow-xl space-y-4">
        {isLoading ? (
          <div className="p-8 text-center text-slate-500 font-mono text-xs">Loading audit trail...</div>
        ) : filteredHistory.length === 0 ? (
          <div className="p-8 text-center text-slate-500 font-sans text-xs">
            No audit records found for this task.
          </div>
        ) : (
          <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-slate-800">
            {filteredHistory.map((item) => (
              <div key={item.id} className="relative">
                {/* Timeline node */}
                <div className="absolute -left-[27px] top-1 w-3 h-3 rounded-full bg-cyan-500 ring-4 ring-[#0B1120]" />

                <div className="p-4 rounded-xl bg-[#070B14] border border-slate-800/80 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-bold text-cyan-400 font-mono tracking-wider">
                      {item.event_type}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500 flex items-center space-x-1">
                      <Clock className="h-3 w-3" />
                      <span>{new Date(item.timestamp).toLocaleString()}</span>
                    </span>
                  </div>

                  <pre className="text-[11px] font-mono text-slate-300 bg-[#0B1120] p-3 rounded-lg border border-slate-800 overflow-x-auto">
                    {JSON.stringify(item.details, null, 2)}
                  </pre>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
