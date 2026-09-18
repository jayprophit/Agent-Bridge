import React, { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Bot,
  Sparkles,
  BookOpen,
  Layers,
  Search,
  Plus,
  Pin,
  Trash2,
  Clock,
  ChevronDown,
  BrainCircuit,
  Settings,
  HardDrive,
  FolderPlus,
  Compass,
  FileText,
  Cpu,
  Check
} from 'lucide-react';
import { ProjectSession } from '../types';
import { AVAILABLE_MODELS } from '../data/models';

interface AgentSidePanelProps {
  projects: ProjectSession[];
  activeProjectId: string;
  onSelectProject: (id: string) => void;
  onNewChat: () => void;
  onOpenNewProjectModal?: () => void;
  activeModelId?: string;
  onModelChange?: (modelId: string) => void;
}

export const AgentSidePanel: React.FC<AgentSidePanelProps> = ({
  projects,
  activeProjectId,
  onSelectProject,
  onNewChat,
  onOpenNewProjectModal,
  activeModelId = 'gemini-2.5-pro',
  onModelChange,
}) => {
  const [activeRailTab, setActiveRailTab] = useState<'threads' | 'agents' | 'prompts' | 'knowledge'>('threads');
  const [searchQuery, setSearchQuery] = useState('');
  const [showModelMenu, setShowModelMenu] = useState(false);
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

  const railItems = [
    { id: 'threads', label: 'Chats', icon: MessageSquare },
    { id: 'agents', label: 'Agents', icon: Bot },
    { id: 'prompts', label: 'Prompts', icon: Sparkles },
    { id: 'knowledge', label: 'Docs', icon: BookOpen },
  ];

  const q = (searchQuery || '').toLowerCase();
  const filteredProjects = (projects || []).filter((p) =>
    (p.name || '').toLowerCase().includes(q)
  );

  const pinnedProjects = filteredProjects.filter((p) => p.pinned);
  const recentProjects = filteredProjects.filter((p) => !p.pinned);

  return (
    <div className="flex h-full shrink-0 select-none z-20">
      {/* Antigravity / Claude / Kimi style Thin Agent Rail */}
      <aside className="w-11 bg-slate-950 border-r border-slate-800 flex flex-col items-center justify-between py-2.5 shrink-0">
        <div className="flex flex-col items-center gap-1.5 w-full">
          {railItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeRailTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveRailTab(item.id as any)}
                className={`relative group flex flex-col items-center justify-center w-8.5 h-8.5 rounded-lg transition-all ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-[0_0_10px_rgba(37,99,235,0.3)]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                }`}
                title={item.label}
              >
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-blue-500 rounded-r-full" />
                )}
                <Icon className="w-3.5 h-3.5" />
                <span className="text-[8px] mt-0.5 font-medium">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Bottom token usage & memory */}
        <div className="flex flex-col items-center gap-2">
          <div
            className="w-7.5 h-7.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400 hover:text-cyan-400 hover:border-cyan-500/40 transition-colors cursor-pointer"
            title="Agent Context Memory: 48k / 1M tokens used"
          >
            <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
          </div>
        </div>
      </aside>

      {/* Primary Agent / Chat Drawer */}
      <aside className="w-56 sm:w-60 bg-slate-950/95 border-r border-slate-800 flex flex-col justify-between overflow-hidden">
        {/* Top Section */}
        <div className="p-2.5 space-y-2">
          {/* Model Selector Dropdown */}
          <div ref={modelMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setShowModelMenu(!showModelMenu)}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 hover:border-cyan-500/40 transition-colors text-left"
              title="Select LLM Backend for Agent"
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <Cpu className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                <div className="truncate">
                  <div className="text-[11px] font-bold text-white leading-tight truncate">
                    {currentModel.name}
                  </div>
                  <div className="text-[9px] text-slate-400 font-mono">
                    {currentModel.provider} • {currentModel.contextWindow}
                  </div>
                </div>
              </div>
              <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
            </button>

            {/* Model Dropdown Menu */}
            {showModelMenu && (
              <div className="absolute left-0 top-full mt-1 w-64 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl z-50 p-1.5 space-y-1 text-xs">
                <div className="px-2 py-1 text-[9px] font-mono text-slate-400 uppercase tracking-wider border-b border-slate-800">
                  Select LLM Backend
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

          {/* New Chat and New Project buttons */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={onNewChat}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-xs font-bold text-white shadow-[0_0_12px_rgba(37,99,235,0.3)] transition-all"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Chat</span>
            </button>

            {onOpenNewProjectModal && (
              <button
                onClick={onOpenNewProjectModal}
                title="Create New Project from Template"
                className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors"
              >
                <FolderPlus className="w-3.5 h-3.5 text-cyan-400" />
              </button>
            )}
          </div>

          {/* Search Conversations */}
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search chats & tasks..."
              className="w-full bg-slate-900/80 border border-slate-800 rounded-lg pl-7 pr-2.5 py-1 text-[11px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-sans"
            />
          </div>
        </div>

        {/* Content based on Rail Tab */}
        <div className="flex-1 overflow-y-auto px-2 space-y-4">
          {activeRailTab === 'threads' && (
            <>
              {/* Pinned Projects / Sessions */}
              {pinnedProjects.length > 0 && (
                <div>
                  <div className="px-2 pb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <Pin className="w-3 h-3 text-cyan-400 rotate-45" />
                    <span>Pinned Environments</span>
                  </div>
                  <div className="space-y-1">
                    {pinnedProjects.map((p) => {
                      const isActive = p.id === activeProjectId;
                      return (
                        <button
                          key={p.id}
                          onClick={() => onSelectProject(p.id)}
                          className={`w-full flex items-center justify-between p-2 rounded-xl text-left text-xs transition-all ${
                            isActive
                              ? 'bg-blue-600/15 border border-blue-500/40 text-white shadow-sm'
                              : 'text-slate-300 hover:bg-slate-900 border border-transparent'
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="w-2 h-2 rounded-full bg-cyan-400 shrink-0" />
                            <div className="truncate">
                              <div className="font-semibold truncate">{p.name}</div>
                              <div className="text-[10px] text-slate-500 truncate">{p.type}</div>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Recent Sessions */}
              <div>
                <div className="px-2 pb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  <Clock className="w-3 h-3 text-slate-500" />
                  <span>Recent Conversations</span>
                </div>
                <div className="space-y-1">
                  {recentProjects.map((p) => {
                    const isActive = p.id === activeProjectId;
                    return (
                      <button
                        key={p.id}
                        onClick={() => onSelectProject(p.id)}
                        className={`w-full flex items-center justify-between p-2 rounded-xl text-left text-xs transition-all ${
                          isActive
                            ? 'bg-blue-600/15 border border-blue-500/40 text-white shadow-sm'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <MessageSquare className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                          <div className="truncate">
                            <div className="font-medium truncate">{p.name}</div>
                            <div className="text-[10px] text-slate-500 truncate">{p.lastActive}</div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {activeRailTab === 'agents' && (
            <div className="space-y-2 p-1">
              <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider px-1">
                Active Agent Swarm
              </div>
              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-white">Antigravity Core</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">
                    Online
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Autonomous orchestrator routing coding, architecture, and testing.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-white">Gemini 2.5 Pro</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">
                    Reasoning
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Deep coding intelligence with multi-file AST context.
                </p>
              </div>
            </div>
          )}

          {activeRailTab === 'prompts' && (
            <div className="space-y-2 p-1">
              <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider px-1">
                Workflow Prompts
              </div>
              {[
                'Refactor into modular components',
                'Write Vitest unit tests',
                'Optimize bundle & tree-shaking',
                'Add WCAG AA accessibility',
              ].map((prompt, i) => (
                <div
                  key={i}
                  className="p-2.5 rounded-xl bg-slate-900/70 hover:bg-slate-900 border border-slate-800 text-xs text-slate-300 cursor-pointer transition-colors"
                >
                  <div className="flex items-center gap-1.5 font-medium text-cyan-400 mb-0.5">
                    <Sparkles className="w-3 h-3" />
                    <span>Workflow #{i + 1}</span>
                  </div>
                  <div className="text-slate-400 line-clamp-2">{prompt}</div>
                </div>
              ))}
            </div>
          )}

          {activeRailTab === 'knowledge' && (
            <div className="space-y-2 p-1">
              <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider px-1">
                Project Knowledge Base
              </div>
              {['README.md', 'Architecture Guide', 'API Specs', 'Environment Secrets'].map((doc, i) => (
                <div
                  key={i}
                  className="p-2.5 rounded-xl bg-slate-900/70 hover:bg-slate-900 border border-slate-800 text-xs text-slate-300 cursor-pointer flex items-center justify-between transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <FileText className="w-3.5 h-3.5 text-blue-400" />
                    <span>{doc}</span>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">Synced</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Bottom Agent Memory Card */}
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/60">
          <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-cyan-400" />
              <div>
                <div className="font-semibold text-slate-200 text-[11px]">Agent Memory</div>
                <div className="text-[10px] text-slate-500">24 items in context</div>
              </div>
            </div>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          </div>
        </div>
      </aside>
    </div>
  );
};
