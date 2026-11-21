import React, { useState } from 'react';
import {
  TrendingUp,
  Clock,
  Flame,
  ShieldAlert,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react';
import { PredictionItem, RiskLevel } from '../../types';
import { RiskPill } from '../common/RiskPill';

interface PredictionViewerProps {
  predictions: PredictionItem[];
  onSelectHorizon?: (horizonSeconds: number) => void;
  selectedHorizon?: number;
}

const HORIZONS = [
  { label: '+30s', seconds: 30 },
  { label: '+1 min', seconds: 60 },
  { label: '+3 min', seconds: 180 },
  { label: '+5 min', seconds: 300 },
];

export const PredictionViewer: React.FC<PredictionViewerProps> = ({
  predictions,
  onSelectHorizon,
  selectedHorizon = 60,
}) => {
  const [activeHorizon, setActiveHorizon] = useState<number>(selectedHorizon);

  const handleHorizonChange = (hz: number) => {
    setActiveHorizon(hz);
    if (onSelectHorizon) onSelectHorizon(hz);
  };

  const filteredPredictions = predictions.filter(
    (p) => p.horizon_seconds === activeHorizon || (activeHorizon === 60 && !p.horizon_seconds)
  );

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0B1120] p-5 shadow-lg flex flex-col space-y-4">
      {/* Header and Horizon Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <h3 className="text-base font-semibold text-white flex items-center space-x-2">
            <TrendingUp className="h-4 w-4 text-cyan-400" />
            <span>Predictive Spatial Intelligence</span>
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Physics-informed advection-diffusion density forecast and occupancy trends.
          </p>
        </div>

        {/* Horizon Tabs */}
        <div className="flex items-center space-x-1.5 p-1 rounded-lg bg-[#070B14] border border-slate-800">
          {HORIZONS.map((hz) => (
            <button
              key={hz.seconds}
              onClick={() => handleHorizonChange(hz.seconds)}
              className={`px-3 py-1 rounded-md text-xs font-mono font-semibold transition-all ${
                activeHorizon === hz.seconds
                  ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {hz.label}
            </button>
          ))}
        </div>
      </div>

      {/* Predictions Table / Cards */}
      {filteredPredictions.length === 0 ? (
        <div className="py-8 text-center text-slate-500 text-xs font-mono">
          No prediction models converged for +{activeHorizon}s horizon yet. Processing video telemetry...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filteredPredictions.map((pred) => {
            const changePct = Math.round(pred.predicted_change_pct || 0);
            return (
              <div
                key={pred.id || `${pred.zone_id}-${pred.horizon_seconds}`}
                className="p-3.5 rounded-lg bg-[#070B14] border border-slate-800/90 hover:border-slate-700 transition-colors flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-semibold text-white">{pred.zone_name}</div>
                      <div className="text-[10px] font-mono text-slate-500">
                        Horizon: +{pred.horizon_seconds}s
                      </div>
                    </div>
                    <RiskPill level={pred.risk_category} size="sm" />
                  </div>

                  <div className="mt-3 flex items-baseline justify-between font-mono">
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase">Current</span>
                      <div className="text-base text-slate-300 font-bold">
                        {Math.round(pred.current_occupancy)} ppl
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-[10px] text-cyan-400 uppercase">Predicted</span>
                      <div className="text-lg text-cyan-400 font-bold">
                        {Math.round(pred.predicted_occupancy)} ppl
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center space-x-1">
                    {changePct > 5 ? (
                      <span className="text-rose-400 flex items-center font-bold">
                        <ArrowUpRight className="h-3.5 w-3.5 mr-0.5" />
                        +{changePct}%
                      </span>
                    ) : changePct < -5 ? (
                      <span className="text-emerald-400 flex items-center font-bold">
                        <ArrowDownRight className="h-3.5 w-3.5 mr-0.5" />
                        {changePct}%
                      </span>
                    ) : (
                      <span className="text-slate-400 flex items-center">
                        <Minus className="h-3.5 w-3.5 mr-0.5" />
                        Stable
                      </span>
                    )}
                    <span className="text-[10px] text-slate-500 capitalize">
                      ({pred.estimated_trend.replace('_', ' ')})
                    </span>
                  </div>

                  <div className="text-[10px] text-slate-500">
                    Conf: {Math.round(pred.confidence * 100)}%
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
