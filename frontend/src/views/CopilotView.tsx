import React, { useState, useEffect, useRef } from 'react';
import {
  Bot,
  Send,
  Sparkles,
  ShieldAlert,
  Cpu,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Check,
  X,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { useTaskContext } from '../context/TaskContext';
import { CopilotActionProposal, CopilotQueryResponse } from '../types';
import { api } from '../services/api';

interface Message {
  id: string;
  sender: 'user' | 'copilot';
  text: string;
  timestamp: string;
  sources?: string[];
  actionProposal?: CopilotActionProposal;
}

export const CopilotView: React.FC = () => {
  const { activeTask, updateTask, changeTaskState, refreshTasks } = useTaskContext();

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'msg-welcome',
      sender: 'copilot',
      text: activeTask
        ? `Hello, Operator. I am your CROWD VISION AI Copilot. I have loaded context for **${activeTask.name}** (${activeTask.location || 'Site'}) with ${activeTask.layout_snapshot?.zones_data?.length || 0} spatial zones. How can I assist you today?`
        : 'Hello, Operator. I am your CROWD VISION AI Copilot. Select an active task from the top bar to inspect spatial layouts, zone capacities, or execute validated actions.',
      timestamp: new Date().toLocaleTimeString(),
      sources: ['system_initialization'],
    },
  ]);

  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [providerStatus, setProviderStatus] = useState<any>(null);
  const [executingAction, setExecutingAction] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showToolsModal, setShowToolsModal] = useState(false);
  const [toolsList, setToolsList] = useState<any[]>([]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Load Copilot Provider Status & Tools
  useEffect(() => {
    api.getCopilotStatus()
      .then((data) => {
        setProviderStatus(data);
        if (data.available_tools) setToolsList(data.available_tools);
      })
      .catch(() => {});
  }, []);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || inputText).trim();
    if (!text || isLoading) return;

    const userMsg: Message = {
      id: `msg-${Date.now()}-u`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputText('');
    setIsLoading(true);

    try {
      const res = await api.queryCopilot({
        task_id: activeTask?.id,
        message: text,
      });

      const copilotMsg: Message = {
        id: `msg-${Date.now()}-a`,
        sender: 'copilot',
        text: res.response,
        timestamp: new Date(res.timestamp).toLocaleTimeString(),
        sources: res.data_sources,
        actionProposal: res.action_proposal,
      };

      setMessages((prev) => [...prev, copilotMsg]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: `msg-${Date.now()}-err`,
        sender: 'copilot',
        text: `Error connecting to Copilot service: ${err.message || 'Service unavailable'}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleExecuteAction = async (proposal: CopilotActionProposal, msgId: string) => {
    setExecutingAction(msgId);
    setActionSuccess(null);

    try {
      // 1. Validate action safety with backend
      const val = await api.validateCopilotAction({
        action_type: proposal.action_type,
        parameters: proposal.parameters,
        task_id: activeTask?.id,
      });

      if (!val.is_valid) {
        alert(`Action validation failed: ${val.validation_errors.join(', ')}`);
        return;
      }

      // 2. Safely execute action via backend executor
      const res = await api.executeCopilotAction({
        action_type: proposal.action_type,
        parameters: proposal.parameters,
        task_id: activeTask?.id,
        confirmed_by: 'operator',
      });

      if (res.success) {
        setActionSuccess(res.message);
        await refreshTasks();
      } else {
        alert(`Action execution failed: ${res.message}`);
      }
    } catch (err: any) {
      alert(`Action failed: ${err.message}`);
    } finally {
      setExecutingAction(null);
    }
  };

  const quickPrompts = [
    'Tell me about the configured zones and capacity limits',
    'What is the current video source and camera perspective?',
    'What are the active safety alerts and risk levels?',
    'Show short-term crowd density predictions',
    'Pause monitoring on this task',
  ];

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col rounded-xl bg-[#0B1120] border border-slate-800 shadow-2xl overflow-hidden">
      {/* Header */}
      <div className="h-16 border-b border-slate-800 px-6 flex items-center justify-between bg-[#070B14] flex-shrink-0">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-bold text-white tracking-tight">AI Crowd Intelligence Copilot</h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                ACTIVE
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono mt-0.5">
              Task: {activeTask ? <span className="text-white font-bold">{activeTask.name}</span> : 'None Selected'} • Provider: {providerStatus?.active_provider || 'Deterministic Engine'}
            </div>
          </div>
        </div>

        <div className="hidden sm:flex items-center space-x-3 text-xs font-mono text-slate-400">
          <button
            onClick={() => setShowToolsModal(true)}
            className="flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-[#0B1120] hover:bg-slate-800 border border-slate-800 hover:border-cyan-500/40 text-slate-300 hover:text-white transition-all cursor-pointer"
          >
            <Cpu className="h-3.5 w-3.5 text-cyan-400" />
            <span>Tools: {providerStatus?.available_tools_count || toolsList.length || 18} Active</span>
          </button>
        </div>
      </div>

      {/* Messages Timeline */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-[#070B14]/40">
        {messages.map((msg) => {
          const isUser = msg.sender === 'user';
          return (
            <div key={msg.id} className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
              <div
                className={`max-w-2xl rounded-2xl p-4 text-xs leading-relaxed space-y-2.5 shadow-md ${
                  isUser
                    ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white rounded-tr-none'
                    : 'bg-[#0B1120] border border-slate-800 text-slate-200 rounded-tl-none'
                }`}
              >
                <div className="whitespace-pre-wrap font-sans text-xs">{msg.text}</div>

                {/* Grounding Sources Badge */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="flex items-center space-x-1.5 pt-2 border-t border-slate-800/80 text-[10px] font-mono text-slate-400">
                    <span className="text-cyan-400 font-bold uppercase">Grounding Sources:</span>
                    <span>{msg.sources.join(' • ')}</span>
                  </div>
                )}

                {/* Structured Action Proposal Card */}
                {msg.actionProposal && (
                  <div className="mt-3 p-3.5 rounded-xl bg-[#070B14] border border-cyan-500/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-cyan-400 uppercase font-mono flex items-center space-x-1.5">
                        <ShieldAlert className="h-3.5 w-3.5" />
                        <span>Action Proposal: {msg.actionProposal.action_type}</span>
                      </span>
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
                        APPROVAL REQUIRED
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-300 font-sans">{msg.actionProposal.rationale}</p>
                    <div className="text-[10px] font-mono text-slate-400">
                      Impact: {msg.actionProposal.risk_assessment}
                    </div>

                    <div className="flex items-center space-x-2 pt-2 border-t border-slate-800">
                      <button
                        onClick={() => handleExecuteAction(msg.actionProposal!, msg.id)}
                        disabled={executingAction === msg.id}
                        className="px-3 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs shadow-md transition-colors flex items-center space-x-1"
                      >
                        <Check className="h-3.5 w-3.5" />
                        <span>{executingAction === msg.id ? 'Validating...' : 'Approve & Execute Action'}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <span className="text-[10px] font-mono text-slate-500 mt-1 px-1">
                {msg.timestamp}
              </span>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex items-center space-x-2 p-3 rounded-xl bg-[#0B1120] border border-slate-800 text-xs text-cyan-400 max-w-xs animate-pulse">
            <Sparkles className="h-4 w-4 animate-spin" />
            <span>Copilot analyzing spatial telemetry...</span>
          </div>
        )}

        {actionSuccess && (
          <div className="p-3 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-200 text-xs flex items-center space-x-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
            <span>{actionSuccess}</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompts */}
      <div className="px-6 py-2.5 bg-[#070B14] border-t border-slate-800/80 flex items-center space-x-2 overflow-x-auto text-[11px]">
        <span className="text-slate-500 font-mono text-[10px] flex-shrink-0">PROMPTS:</span>
        {quickPrompts.map((p, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(p)}
            className="whitespace-nowrap px-2.5 py-1 rounded-lg bg-[#0B1120] hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors flex-shrink-0"
          >
            {p}
          </button>
        ))}
      </div>

      {/* Input Box */}
      <div className="p-4 bg-[#0B1120] border-t border-slate-800 flex items-center space-x-3 flex-shrink-0">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSend();
          }}
          placeholder="Ask Copilot about active task zones, capacity limits, or propose operational actions..."
          className="flex-1 bg-[#070B14] border border-slate-700/80 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-sans"
        />

        <button
          onClick={() => handleSend()}
          disabled={!inputText.trim() || isLoading}
          className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-xs shadow-lg shadow-cyan-500/25 active:scale-95 disabled:opacity-40 disabled:pointer-events-none transition-all flex items-center space-x-1.5"
        >
          <span>Send</span>
          <Send className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Tools Catalog Modal */}
      {showToolsModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#0B1120] border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-[#070B14]">
              <div className="flex items-center space-x-2">
                <Cpu className="h-4 w-4 text-cyan-400" />
                <h3 className="text-sm font-bold text-white">Copilot Validated Tool Catalog</h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                  {toolsList.length} Tools
                </span>
              </div>
              <button
                onClick={() => setShowToolsModal(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-3 flex-1 text-xs">
              {toolsList.map((tool, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl bg-[#070B14] border border-slate-800 space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-cyan-400 text-xs">
                      {tool.name}
                    </span>
                    <div className="flex items-center space-x-2">
                      <span
                        className={`text-[9px] font-mono px-2 py-0.5 rounded border ${
                          tool.category === 'action'
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        }`}
                      >
                        {tool.category === 'action' ? 'ACTION (CONFIRMATION REQUIRED)' : 'READ-ONLY'}
                      </span>
                    </div>
                  </div>
                  <p className="text-slate-300 font-sans text-[11px]">{tool.description}</p>
                  {tool.parameters && (
                    <div className="text-[10px] font-mono text-slate-500 bg-[#0B1120] p-1.5 rounded">
                      Parameters: {Object.keys(tool.parameters.properties || tool.parameters || {}).join(', ') || 'none'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
