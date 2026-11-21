import React, { useState, useEffect } from 'react';
import {
  FileSpreadsheet,
  Download,
  Plus,
  RefreshCw,
  Calendar,
  AlertTriangle,
  Users,
  CheckCircle,
} from 'lucide-react';
import { ReportItem } from '../../types';
import { api } from '../../services/api';

interface ReportsViewProps {
  eventId: string;
  jobId?: string;
}

export const ReportsView: React.FC<ReportsViewProps> = ({ eventId, jobId }) => {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<ReportItem | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const fetchReports = async () => {
    setIsLoading(true);
    try {
      const data = await api.getReports(eventId);
      setReports(data);
      if (data.length > 0 && !selectedReport) {
        setSelectedReport(data[0]);
      }
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (eventId) fetchReports();
  }, [eventId]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const newRep = await api.generateReport(eventId, jobId);
      setReports([newRep, ...reports]);
      setSelectedReport(newRep);
    } catch {
      // ignore
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExportCsv = async (reportId: string) => {
    try {
      const csvData = await api.exportReportCsv(reportId);
      const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', `crowdvision_report_${reportId.slice(0, 8)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch {
      // ignore
    }
  };

  const sData = selectedReport?.summary_data;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Reports Archive Sidebar */}
      <div className="rounded-xl border border-slate-800 bg-[#0B1120] p-4 flex flex-col space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold flex items-center space-x-1.5">
            <FileSpreadsheet className="h-3.5 w-3.5 text-cyan-400" />
            <span>Operational Reports</span>
          </h4>
          <button
            onClick={fetchReports}
            className="text-slate-400 hover:text-white p-1"
            title="Refresh List"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className="w-full flex items-center justify-center space-x-2 py-2 px-3 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs transition-colors shadow-md shadow-cyan-500/20"
        >
          {isGenerating ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          <span>{isGenerating ? 'Generating...' : 'Compile New Report'}</span>
        </button>

        <div className="space-y-1.5 overflow-y-auto max-h-[500px]">
          {reports.map((rep) => (
            <button
              key={rep.id}
              onClick={() => setSelectedReport(rep)}
              className={`w-full text-left p-3 rounded-lg text-xs font-medium transition-all ${
                selectedReport?.id === rep.id
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-300 hover:bg-slate-800/80'
              }`}
            >
              <div className="font-semibold text-white">{rep.title}</div>
              <div className="text-[10px] text-slate-400 font-mono mt-1 flex items-center space-x-1">
                <Calendar className="h-3 w-3" />
                <span>{new Date(rep.created_at).toLocaleDateString()}</span>
              </div>
            </button>
          ))}
          {reports.length === 0 && !isLoading && (
            <div className="py-8 text-center text-slate-500 text-xs">
              No reports compiled yet. Click "Compile New Report".
            </div>
          )}
        </div>
      </div>

      {/* Main Report Details & CSV Export */}
      <div className="lg:col-span-3 rounded-xl border border-slate-800 bg-[#0B1120] p-6 flex flex-col space-y-6">
        {selectedReport ? (
          <>
            {/* Report Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-xl font-bold text-white tracking-tight">
                  {selectedReport.title}
                </h3>
                <div className="text-xs text-slate-400 font-mono mt-1">
                  Report ID: {selectedReport.id} | Generated: {new Date(selectedReport.created_at).toLocaleString()}
                </div>
              </div>

              <button
                onClick={() => handleExportCsv(selectedReport.id)}
                className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-medium text-xs shadow-lg shadow-emerald-500/20 active:scale-95 transition-all"
              >
                <Download className="h-4 w-4" />
                <span>One-Click Export CSV</span>
              </button>
            </div>

            {/* Executive Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-[#070B14] border border-slate-800">
                <div className="text-xs text-slate-400 font-mono">PEAK OCCUPANCY</div>
                <div className="text-2xl font-bold text-white font-mono mt-1">
                  {sData?.max_concurrent_crowd || 0} <span className="text-xs font-normal text-slate-500">ppl</span>
                </div>
                <div className="text-[11px] text-cyan-400 mt-1">Across all monitored zones</div>
              </div>

              <div className="p-4 rounded-xl bg-[#070B14] border border-slate-800">
                <div className="text-xs text-slate-400 font-mono">FRAMES ANALYZED</div>
                <div className="text-2xl font-bold text-white font-mono mt-1">
                  {sData?.frames_analyzed || 0}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Full OpenCV & ByteTrack pipeline</div>
              </div>

              <div className="p-4 rounded-xl bg-[#070B14] border border-slate-800">
                <div className="text-xs text-slate-400 font-mono">TOTAL ALERTS LOGGED</div>
                <div className="text-2xl font-bold text-rose-400 font-mono mt-1">
                  {sData?.alert_metrics?.total_alerts || 0}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  Critical: {sData?.alert_metrics?.critical || 0} | High: {sData?.alert_metrics?.high || 0}
                </div>
              </div>
            </div>

            {/* Zone Breakdown Table */}
            <div>
              <h4 className="text-sm font-semibold text-white mb-3 flex items-center space-x-2">
                <span>Spatial Zone Breakdown & Safety Metrics</span>
              </h4>

              <div className="overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-[#070B14] border-b border-slate-800 text-slate-400 uppercase text-[10px]">
                    <tr>
                      <th className="p-3">Zone Name</th>
                      <th className="p-3">Peak People</th>
                      <th className="p-3">Avg People</th>
                      <th className="p-3">Peak Utilization</th>
                      <th className="p-3">Max Inflow</th>
                      <th className="p-3">Max Outflow</th>
                      <th className="p-3">Bottlenecks</th>
                      <th className="p-3">Counterflows</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80 bg-[#0B1120]">
                    {sData?.zone_breakdown &&
                      Object.entries(sData.zone_breakdown).map(([zid, z]) => (
                        <tr key={zid} className="hover:bg-slate-800/40 transition-colors">
                          <td className="p-3 font-semibold text-white">{z.zone_name}</td>
                          <td className="p-3 text-cyan-400 font-bold">{z.peak_people}</td>
                          <td className="p-3 text-slate-300">{z.avg_people?.toFixed(1)}</td>
                          <td className="p-3">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] ${
                                (z.peak_capacity_utilization_pct || 0) > 80
                                  ? 'bg-rose-500/20 text-rose-300'
                                  : 'bg-emerald-500/20 text-emerald-300'
                              }`}
                            >
                              {Math.round(z.peak_capacity_utilization_pct || 0)}%
                            </span>
                          </td>
                          <td className="p-3 text-slate-400">{z.max_inflow?.toFixed(1)}/s</td>
                          <td className="p-3 text-slate-400">{z.max_outflow?.toFixed(1)}/s</td>
                          <td className="p-3 text-amber-400">{z.bottleneck_count || 0}</td>
                          <td className="p-3 text-rose-400">{z.counterflow_count || 0}</td>
                        </tr>
                      ))}
                    {(!sData?.zone_breakdown || Object.keys(sData.zone_breakdown).length === 0) && (
                      <tr>
                        <td colSpan={8} className="p-6 text-center text-slate-500">
                          No zone telemetry records included in this report session.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : (
          <div className="py-20 text-center text-slate-500 font-mono text-xs">
            Select a report from the left sidebar or compile a new one.
          </div>
        )}
      </div>
    </div>
  );
};
