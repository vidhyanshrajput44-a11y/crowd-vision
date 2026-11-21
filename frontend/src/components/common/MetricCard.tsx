import React from 'react';
import { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: LucideIcon;
  trend?: {
    value: string;
    isPositive?: boolean;
    isNeutral?: boolean;
  };
  color?: 'cyan' | 'blue' | 'emerald' | 'amber' | 'rose' | 'default';
  className?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  color = 'cyan',
  className = '',
}) => {
  const iconColors = {
    cyan: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    rose: 'text-rose-400 bg-rose-500/10 border-rose-500/20',
    default: 'text-slate-400 bg-slate-800 border-slate-700',
  };

  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-slate-800/80 bg-[#0B1120]/90 p-5 shadow-lg backdrop-blur-sm transition-all duration-200 hover:border-slate-700 ${className}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {title}
        </span>
        {Icon && (
          <div className={`rounded-lg border p-2 ${iconColors[color]}`}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>

      <div className="mt-3 flex items-baseline justify-between">
        <div className="text-2xl font-bold tracking-tight text-white font-mono">
          {value}
        </div>
        {trend && (
          <div
            className={`flex items-center text-xs font-medium ${
              trend.isNeutral
                ? 'text-slate-400'
                : trend.isPositive
                ? 'text-emerald-400'
                : 'text-rose-400'
            }`}
          >
            <span>{trend.value}</span>
          </div>
        )}
      </div>

      {subtitle && (
        <p className="mt-1 text-xs text-slate-400 line-clamp-1">{subtitle}</p>
      )}
    </div>
  );
};
