import React, { useState } from 'react';
import {
  Layers,
  Search,
  PlusCircle,
  Video,
  FileSpreadsheet,
  ArrowRight,
  Calendar,
  CheckCircle,
} from 'lucide-react';
import { EventItem } from '../types';

interface TasksListViewProps {
  events: EventItem[];
  selectedEvent: EventItem | null;
  onSelectEvent: (event: EventItem) => void;
  onNavigateToMonitoring: () => void;
  onNavigateToReports: () => void;
  onOpenCreateTask: () => void;
}

export const TasksListView: React.FC<TasksListViewProps> = ({
  events,
  selectedEvent,
  onSelectEvent,
  onNavigateToMonitoring,
  onNavigateToReports,
  onOpenCreateTask,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  const filtered = events.filter((ev) => {
    const matchSearch =
      ev.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ev.event_type.toLowerCase().includes(searchQuery.toLowerCase());
    const matchStatus = statusFilter === 'ALL' || ev.status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-xl bg-[#0B1120] border border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Crowd Management Tasks</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            All configured monitoring venues, drone video analysis sessions, and events.
          </p>
        </div>

        <button
          onClick={onOpenCreateTask}
          className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
        >
          <PlusCircle className="h-4 w-4" />
          <span>Create New Task</span>
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
            placeholder="Search tasks, venues, types..."
            className="bg-transparent text-white placeholder-slate-500 focus:outline-none w-full text-xs"
          />
        </div>

        <div className="flex items-center space-x-2 font-mono">
          {['ALL', 'ACTIVE', 'COMPLETED', 'PAUSED'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1 rounded-md transition-colors ${
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
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#0B1120] shadow-lg">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-[#070B14] border-b border-slate-800 text-slate-400 uppercase text-[10px]">
            <tr>
              <th className="p-3.5">Task Name</th>
              <th className="p-3.5">Event Type</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5">Created Date</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {filtered.map((ev) => (
              <tr
                key={ev.id}
                onClick={() => onSelectEvent(ev)}
                className={`hover:bg-slate-800/40 transition-colors cursor-pointer ${
                  selectedEvent?.id === ev.id ? 'bg-cyan-500/5' : ''
                }`}
              >
                <td className="p-3.5">
                  <div className="font-semibold text-white text-sm font-sans">{ev.name}</div>
                  <div className="text-[10px] text-slate-500">ID: {ev.id}</div>
                </td>
                <td className="p-3.5">
                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px]">
                    {ev.event_type}
                  </span>
                </td>
                <td className="p-3.5">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] ${
                      ev.status === 'ACTIVE'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {ev.status}
                  </span>
                </td>
                <td className="p-3.5 text-slate-400">
                  {new Date(ev.created_at).toLocaleDateString()}
                </td>
                <td className="p-3.5 text-right space-x-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectEvent(ev);
                      onNavigateToMonitoring();
                    }}
                    className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-400 border border-cyan-500/30 transition-colors"
                  >
                    <Video className="h-3.5 w-3.5" />
                    <span>Monitor</span>
                  </button>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectEvent(ev);
                      onNavigateToReports();
                    }}
                    className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                  >
                    <FileSpreadsheet className="h-3.5 w-3.5" />
                    <span>Reports</span>
                  </button>
                </td>
              </tr>
            ))}

            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-slate-500">
                  No matching tasks found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
