import React from 'react';
import {
  Activity,
  Users,
  AlertTriangle,
  Layers,
  ArrowRight,
  TrendingUp,
  ShieldCheck,
  Video,
  PlusCircle,
} from 'lucide-react';
import { MetricCard } from '../components/common/MetricCard';
import { RiskPill } from '../components/common/RiskPill';
import { EventItem, AlertItem, EventZoneSummary } from '../types';

interface DashboardViewProps {
  events: EventItem[];
  selectedEvent: EventItem | null;
  onSelectEvent: (event: EventItem) => void;
  onNavigateToMonitoring: () => void;
  onOpenCreateTask: () => void;
  alerts: AlertItem[];
  zoneSummary: EventZoneSummary | null;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  events,
  selectedEvent,
  onSelectEvent,
  onNavigateToMonitoring,
  onOpenCreateTask,
  alerts,
  zoneSummary,
}) => {
  const activeAlerts = alerts.filter((a) => a.status === 'ACTIVE');
  const criticalCount = activeAlerts.filter((a) => a.severity === 'CRITICAL').length;
  const totalMonitoredPeople = zoneSummary?.total_people || 0;

  return (
    <div className="space-y-6">
      {/* Top Banner & Quick Action */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-r from-[#0B1120] via-[#0D1527] to-[#070B14] p-6 shadow-2xl">
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-4">
          <div className="max-w-2xl">
            <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono mb-3">
              <Activity className="h-3.5 w-3.5 animate-pulse" />
              <span>Real-Time Predictive Crowd Monitoring Platform</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Operational Command & Spatial Intelligence
            </h1>
            <p className="mt-1 text-xs text-slate-400 leading-relaxed">
              Continuous person tracking with ByteTrack, advection-diffusion density predictions,
              and autonomous risk interpretation.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={onOpenCreateTask}
              className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-lg shadow-cyan-500/25 active:scale-95 transition-all"
            >
              <PlusCircle className="h-4 w-4" />
              <span>Create New Task</span>
            </button>

            {selectedEvent && (
              <button
                onClick={onNavigateToMonitoring}
                className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-medium text-xs transition-colors"
              >
                <Video className="h-4 w-4 text-cyan-400" />
                <span>Open Live Stream</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Ambient background decoration */}
        <div className="absolute right-0 top-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Monitored Population"
          value={totalMonitoredPeople.toLocaleString()}
          subtitle="Real-time detected persons across active zones"
          icon={Users}
          color="cyan"
          trend={{ value: 'Synchronized', isPositive: true }}
        />

        <MetricCard
          title="Critical Alerts"
          value={criticalCount}
          subtitle="Zones requiring immediate crowd distribution"
          icon={AlertTriangle}
          color={criticalCount > 0 ? 'rose' : 'emerald'}
          trend={{ value: `${activeAlerts.length} total active`, isNeutral: true }}
        />

        <MetricCard
          title="Monitored Zones"
          value={zoneSummary?.zones?.length || 0}
          subtitle="Active spatial polygon partitions"
          icon={Layers}
          color="blue"
        />

        <MetricCard
          title="Predictive Horizons"
          value="+30s / +1m / +3m / +5m"
          subtitle="Physics-informed density projections"
          icon={TrendingUp}
          color="amber"
        />
      </div>

      {/* Main Dashboard Grid: Active Tasks + Live Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Tasks Column */}
        <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-[#0B1120] p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
              <Layers className="h-4 w-4 text-cyan-400" />
              <span>Configured Crowd Intelligence Tasks</span>
            </h3>
            <span className="text-xs font-mono text-slate-400">{events.length} Tasks Active</span>
          </div>

          <div className="space-y-2.5">
            {events.map((ev) => {
              const isSelected = selectedEvent?.id === ev.id;
              return (
                <div
                  key={ev.id}
                  onClick={() => onSelectEvent(ev)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer flex items-center justify-between ${
                    isSelected
                      ? 'bg-cyan-500/10 border-cyan-500/30 shadow-md shadow-cyan-500/5'
                      : 'bg-[#070B14] border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-white text-sm">{ev.name}</span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                        {ev.event_type}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 font-mono mt-1">
                      Event ID: {ev.id.slice(0, 16)}... | Created: {new Date(ev.created_at).toLocaleDateString()}
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                        ev.status === 'ACTIVE'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {ev.status}
                    </span>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectEvent(ev);
                        onNavigateToMonitoring();
                      }}
                      className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-400 transition-colors"
                      title="Launch Video Workspace"
                    >
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}

            {events.length === 0 && (
              <div className="py-12 text-center text-slate-500 text-xs font-mono">
                No tasks created yet. Click "Create New Task" above to begin.
              </div>
            )}
          </div>
        </div>

        {/* Live Safety Alerts Column */}
        <div className="rounded-xl border border-slate-800 bg-[#0B1120] p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
              <AlertTriangle className="h-4 w-4 text-rose-400" />
              <span>Real-Time Alerts</span>
            </h3>
            <span className="text-xs font-mono text-rose-400 font-bold">{activeAlerts.length} Active</span>
          </div>

          <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
            {activeAlerts.slice(0, 6).map((alert) => (
              <div
                key={alert.id}
                className="p-3 rounded-lg bg-[#070B14] border border-slate-800 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <span className="text-xs font-semibold text-white">{alert.title}</span>
                  <RiskPill level={alert.severity} size="sm" />
                </div>
                <div className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                  {alert.description}
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-2 flex justify-between">
                  <span>Zone: {alert.zone_name || alert.zone_id}</span>
                  <span>{new Date(alert.created_at).toLocaleTimeString()}</span>
                </div>
              </div>
            ))}

            {activeAlerts.length === 0 && (
              <div className="py-12 text-center text-slate-500 text-xs font-mono flex flex-col items-center">
                <ShieldCheck className="h-8 w-8 text-emerald-400 mb-2 opacity-80" />
                <span>All zones nominal. No active safety violations.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
