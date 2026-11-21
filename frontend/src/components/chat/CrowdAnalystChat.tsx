import React, { useState, useRef, useEffect } from 'react';
import {
  Bot,
  Send,
  User,
  Sparkles,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
} from 'lucide-react';
import { ChatMessage } from '../../types';
import { api } from '../../services/api';

interface CrowdAnalystChatProps {
  eventId: string;
}

const SUGGESTED_PROMPTS = [
  'Summarize current crowd risk and key hotspots',
  'Which zones are predicted to exceed capacity in 3 minutes?',
  'Recommend crowd mitigation actions for Stage Area',
  'Detect any counterflows or bottleneck pinch points',
];

export const CrowdAnalystChat: React.FC<CrowdAnalystChatProps> = ({ eventId }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'agent',
      text: 'Hello, I am your Autonomous Crowd Intelligence Analyst. I am continuously monitoring crowd telemetry, density growth rates, and predictive advection-diffusion models. How can I assist with your operational decision making?',
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  const toggleReasoning = (msgId: string) => {
    setExpandedReasoning((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = textToSend || inputText;
    if (!text.trim() || isSending) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: text.trim(),
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsSending(true);

    try {
      const res = await api.sendChatMessage(eventId, text.trim());
      const agentMsg: ChatMessage = {
        id: `agent-${Date.now()}`,
        sender: 'agent',
        text: res.response,
        timestamp: new Date().toLocaleTimeString(),
        reasoning: res.reasoning_steps,
        recommendations: res.recommendations,
        risk_evaluations: res.risk_evaluations,
      };
      setMessages((prev) => [...prev, agentMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `agent-err-${Date.now()}`,
        sender: 'agent',
        text: `Error connecting to Crowd Analyst: ${err.message || 'Service unavailable'}. Please verify backend & AI agent are active.`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0B1120] p-5 shadow-lg flex flex-col h-[650px]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">AI Crowd Analyst</h3>
            <p className="text-[11px] text-cyan-400 font-mono">
              Direct Autonomous Intelligence Layer (:8100)
            </p>
          </div>
        </div>
      </div>

      {/* Suggested Prompts Pills */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-3 mb-2 text-xs scrollbar-none">
        <Sparkles className="h-3.5 w-3.5 text-cyan-400 flex-shrink-0" />
        {SUGGESTED_PROMPTS.map((prompt, idx) => (
          <button
            key={idx}
            onClick={() => handleSendMessage(prompt)}
            disabled={isSending}
            className="flex-shrink-0 px-3 py-1 rounded-full bg-[#070B14] hover:bg-slate-800 border border-slate-700/80 text-slate-300 text-xs transition-colors hover:border-cyan-500/40"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Chat Messages Log */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map((msg) => {
          const isAgent = msg.sender === 'agent';
          const hasReasoning = msg.reasoning && msg.reasoning.length > 0;
          const hasRecs = msg.recommendations && msg.recommendations.length > 0;
          const isExpanded = !!expandedReasoning[msg.id];

          return (
            <div
              key={msg.id}
              className={`flex items-start space-x-3 ${isAgent ? '' : 'flex-row-reverse space-x-reverse'}`}
            >
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  isAgent
                    ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30'
                    : 'bg-slate-800 text-slate-300 border border-slate-700'
                }`}
              >
                {isAgent ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
              </div>

              <div
                className={`max-w-[85%] rounded-xl p-3.5 text-xs ${
                  isAgent
                    ? 'bg-[#070B14] border border-slate-800 text-slate-200'
                    : 'bg-cyan-600 text-white font-medium shadow-md shadow-cyan-600/20'
                }`}
              >
                <div className="whitespace-pre-wrap leading-relaxed">{msg.text}</div>

                {/* Analytical Reasoning Drawer */}
                {isAgent && hasReasoning && (
                  <div className="mt-3 pt-2.5 border-t border-slate-800/80">
                    <button
                      onClick={() => toggleReasoning(msg.id)}
                      className="flex items-center space-x-1.5 text-[11px] font-mono text-cyan-400 hover:text-cyan-300 transition-colors"
                    >
                      {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      <span>Analytical Reasoning Trace ({msg.reasoning?.length} steps)</span>
                    </button>

                    {isExpanded && (
                      <div className="mt-2 space-y-1 pl-3 border-l border-cyan-500/30 font-mono text-[11px] text-slate-400">
                        {msg.reasoning?.map((step, sIdx) => (
                          <div key={sIdx} className="leading-tight">
                            • {step}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Recommendations List */}
                {isAgent && hasRecs && (
                  <div className="mt-3 pt-2.5 border-t border-slate-800/80 space-y-1.5">
                    <div className="text-[11px] font-mono text-emerald-400 font-semibold flex items-center space-x-1">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>Recommended Management Actions</span>
                    </div>
                    <ul className="space-y-1 pl-2 text-slate-300 text-[11px]">
                      {msg.recommendations?.map((rec, rIdx) => (
                        <li key={rIdx} className="flex items-start space-x-1.5">
                          <span className="text-cyan-400 font-bold">›</span>
                          <span>{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="mt-2 text-[10px] text-slate-500 text-right font-mono">
                  {msg.timestamp}
                </div>
              </div>
            </div>
          );
        })}

        {isSending && (
          <div className="flex items-start space-x-3">
            <div className="w-7 h-7 rounded-lg bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 flex items-center justify-center">
              <Bot className="h-4 w-4" />
            </div>
            <div className="p-3 rounded-xl bg-[#070B14] border border-slate-800 text-xs text-slate-400 flex items-center space-x-2">
              <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-400" />
              <span>Synthesizing multi-zone predictions and risk assessments...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <div className="mt-3 pt-3 border-t border-slate-800 flex items-center space-x-2">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSendMessage();
          }}
          placeholder="Ask about crowd trends, risks, bottlenecks, or recommendations..."
          className="flex-1 rounded-xl bg-[#070B14] border border-slate-700/80 px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
        />
        <button
          onClick={() => handleSendMessage()}
          disabled={isSending || !inputText.trim()}
          className="p-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold transition-all shadow-md shadow-cyan-500/20 active:scale-95"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
