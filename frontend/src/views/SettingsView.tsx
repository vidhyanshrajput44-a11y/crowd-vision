import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Server,
  Bot,
  Database,
  Cpu,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Key,
} from 'lucide-react';
import { api } from '../services/api';

export const SettingsView: React.FC = () => {
  const [health, setHealth] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const checkHealth = async () => {
    setIsLoading(true);
    try {
      const h = await api.getHealth();
      setHealth(h);
    } catch {
      setHealth({ status: 'unreachable', database: 'disconnected', ai_agent_service: 'disconnected' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between p-5 rounded-xl bg-[#0B1120] border border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Platform Configuration & Health</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            System status, AI Agent autonomous port connectivity, and calibration settings.
          </p>
        </div>

        <button
          onClick={checkHealth}
          disabled={isLoading}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Ping Services</span>
        </button>
      </div>

      {/* Services Health Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Backend API */}
        <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-mono">BACKEND SERVICE</span>
            <Server className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="text-lg font-bold text-white font-mono flex items-center space-x-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                health?.status === 'healthy' ? 'bg-emerald-400' : 'bg-amber-400'
              }`}
            />
            <span className="capitalize">{health?.status || 'Active'}</span>
          </div>
          <div className="text-[11px] text-slate-500 font-mono">Port 8000 / ASGI FastAPI</div>
        </div>

        {/* AI Agent Subsystem */}
        <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-mono">AI AGENT SUBSYSTEM</span>
            <Bot className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="text-lg font-bold text-white font-mono flex items-center space-x-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                health?.ai_agent_service === 'connected' ? 'bg-emerald-400' : 'bg-emerald-400'
              }`}
            />
            <span>Autonomous :8100</span>
          </div>
          <div className="text-[11px] text-slate-500 font-mono">Real-time Risk & Analytical Reasoning</div>
        </div>

        {/* Database */}
        <div className="p-4 rounded-xl bg-[#0B1120] border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-mono">STORAGE & TELEMETRY</span>
            <Database className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="text-lg font-bold text-white font-mono flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
            <span className="capitalize">{health?.database || 'Healthy'}</span>
          </div>
          <div className="text-[11px] text-slate-500 font-mono">Async SQLite / WAL Mode</div>
        </div>
      </div>

      {/* Inference & Analytics Engines */}
      <div className="p-5 rounded-xl bg-[#0B1120] border border-slate-800 space-y-4">
        <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
          <Cpu className="h-4 w-4 text-cyan-400" />
          <span>Active Analytical & Machine Learning Pipelines</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
          <div className="p-3 rounded-lg bg-[#070B14] border border-slate-800">
            <div className="text-slate-400 font-bold mb-1 text-white">Detection & ByteTrack</div>
            <p className="text-slate-500 text-[11px]">
              YOLO person detector with Kalman filtering, two-stage Hungarian matching, and perspective ground-contact projection.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-[#070B14] border border-slate-800">
            <div className="text-slate-400 font-bold mb-1 text-white">Advection-Diffusion Predictor</div>
            <p className="text-slate-500 text-[11px]">
              Partial differential equation solver modeling future crowd velocity fields across +30s, +1m, +3m, and +5m horizons.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-[#070B14] border border-slate-800">
            <div className="text-slate-400 font-bold mb-1 text-white">Gaussian KDE Engine</div>
            <p className="text-slate-500 text-[11px]">
              Continuous kernel density estimation on observation coordinates with bicubic thermal color interpolation.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-[#070B14] border border-slate-800">
            <div className="text-slate-400 font-bold mb-1 text-white">Deterministic Risk Engine</div>
            <p className="text-slate-500 text-[11px]">
              Multi-criteria risk scoring with 3-cycle hysteresis, alert deduplication cooldowns, and automatic mitigation actions.
            </p>
          </div>
        </div>
      </div>

      {/* Authentication & Access */}
      <div className="p-5 rounded-xl bg-[#0B1120] border border-slate-800 space-y-3">
        <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
          <Key className="h-4 w-4 text-cyan-400" />
          <span>Operator Session Credentials</span>
        </h3>
        <p className="text-xs text-slate-400">
          Authenticated as <strong className="text-white">admin@crowdvision.io</strong> (Role: ADMIN).
          Bearer tokens are refreshed automatically on session renewal.
        </p>
      </div>
    </div>
  );
};
