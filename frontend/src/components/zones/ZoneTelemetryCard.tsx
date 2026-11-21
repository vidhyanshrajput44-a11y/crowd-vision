import React from 'react';
import {
  Users,
  ArrowDownRight,
  ArrowUpRight,
  Gauge,
  Compass,
  AlertOctagon,
  Shuffle,
} from 'lucide-react';
import { ZoneTelemetry } from '../../types';
import { RiskPill } from '../common/RiskPill';

interface ZoneTelemetryCardProps {
  telemetry: ZoneTelemetry;
  maxCapacity?: number;
  onClick?: () => void;
}

export const ZoneTelemetryCard: React.FC<ZoneTelemetryCardProps> = ({
  telemetry,
  maxCapacity = 100,
  onClick,
}) => {
  const utilPct = telemetry.capacity_utilization_pct !== undefined
    ? Math.round(telemetry.capacity_utilization_pct)
    : Math.round((telemetry.people_count / Math.max(maxCapacity, 1)) * 100);

  let barColor = 'bg-emerald-500';
  if (utilPct > 80) {
    barColor = 'bg-rose-500';
  } else if (utilPct > 60) {
    barColor = 'bg-amber-500';
  }

  return (
    <div
      onClick={onClick}
      className="rounded-xl border border-slate-800 bg-[#0B1120] p-4 shadow-lg hover:border-slate-700 transition-all cursor-pointer flex flex-col justify-between"
    >
      <div>
        {/* Header: Name and Risk Pill */}
        <div className="flex items-start justify-between">
          <div>
            <h4 className="text-sm font-semibold text-white tracking-tight">{telemetry.zone_name}</h4>
            <div className="text-[11px] font-mono text-slate-500">
              ID: {telemetry.zone_id.slice(0, 12)}
            </div>
          </div>
          <RiskPill level={telemetry.risk_level} size="sm" />
        </div>

        {/* Capacity Bar */}
        <div className="mt-3">
          <div className="flex justify-between text-xs font-mono mb-1">
            <span className="text-slate-400">Occupancy</span>
            <span className="text-white font-bold">
              {telemetry.people_count} / {maxCapacity} ({utilPct}%)
            </span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div
              className={`h-full ${barColor} transition-all duration-300`}
              style={{ width: `${Math.min(utilPct, 100)}%` }}
            />
          </div>
        </div>

        {/* Metrics Grid */}
        <div className="mt-4 grid grid-cols-2 gap-2 text-xs font-mono">
          <div className="rounded-lg bg-[#070B14] p-2 border border-slate-800/80">
            <div className="text-[10px] text-slate-500 flex items-center space-x-1">
              <Gauge className="h-3 w-3 text-cyan-400" />
              <span>DENSITY</span>
            </div>
            <div className="text-white font-bold text-sm mt-0.5">
              {telemetry.density_value.toFixed(2)} <span className="text-[10px] text-slate-400 font-normal">p/m²</span>
            </div>
          </div>

          <div className="rounded-lg bg-[#070B14] p-2 border border-slate-800/80">
            <div className="text-[10px] text-slate-500 flex items-center space-x-1">
              <Compass className="h-3 w-3 text-blue-400" />
              <span>FLOW NET</span>
            </div>
            <div
              className={`text-sm font-bold mt-0.5 ${
                telemetry.net_flow > 0 ? 'text-amber-400' : 'text-emerald-400'
              }`}
            >
              {telemetry.net_flow > 0 ? `+${telemetry.net_flow.toFixed(1)}` : telemetry.net_flow.toFixed(1)}{' '}
              <span className="text-[10px] text-slate-400 font-normal">p/s</span>
            </div>
          </div>
        </div>

        {/* Flow rates & movement */}
        <div className="mt-2.5 flex items-center justify-between text-[11px] font-mono text-slate-400 px-1">
          <span className="flex items-center space-x-1">
            <ArrowDownRight className="h-3 w-3 text-emerald-400" />
            <span>In: {telemetry.inflow_rate.toFixed(1)}/s</span>
          </span>
          <span className="flex items-center space-x-1">
            <ArrowUpRight className="h-3 w-3 text-rose-400" />
            <span>Out: {telemetry.outflow_rate.toFixed(1)}/s</span>
          </span>
          {telemetry.avg_speed !== undefined && (
            <span>Speed: {telemetry.avg_speed.toFixed(1)} m/s</span>
          )}
        </div>
      </div>

      {/* Safety Alert Flags */}
      {(telemetry.is_bottleneck || telemetry.is_counterflow) && (
        <div className="mt-3 pt-2 border-t border-slate-800/80 flex flex-wrap gap-1.5">
          {telemetry.is_bottleneck && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
              <AlertOctagon className="h-3 w-3 mr-1" />
              BOTTLENECK DETECTED
            </span>
          )}
          {telemetry.is_counterflow && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
              <Shuffle className="h-3 w-3 mr-1" />
              COUNTERFLOW
            </span>
          )}
        </div>
      )}
    </div>
  );
};
