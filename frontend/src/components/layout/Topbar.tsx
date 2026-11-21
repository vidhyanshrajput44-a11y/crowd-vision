import React, { useState, useRef, useEffect } from 'react';
import {
  Calendar,
  ChevronDown,
  Wifi,
  Bell,
  User as UserIcon,
  RefreshCw,
  PlusCircle,
  Layers,
  MapPin,
  Check,
  Search,
  ExternalLink,
} from 'lucide-react';
import { useTaskContext } from '../../context/TaskContext';
import { User } from '../../types';

interface TopbarProps {
  currentUser: User | null;
  activeAlertCount?: number;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onOpenCreateTask: () => void;
  onNavigateToTasks: () => void;
}

export const Topbar: React.FC<TopbarProps> = ({
  currentUser,
  activeAlertCount = 0,
  onRefresh,
  isRefreshing = false,
  onOpenCreateTask,
  onNavigateToTasks,
}) => {
  const { tasks, activeTask, selectTask } = useTaskContext();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [taskSearch, setTaskSearch] = useState('');
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const filteredTasks = tasks.filter(
    (t) =>
      t.name.toLowerCase().includes(taskSearch.toLowerCase()) ||
      (t.location && t.location.toLowerCase().includes(taskSearch.toLowerCase()))
  );

  return (
    <header className="h-16 border-b border-slate-800/80 bg-[#070B14]/90 backdrop-blur-md px-6 flex items-center justify-between z-30 select-none">
      {/* Active Task Selector / Switcher */}
      <div className="flex items-center space-x-4">
        <div className="relative" ref={dropdownRef}>
          <div className="flex items-center space-x-2 text-[10px] font-mono text-slate-400 uppercase tracking-wider mb-0.5">
            <Calendar className="h-3 w-3 text-cyan-400" />
            <span>Active Monitoring Task</span>
          </div>

          <button
            type="button"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center space-x-2.5 bg-[#0B1120] hover:bg-slate-800/80 border border-slate-700/80 text-white text-xs font-semibold rounded-lg pl-3 pr-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-colors shadow-sm"
          >
            {activeTask ? (
              <>
                <span className="truncate max-w-[200px]">{activeTask.name}</span>
                <span
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono uppercase ${
                    activeTask.state === 'READY'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : activeTask.state === 'PROCESSING' || activeTask.state === 'LIVE'
                      ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
                      : activeTask.state === 'PAUSED'
                      ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  {activeTask.state}
                </span>
              </>
            ) : (
              <span className="text-slate-500">No active task</span>
            )}
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </button>

          {/* Switcher Dropdown Menu */}
          {dropdownOpen && (
            <div className="absolute left-0 mt-1.5 w-80 rounded-xl bg-[#0B1120] border border-slate-800 shadow-2xl overflow-hidden z-50 animate-fade-in text-xs">
              {/* Search input in switcher */}
              <div className="p-2.5 border-b border-slate-800 bg-[#070B14]">
                <div className="flex items-center space-x-2 bg-[#0B1120] border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs">
                  <Search className="h-3 w-3 text-slate-500" />
                  <input
                    type="text"
                    value={taskSearch}
                    onChange={(e) => setTaskSearch(e.target.value)}
                    placeholder="Search tasks..."
                    className="bg-transparent text-white placeholder-slate-500 focus:outline-none w-full text-xs font-mono"
                    autoFocus
                  />
                </div>
              </div>

              {/* Tasks List */}
              <div className="max-h-56 overflow-y-auto divide-y divide-slate-800/60">
                {filteredTasks.length === 0 ? (
                  <div className="p-4 text-center text-slate-500 text-xs font-mono">
                    No matching tasks
                  </div>
                ) : (
                  filteredTasks.map((t) => {
                    const isSelected = activeTask?.id === t.id;
                    return (
                      <div
                        key={t.id}
                        onClick={() => {
                          selectTask(t.id);
                          setDropdownOpen(false);
                        }}
                        className={`p-2.5 cursor-pointer flex items-center justify-between transition-colors ${
                          isSelected ? 'bg-cyan-950/40 text-white' : 'hover:bg-slate-800/50 text-slate-300'
                        }`}
                      >
                        <div className="truncate mr-2">
                          <div className="font-bold truncate text-xs">{t.name}</div>
                          <div className="text-[10px] text-slate-500 flex items-center space-x-1 truncate mt-0.5">
                            <MapPin className="h-2.5 w-2.5 flex-shrink-0" />
                            <span className="truncate">{t.location || 'Site Location'}</span>
                          </div>
                        </div>

                        <div className="flex items-center space-x-2 flex-shrink-0">
                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 uppercase">
                            {t.state}
                          </span>
                          {isSelected && <Check className="h-3.5 w-3.5 text-cyan-400" />}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Quick Actions Footer */}
              <div className="p-2 border-t border-slate-800 bg-[#070B14] flex items-center justify-between">
                <button
                  onClick={() => {
                    setDropdownOpen(false);
                    onOpenCreateTask();
                  }}
                  className="flex items-center space-x-1 text-cyan-400 hover:text-cyan-300 font-bold text-[11px] px-2 py-1"
                >
                  <PlusCircle className="h-3 w-3" />
                  <span>New Task</span>
                </button>

                <button
                  onClick={() => {
                    setDropdownOpen(false);
                    onNavigateToTasks();
                  }}
                  className="flex items-center space-x-1 text-slate-400 hover:text-white text-[11px] px-2 py-1"
                >
                  <span>All Tasks</span>
                  <ExternalLink className="h-3 w-3" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center space-x-3">
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
            title="Refresh Application State"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        )}

        {/* Live Network Stream Status */}
        <div className="hidden md:flex items-center space-x-2 px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono">
          <Wifi className="h-3.5 w-3.5 animate-pulse" />
          <span>CROWD VISION CORE</span>
        </div>

        {/* User Profile */}
        <div className="flex items-center space-x-3 pl-3 border-l border-slate-800">
          <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <UserIcon className="h-4 w-4" />
          </div>
          <div className="hidden lg:block text-left">
            <div className="text-xs font-semibold text-white">
              {currentUser?.full_name || 'System Operator'}
            </div>
            <div className="text-[10px] font-mono text-cyan-400">
              {currentUser?.role || 'OPERATOR'}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
