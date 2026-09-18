import React, { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  ChevronDown,
  SlidersHorizontal,
  Paperclip,
  AtSign,
  Wrench,
  ArrowUp,
  CheckCircle2,
  Clock,
  Circle,
  FileCode2,
  Terminal,
  Play,
  RotateCw,
  Eye,
  Check,
  Send,
  Loader2,
  Cpu
} from 'lucide-react';
import { ChatMessage, PlanStep, CodeChip, ThemeType } from '../types';
import { AvatarHologram } from './AvatarHologram';
import { AVAILABLE_MODELS } from '../data/models';

interface ChatPanelProps {
  messages: ChatMessage[];
  environment: string;
  onEnvironmentChange: (env: string) => void;
  onSendMessage: (text: string) => void;
  onSelectCodeChip: (filePath: string) => void;
  onActionClick: (action: string) => void;
  theme: ThemeType;
  onStartVoiceCall: () => void;
  onStartVideoCall: () => void;
  onOpenTools: () => void;
  activeModelId?: string;
  onModelChange?: (modelId: string) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  environment,
  onEnvironmentChange,
  onSendMessage,
  onSelectCodeChip,
  onActionClick,
  theme,
  onStartVoiceCall,
  onStartVideoCall,
  onOpenTools,
  activeModelId = 'gemini-2.5-pro',
  onModelChange,
}) => {
  const [inputText, setInputText] = useState('');
  const [showMentionMenu, setShowMentionMenu] = useState(false);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const modelMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target as Node)) {
        setShowModelMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentModel =
    AVAILABLE_MODELS.find((m) => m.id === activeModelId) || AVAILABLE_MODELS[0];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim()) return;

    const userText = inputText.trim();
    setInputText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    onSendMessage(userText);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleMentionSelect = (mention: string) => {
    setInputText((prev) => `${prev} @${mention} `);
    setShowMentionMenu(false);
    textareaRef.current?.focus();
  };

  const mentionsList = [
    { type: 'agent', name: 'Atlas', desc: 'Project Lead' },
    { type: 'agent', name: 'Luna', desc: 'UI/UX Design' },
    { type: 'agent', name: 'Dev', desc: 'Full-Stack Developer' },
    { type: 'agent', name: 'Nova', desc: 'QA Specialist' },
    { type: 'file', name: 'TaskList.tsx', desc: 'React Component' },
    { type: 'file', name: 'useTasks.ts', desc: 'State Hook' },
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950/70 relative overflow-hidden">
      {/* Header bar */}
      <div className="h-10 border-b border-slate-800/80 px-3 flex items-center justify-between bg-slate-950/90 z-10 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-1.5">
            <div className="w-5 h-5 rounded-md bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400">
              <Sparkles className="w-3 h-3" />
            </div>
            <span className="font-bold text-xs text-white">Aetherius</span>
            <span className="flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              AI Assistant
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Model Selector Dropdown */}
          <div ref={modelMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setShowModelMenu(!showModelMenu)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/80 hover:border-cyan-500/50 text-xs text-slate-200 transition-colors shadow-sm"
              title="Toggle LLM Backend"
            >
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-semibold text-white">{currentModel.name}</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-slate-950 text-cyan-400 font-mono hidden sm:inline border border-slate-800">
                {currentModel.badge}
              </span>
              <ChevronDown className="w-3 h-3 text-slate-400" />
            </button>

            {showModelMenu && (
              <div className="absolute right-0 top-full mt-1 w-64 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl z-50 p-1.5 space-y-1 text-xs">
                <div className="px-2 py-1 text-[9px] font-mono text-slate-400 uppercase tracking-wider border-b border-slate-800">
                  Select LLM Backend for Chat
                </div>
                {AVAILABLE_MODELS.map((m) => {
                  const isSelected = m.id === currentModel.id;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => {
                        onModelChange?.(m.id);
                        setShowModelMenu(false);
                      }}
                      className={`w-full text-left p-2 rounded-lg transition-colors flex items-start justify-between ${
                        isSelected
                          ? 'bg-blue-600/20 border border-blue-500/40 text-white'
                          : 'hover:bg-slate-800 text-slate-300 border border-transparent'
                      }`}
                    >
                      <div className="min-w-0 mr-2">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-xs text-slate-100">{m.name}</span>
                          <span className="text-[9px] px-1 py-0.2 rounded bg-slate-950 font-mono text-cyan-400 border border-slate-800">
                            {m.badge}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-400 line-clamp-1 mt-0.5">{m.description}</p>
                        <div className="flex items-center gap-2 mt-1 text-[9px] font-mono text-slate-500">
                          <span>{m.provider}</span>
                          <span>•</span>
                          <span>{m.contextWindow}</span>
                        </div>
                      </div>
                      {isSelected && <Check className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Environment dropdown */}
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hidden sm:flex">
            <span className="text-slate-400">Env:</span>
            <span className="font-mono text-cyan-400 font-semibold text-[11px]">{environment}</span>
          </div>

          <button
            onClick={onOpenTools}
            title="Configure Tools"
            className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-900 transition-colors"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Hologram Presence Section */}
      <AvatarHologram
        theme={theme}
        onStartVoiceCall={onStartVoiceCall}
        onStartVideoCall={onStartVideoCall}
        isSpeaking={false}
      />

      {/* Conversation Message Feed */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className="space-y-3">
            {msg.sender === 'user' ? (
              /* User Prompt Bubble */
              <div className="flex justify-end gap-3">
                <div className="max-w-2xl bg-blue-600/15 border border-blue-500/30 rounded-2xl p-4 text-slate-100 shadow-sm">
                  <div className="flex items-center justify-between gap-4 mb-1">
                    <span className="text-[10px] font-mono text-blue-400 font-semibold">
                      You
                    </span>
                    <span className="text-[10px] text-slate-400">{msg.timestamp}</span>
                  </div>
                  <p className="text-sm leading-relaxed text-slate-100 whitespace-pre-wrap">
                    {msg.text}
                  </p>
                </div>
                <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-xs font-bold text-white shrink-0 mt-1 shadow-sm">
                  JD
                </div>
              </div>
            ) : (
              /* Agent Response */
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 flex items-center justify-center text-white shrink-0 mt-1 shadow-[0_0_12px_rgba(56,189,248,0.4)]">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>

                <div className="flex-1 max-w-3xl space-y-4">
                  {/* Text Header */}
                  {msg.text && (
                    <div className="text-sm leading-relaxed text-slate-200 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4 shadow-sm">
                      <div className="flex items-center justify-between gap-4 mb-2 pb-2 border-b border-slate-800/60">
                        <span className="text-[10px] font-mono text-cyan-400 font-semibold flex items-center gap-1.5">
                          <span>Aetherius</span>
                          <span className="text-slate-500">•</span>
                          <span>Autonomous Planner</span>
                        </span>
                        <span className="text-[10px] text-slate-400">{msg.timestamp}</span>
                      </div>
                      <p className="whitespace-pre-wrap">{msg.text}</p>
                    </div>
                  )}

                  {/* Implementation Plan Card */}
                  {msg.plan && (
                    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-lg space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-bold text-white">
                          <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                          <span>{msg.plan.title}</span>
                        </div>
                        <span className="text-[11px] text-slate-400 font-mono">
                          {msg.plan.steps.filter((s) => s.status === 'completed').length} of{' '}
                          {msg.plan.steps.length} completed
                        </span>
                      </div>

                      <div className="space-y-2 pt-1">
                        {msg.plan.steps.map((step) => (
                          <div
                            key={step.id}
                            className={`flex items-start justify-between p-2.5 rounded-xl text-xs transition-colors ${
                              step.status === 'in_progress'
                                ? 'bg-cyan-950/40 border border-cyan-500/30 text-cyan-100'
                                : step.status === 'completed'
                                ? 'bg-slate-950/40 border border-slate-800/60 text-slate-300'
                                : 'text-slate-400 border border-transparent'
                            }`}
                          >
                            <div className="flex items-start gap-2.5">
                              {step.status === 'completed' ? (
                                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                              ) : step.status === 'in_progress' ? (
                                <Loader2 className="w-4 h-4 text-cyan-400 animate-spin shrink-0 mt-0.5" />
                              ) : (
                                <Circle className="w-4 h-4 text-slate-600 shrink-0 mt-0.5" />
                              )}
                              <span className="leading-tight">{step.title}</span>
                            </div>

                            {step.time && (
                              <span
                                className={`text-[11px] font-mono shrink-0 ml-3 ${
                                  step.status === 'in_progress'
                                    ? 'text-cyan-400 font-semibold'
                                    : 'text-slate-500'
                                }`}
                              >
                                {step.time}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Code File Chips */}
                  {msg.codeChips && msg.codeChips.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Generated / Modified Files:
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {msg.codeChips.map((chip) => (
                          <button
                            key={chip.name}
                            onClick={() => onSelectCodeChip(chip.filePath)}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-xs text-slate-200 transition-all group"
                          >
                            <FileCode2 className="w-3.5 h-3.5 text-blue-400 group-hover:text-cyan-400" />
                            <span className="font-mono">{chip.name}</span>
                            <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded">
                              {chip.changes}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Interactive Action Buttons */}
                  {msg.actionButtons && msg.actionButtons.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      {msg.actionButtons.map((btn) => (
                        <button
                          key={btn.label}
                          onClick={() => onActionClick(btn.action)}
                          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                            btn.primary
                              ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_15px_rgba(37,99,235,0.4)]'
                              : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800'
                          }`}
                        >
                          {btn.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Mention Popup */}
      {showMentionMenu && (
        <div className="absolute bottom-24 left-6 w-64 bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-2 z-30 space-y-1 text-xs">
          <div className="px-2 py-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
            Mention Agent or File
          </div>
          {mentionsList.map((item) => (
            <button
              key={item.name}
              onClick={() => handleMentionSelect(item.name)}
              className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-slate-800 text-left transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-cyan-400 font-mono">@{item.name}</span>
              </div>
              <span className="text-[10px] text-slate-400">{item.desc}</span>
            </button>
          ))}
        </div>
      )}

      {/* Chat Input Container */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/90 z-20 shrink-0">
        <form
          onSubmit={handleSubmit}
          className="relative rounded-2xl bg-slate-900/95 border border-slate-800 focus-within:border-blue-500/60 shadow-xl transition-all p-2.5"
        >
          <textarea
            ref={textareaRef}
            rows={2}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Aetherius... (⇧↵ for new line)"
            className="w-full bg-transparent resize-none text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none px-2 py-1"
          />

          <div className="flex items-center justify-between pt-1 border-t border-slate-800/60 mt-1">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                title="Attach file or screenshot"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setShowMentionMenu(!showMentionMenu)}
                title="Mention agent or file (@)"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              >
                <AtSign className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={onOpenTools}
                title="Select Tools & Automations"
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <Wrench className="w-3.5 h-3.5 text-cyan-400" />
                <span>Tools</span>
              </button>
            </div>

            <button
              type="submit"
              disabled={!inputText.trim()}
              className={`p-2 rounded-xl transition-all ${
                inputText.trim()
                  ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_12px_rgba(37,99,235,0.5)]'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed'
              }`}
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
