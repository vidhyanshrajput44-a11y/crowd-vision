import React from 'react';
import { RiskLevel, AlertSeverity } from '../../types';

interface RiskPillProps {
  level: RiskLevel | AlertSeverity | string;
  className?: string;
  size?: 'sm' | 'md';
}

export const RiskPill: React.FC<RiskPillProps> = ({ level, className = '', size = 'md' }) => {
  const normLevel = (level || 'NORMAL').toUpperCase();

  let colorClasses = 'bg-slate-800 text-slate-300 border-slate-700';

  if (normLevel === 'NORMAL' || normLevel === 'LOW') {
    if (normLevel === 'LOW') {
      colorClasses = 'bg-blue-500/10 text-blue-400 border-blue-500/30';
    } else {
      colorClasses = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    }
  } else if (normLevel === 'MODERATE' || normLevel === 'MEDIUM') {
    colorClasses = 'bg-amber-500/10 text-amber-400 border-amber-500/30';
  } else if (normLevel === 'HIGH') {
    colorClasses = 'bg-orange-500/10 text-orange-400 border-orange-500/30';
  } else if (normLevel === 'CRITICAL') {
    colorClasses = 'bg-red-500/20 text-red-300 border-red-500/50 shadow-sm shadow-red-900/30 animate-pulse';
  }

  const sizeClasses = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-semibold';

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full border uppercase tracking-wider font-mono ${sizeClasses} ${colorClasses} ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 opacity-80" />
      {normLevel}
    </span>
  );
};
