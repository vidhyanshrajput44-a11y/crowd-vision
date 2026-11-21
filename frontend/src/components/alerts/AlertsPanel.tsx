import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Filter,
  Check,
  ShieldCheck,
  ChevronRight,
} from 'lucide-react';
import { AlertItem, AlertSeverity } from '../../types';
import { RiskPill } from '../common/RiskPill';
import { api } from '../../services/api';

interface AlertsPanelProps {
  alerts: AlertItem[];
  onAlertUpdated?: () => void;
}

export const AlertsPanel: React.FC<AlertsPanelProps> = ({
  alerts,
  onAlertUpdated,
}) => {
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const handleStatusChange = async (alertId: string, status: 'ACKNOWLEDGED' | 'RESOLVED') => {
    setUpdatingId(alertId);
    try {
      await api.updateAlertStatus(alertId, status);
      if (onAlertUpdated) onAlertUpdated();
    } catch {
      // ignore
    } finally {
      setUpdatingId(null);
    }
  };

  const filtered = alerts.filter((a) => {
    if (filterSeverity === 'ALL') return true;
    return a.severity.toUpperCase() === filterSeverity.toUpperCase();
  });

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0B1120] p-5 shadow-lg flex flex-col space-y-4">
      {/* Header and Filter */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <h3 className="text-base font-semibold text-white flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-rose-400" />
            <span>Alerts & Incident Log</span>
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time threshold and predictive anomaly detections.
          </p>
        </div>

        {/* Severity Filter Pills */}
        <div className="flex items-center space-x-1.5 p-1 rounded-lg bg-[#070B14] border border-slate-800 text-xs font-mono">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM'].map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`px-2.5 py-1 rounded-md transition-all ${
                filterSeverity === sev
                  ? 'bg-slate-800 text-cyan-400 font-bold border border-slate-700'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Alerts Feed */}
      {filtered.length === 0 ? (
        <div className="py-12 text-center text-slate-500 text-xs font-mono flex flex-col items-center">
          <ShieldCheck className="h-8 w-8 text-emerald-400 mb-2 opacity-80" />
          <span>No active alerts matching criteria. All zones operating within safety bounds.</span>
        </div>
      ) : (
        <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
          {filtered.map((alert) => (
            <div
              key={alert.id}
              className={`p-4 rounded-xl border transition-all ${
                alert.status === 'ACTIVE'
                  ? 'bg-[#070B14] border-slate-800 hover:border-slate-700'
                  : 'bg-slate-900/40 border-slate-800/40 opacity-70'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-3">
                  <RiskPill level={alert.severity} size="sm" />
                  <div>
                    <h4 className="text-sm font-semibold text-white">{alert.title}</h4>
                    <div className="text-xs text-slate-400 mt-1">{alert.description}</div>
                  </div>
                </div>

                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                    alert.status === 'ACTIVE'
                      ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                      : alert.status === 'ACKNOWLEDGED'
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  }`}
                >
                  {alert.status}
                </span>
              </div>

              {/* Supporting Measurements & Time */}
              <div className="mt-3 pt-2.5 border-t border-slate-800/60 flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 gap-2">
                <div className="flex items-center space-x-3">
                  <span>Zone: <strong className="text-slate-300">{alert.zone_name || alert.zone_id}</strong></span>
                  {alert.video_timestamp_sec !== undefined && (
                    <span>Timestamp: <strong>{alert.video_timestamp_sec.toFixed(1)}s</strong></span>
                  )}
                  {alert.supporting_measurements && Object.keys(alert.supporting_measurements).length > 0 && (
                    <span className="text-slate-500 hidden sm:inline">
                      Data: {JSON.stringify(alert.supporting_measurements).slice(0, 40)}...
                    </span>
                  )}
                </div>

                {/* Action Buttons */}
                {alert.status !== 'RESOLVED' && (
                  <div className="flex items-center space-x-2">
                    {alert.status === 'ACTIVE' && (
                      <button
                        onClick={() => handleStatusChange(alert.id, 'ACKNOWLEDGED')}
                        disabled={updatingId === alert.id}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-sans transition-colors"
                      >
                        Acknowledge
                      </button>
                    )}
                    <button
                      onClick={() => handleStatusChange(alert.id, 'RESOLVED')}
                      disabled={updatingId === alert.id}
                      className="px-2.5 py-1 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 text-xs font-sans transition-colors flex items-center space-x-1"
                    >
                      <Check className="h-3 w-3" />
                      <span>Resolve</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
