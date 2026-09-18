import React, { useState } from 'react';
import {
  Plus,
  ChevronDown,
  Search,
  ShoppingCart,
  Image as ImageIcon,
  Globe,
  FileText,
  LineChart,
  Monitor,
  Hash,
  Smartphone,
  Layers,
  Sparkles,
  Pin
} from 'lucide-react';
import { ProjectSession } from '../types';

interface ProjectsDrawerProps {
  projects: ProjectSession[];
  activeProjectId: string;
  onSelectProject: (projectId: string) => void;
  onNewChat: () => void;
}

export const ProjectsDrawer: React.FC<ProjectsDrawerProps> = ({
  projects,
  activeProjectId,
  onSelectProject,
  onNewChat,
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  const getIconForProject = (name: string) => {
    if (name.includes('E-commerce')) return ShoppingCart;
    if (name.includes('Image')) return ImageIcon;
    if (name.includes('Marketing')) return Globe;
    if (name.includes('Research')) return Globe;
    if (name.includes('Data Analysis')) return LineChart;
    if (name.includes('Portfolio')) return Monitor;
    if (name.includes('Slack')) return Hash;
    if (name.includes('Mobile')) return Smartphone;
    return FileText;
  };

  const q = (searchQuery || '').toLowerCase();
  const filtered = (projects || []).filter((p) =>
    (p.name || '').toLowerCase().includes(q)
  );

  const pinnedProjects = filtered.filter((p) => p.pinned);
  const recentProjects = filtered.filter((p) => !p.pinned);

  return (
    <aside className="w-64 sm:w-72 bg-slate-950/95 border-r border-slate-800/80 flex flex-col justify-between shrink-0 select-none overflow-hidden">
      {/* Top Actions */}
      <div className="p-3.5 space-y-3">
        {/* + New Chat button with split dropdown */}
        <div className="flex items-center rounded-xl bg-blue-600 hover:bg-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.4)] transition-all overflow-hidden">
          <button
            onClick={onNewChat}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 px-3 text-xs font-bold text-white tracking-wide"
          >
            <Plus className="w-4 h-4" />
            <span>New Chat</span>
          </button>
          <div className="w-[1px] h-6 bg-blue-400/40" />
          <button
            onClick={onNewChat}
            className="px-2 py-2.5 text-white/80 hover:text-white transition-colors"
            title="Choose Template / Model"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>

        {/* Search Conversations */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full bg-slate-900/90 border border-slate-800/90 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/60 transition-colors"
          />
        </div>
      </div>

      {/* Projects List */}
      <div className="flex-1 overflow-y-auto px-3 py-1 space-y-4">
        {/* Pinned Section */}
        {pinnedProjects.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 px-2 mb-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <Pin className="w-3 h-3 text-slate-500" />
              <span>Pinned</span>
            </div>
            <div className="space-y-1">
              {pinnedProjects.map((p) => {
                const Icon = getIconForProject(p.name);
                const isActive = p.id === activeProjectId;
                return (
                  <button
                    key={p.id}
                    onClick={() => onSelectProject(p.id)}
                    className={`w-full flex items-start gap-2.5 p-2 rounded-xl text-left transition-all ${
                      isActive
                        ? 'bg-blue-600/15 border border-blue-500/40 text-white'
                        : 'hover:bg-slate-900/80 text-slate-300 border border-transparent'
                    }`}
                  >
                    <div className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 mt-0.5">
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold truncate">{p.name}</div>
                      <div className="text-[11px] text-slate-400 truncate">{p.type}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Recent Section */}
        <div>
          <div className="px-2 mb-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Recent
          </div>
          <div className="space-y-1">
            {recentProjects.map((p) => {
              const Icon = getIconForProject(p.name);
              const isActive = p.id === activeProjectId;
              return (
                <button
                  key={p.id}
                  onClick={() => onSelectProject(p.id)}
                  className={`w-full flex items-start gap-2.5 p-2 rounded-xl text-left transition-all group ${
                    isActive
                      ? 'bg-blue-600/15 border border-blue-500/40 text-white'
                      : 'hover:bg-slate-900/80 text-slate-300 border border-transparent'
                  }`}
                >
                  <div className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 mt-0.5 group-hover:text-blue-400">
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold truncate">{p.name}</span>
                      {isActive && (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                      {p.lastActive.includes('Active') ? (
                        <span className="text-emerald-400 flex items-center gap-1">
                          <span className="w-1 h-1 rounded-full bg-emerald-400" />
                          Active session
                        </span>
                      ) : (
                        <span>{p.lastActive}</span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom Isolated Environment Banner */}
      <div className="p-3 border-t border-slate-800/80">
        <div className="p-3 rounded-xl bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800 flex items-start gap-2.5">
          <div className="p-1.5 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 shrink-0">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-[11px] font-semibold text-slate-200">
              Each chat is an isolated environment.
            </h4>
            <p className="text-[10px] text-slate-400 mt-0.5 leading-snug">
              Files, dependencies, and settings stay separate per conversation.
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
};
