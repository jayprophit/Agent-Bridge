import React, { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Code2,
  Users2,
  Search,
  CheckCircle2,
  ChevronDown,
  Settings,
  Bell,
  Sparkles,
  Minus,
  Square,
  X,
  Palette,
  Check,
  Activity,
  FolderPlus,
  Share2
} from 'lucide-react';
import { ViewMode, ThemeType } from '../types';

interface HeaderProps {
  mode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  theme: ThemeType;
  onThemeChange: (theme: ThemeType) => void;
  onOpenCommandPalette: () => void;
  onOpenSettings: () => void;
  onOpenModelsDrawer: () => void;
  onOpenPerformanceDashboard?: () => void;
  onOpenNewProjectModal?: () => void;
  onOpenShare?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  mode,
  onModeChange,
  theme,
  onThemeChange,
  onOpenCommandPalette,
  onOpenSettings,
  onOpenModelsDrawer,
  onOpenPerformanceDashboard,
  onOpenNewProjectModal,
  onOpenShare,
}) => {
  const [showThemeMenu, setShowThemeMenu] = useState(false);
  const [showEnvMenu, setShowEnvMenu] = useState(false);
  const themeMenuRef = useRef<HTMLDivElement>(null);
  const envMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (themeMenuRef.current && !themeMenuRef.current.contains(event.target as Node)) {
        setShowThemeMenu(false);
      }
      if (envMenuRef.current && !envMenuRef.current.contains(event.target as Node)) {
        setShowEnvMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const themeItems: Record<
    ThemeType,
    { label: string; syntaxPalette: string; colorDot: string }
  > = {
    dark: { label: 'Dark', syntaxPalette: 'One Dark Pro', colorDot: 'bg-[#c678dd]' },
    'dark-light': { label: 'Dark Light', syntaxPalette: 'Charcoal Slate', colorDot: 'bg-[#38bdf8]' },
    light: { label: 'Light', syntaxPalette: 'GitHub Light', colorDot: 'bg-[#2563eb]' },
    white: { label: 'White', syntaxPalette: 'Clean Paper', colorDot: 'bg-[#7c3aed]' },
    aurora: { label: 'Aurora', syntaxPalette: 'Neon Cyan', colorDot: 'bg-[#06b6d4]' },
    amber: { label: 'Amber', syntaxPalette: 'CRT Phosphor', colorDot: 'bg-[#f59e0b]' },
    frosted: { label: 'Frosted', syntaxPalette: 'Translucent Indigo', colorDot: 'bg-[#818cf8]' },
  };

  return (
    <header className="h-10.5 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md px-3 flex items-center justify-between z-30 shrink-0 select-none">
      {/* Brand & Tagline */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="relative w-6 h-6 rounded-lg bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 flex items-center justify-center shadow-[0_0_12px_rgba(59,130,246,0.4)]">
            <Sparkles className="w-3.5 h-3.5 text-white animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-sm tracking-tight text-white font-sans">
                Aetherius <span className="font-light text-cyan-400">IDE</span>
              </span>
            </div>
          </div>
        </div>

        {/* Mode Switchers: Chat, Work, Team */}
        <div className="hidden md:flex items-center bg-slate-900/90 p-0.5 rounded-lg border border-slate-800/90 shadow-inner">
          <button
            onClick={() => onModeChange('chat')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all duration-150 ${
              mode === 'chat'
                ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Chat</span>
          </button>
          <button
            onClick={() => onModeChange('work')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all duration-150 ${
              mode === 'work'
                ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Code2 className="w-3.5 h-3.5" />
            <span>Work</span>
          </button>
          <button
            onClick={() => onModeChange('team')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all duration-150 ${
              mode === 'team'
                ? 'bg-indigo-600 text-white shadow-[0_0_10px_rgba(79,70,229,0.4)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Users2 className="w-3.5 h-3.5" />
            <span>Team</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
          </button>
        </div>
      </div>

      {/* Center Search Bar */}
      <div className="flex-1 max-w-md mx-4 hidden lg:block">
        <button
          onClick={onOpenCommandPalette}
          className="w-full flex items-center justify-between px-3.5 py-1.5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-slate-300 text-xs transition-colors shadow-inner"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-slate-500" />
            <span>Search files, commands, agents...</span>
          </div>
          <kbd className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 border border-slate-700 text-slate-400">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3">
        {/* Dev Environment Ready Pill */}
        <div className="relative" ref={envMenuRef}>
          <button
            onClick={() => setShowEnvMenu(!showEnvMenu)}
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-slate-700 text-xs font-medium text-slate-300 transition-colors"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
            <span className="hidden sm:inline">Dev Environment Ready</span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          {showEnvMenu && (
            <div className="absolute right-0 mt-2 w-64 p-3 rounded-xl bg-slate-900 border border-slate-800 shadow-2xl z-50 text-xs space-y-2">
              <div className="font-semibold text-slate-200 border-b border-slate-800 pb-2">
                Active Environment
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Node.js:</span>
                <span className="font-mono text-cyan-400">v22.14.0</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Port:</span>
                <span className="font-mono text-cyan-400">3000 (ingress)</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Vite:</span>
                <span className="font-mono text-emerald-400">Ready (387ms)</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Hot Module:</span>
                <span className="font-mono text-slate-300">Fast Refresh</span>
              </div>
            </div>
          )}
        </div>

        {/* Theme Dropdown */}
        <div className="relative" ref={themeMenuRef}>
          <button
            onClick={() => setShowThemeMenu(!showThemeMenu)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-slate-700 text-xs font-medium text-slate-300 transition-colors"
          >
            <Palette className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Theme: {themeItems[theme]?.label || 'Dark'}</span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          {showThemeMenu && (
            <div className="absolute right-0 mt-2 w-64 py-2 rounded-xl bg-slate-900 border border-slate-700 shadow-2xl z-50 text-xs space-y-1">
              <div className="px-3 py-1 text-[10px] font-mono text-slate-400 border-b border-slate-800 uppercase tracking-wider flex items-center justify-between">
                <span>UI Theme</span>
                <span>Code Syntax Palette</span>
              </div>
              {(Object.keys(themeItems) as ThemeType[]).map((t) => {
                const item = themeItems[t];
                const isSelected = theme === t;
                return (
                  <button
                    key={t}
                    onClick={() => {
                      onThemeChange(t);
                      setShowThemeMenu(false);
                    }}
                    className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors ${
                      isSelected ? 'bg-blue-600/20 text-white' : 'hover:bg-slate-800/80 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${item.colorDot} shadow-sm`} />
                      <span className={isSelected ? 'text-cyan-400 font-semibold' : 'text-slate-200'}>
                        {item.label}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-400 px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">
                        {item.syntaxPalette}
                      </span>
                      {isSelected && <Check className="w-3.5 h-3.5 text-cyan-400 shrink-0" />}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Share Project Live Collaboration Button */}
        {onOpenShare && (
          <button
            onClick={onOpenShare}
            title="Generate Shareable Project Link"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-600/20 hover:bg-blue-600/35 text-cyan-300 border border-blue-500/40 hover:border-cyan-400/60 transition-all text-xs font-semibold shadow-sm"
          >
            <Share2 className="w-3.5 h-3.5 text-cyan-400" />
            <span>Share</span>
          </button>
        )}

        {/* New Project Button */}
        {onOpenNewProjectModal && (
          <button
            onClick={onOpenNewProjectModal}
            title="Create New Project from Template"
            className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800/60 transition-colors hidden sm:flex items-center gap-1 text-xs"
          >
            <FolderPlus className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline text-slate-300 font-medium text-[11px]">New</span>
          </button>
        )}

        {/* Performance & Internal Telemetry Dashboard */}
        {onOpenPerformanceDashboard && (
          <button
            onClick={onOpenPerformanceDashboard}
            title="IDE Internal Performance & Telemetry (Ctrl+Shift+M)"
            className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-800/60 transition-colors flex items-center gap-1"
          >
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[10px] font-mono text-emerald-400 hidden xl:inline">18% CPU</span>
          </button>
        )}

        {/* Settings & Models */}
        <button
          onClick={onOpenModelsDrawer}
          title="AI Models & Plugins"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
        >
          <Settings className="w-3.5 h-3.5" />
        </button>

        {/* User Profile avatar JD */}
        <div className="flex items-center gap-2 pl-1.5 border-l border-slate-800">
          <div className="relative">
            <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center text-[10px] font-bold text-white shadow-sm">
              JD
            </div>
            <span className="absolute bottom-0 right-0 w-1.5 h-1.5 rounded-full bg-emerald-400 ring-1 ring-slate-950" />
          </div>
        </div>

        {/* OS Window Controls */}
        <div className="hidden sm:flex items-center gap-1.5 pl-2 text-slate-500">
          <button className="p-1 hover:text-slate-300 transition-colors" title="Minimize">
            <Minus className="w-3 h-3" />
          </button>
          <button className="p-1 hover:text-slate-300 transition-colors" title="Maximize">
            <Square className="w-2.5 h-2.5" />
          </button>
          <button className="p-1 hover:text-rose-400 transition-colors" title="Close">
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>
    </header>
  );
};
