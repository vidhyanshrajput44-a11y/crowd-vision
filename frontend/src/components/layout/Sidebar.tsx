import React from 'react';
import {
  LayoutDashboard,
  Video,
  Layers,
  Compass,
  Square,
  Bot,
  AlertTriangle,
  History,
  FileSpreadsheet,
  Settings,
  PlusCircle,
  Activity,
  ShieldCheck,
} from 'lucide-react';

export type NavTab =
  | 'monitoring'
  | 'tasks'
  | 'layouts'
  | 'layout-builder'
  | 'copilot'
  | 'alerts'
  | 'history'
  | 'reports'
  | 'settings';

interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onOpenCreateTask: () => void;
  alertCount?: number;
  agentStatus?: 'connected' | 'offline' | 'checking';
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  onOpenCreateTask,
  alertCount = 0,
  agentStatus = 'connected',
}) => {
  const navItems: { id: NavTab; label: string; icon: React.FC<{ className?: string }>; badge?: number }[] = [
    { id: 'monitoring', label: 'Monitoring Console', icon: Video },
    { id: 'tasks', label: 'Tasks Management', icon: Layers },
    { id: 'layouts', label: 'Spatial Layouts', icon: Compass },
    { id: 'layout-builder', label: 'Layout Builder', icon: Square },
    { id: 'copilot', label: 'AI Copilot', icon: Bot },
    { id: 'alerts', label: 'Alerts Center', icon: AlertTriangle, badge: alertCount },
    { id: 'history', label: 'Audit History', icon: History },
    { id: 'reports', label: 'Reports', icon: FileSpreadsheet },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 flex-shrink-0 border-r border-slate-800/80 bg-[#070B14] flex flex-col justify-between select-none">
      <div>
        {/* Brand Header */}
        <div className="h-16 flex items-center px-6 border-b border-slate-800/80">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Activity className="h-5 w-5 text-white animate-pulse" />
            </div>
            <div>
              <div className="text-base font-bold text-white tracking-wider font-mono">
                CROWD<span className="text-cyan-400">VISION</span>
              </div>
              <div className="text-[10px] text-cyan-500/80 font-mono tracking-widest uppercase">
                Spatial Intelligence
              </div>
            </div>
          </div>
        </div>

        {/* Primary Action Button */}
        <div className="p-4">
          <button
            onClick={onOpenCreateTask}
            className="w-full flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-medium text-sm shadow-lg shadow-cyan-500/25 hover:from-cyan-400 hover:to-blue-500 transition-all duration-200 active:scale-[0.98]"
          >
            <PlusCircle className="h-4 w-4" />
            <span>Create New Task</span>
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="px-3 space-y-1 mt-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <Icon className={`h-4 w-4 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* System Status Footer */}
      <div className="p-4 border-t border-slate-800/80 space-y-3">
        <div className="rounded-xl border border-slate-800 bg-[#0B1120]/80 p-3 text-xs">
          <div className="flex items-center justify-between text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-cyan-400" />
              <span>AI Agent Subsystem</span>
            </span>
            <span
              className={`w-2 h-2 rounded-full ${
                agentStatus === 'connected'
                  ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50'
                  : 'bg-amber-400'
              }`}
            />
          </div>
          <div className="flex justify-between items-center text-[11px] font-mono">
            <span className="text-slate-500">Autonomous Port</span>
            <span className="text-cyan-400 font-semibold">:8100</span>
          </div>
        </div>

        <div className="text-[11px] text-slate-500 text-center font-mono">
          CrowdVision v2.4 Enterprise
        </div>
      </div>
    </aside>
  );
};
