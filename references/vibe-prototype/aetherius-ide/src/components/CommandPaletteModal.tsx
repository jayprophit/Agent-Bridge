import React, { useState, useEffect } from 'react';
import {
  Search,
  MessageSquare,
  Code2,
  Users2,
  FolderClosed,
  Terminal,
  Palette,
  Phone,
  Video,
  X,
  Sparkles,
  Keyboard,
  Sliders
} from 'lucide-react';
import { ViewMode, ThemeType } from '../types';

interface CommandPaletteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectMode: (mode: ViewMode) => void;
  onSelectProject: (projectId: string) => void;
  onSelectTheme: (theme: ThemeType) => void;
  onStartVoiceCall: () => void;
  onStartVideoCall: () => void;
  onOpenTools?: () => void;
}

export const CommandPaletteModal: React.FC<CommandPaletteModalProps> = ({
  isOpen,
  onClose,
  onSelectMode,
  onSelectProject,
  onSelectTheme,
  onStartVoiceCall,
  onStartVideoCall,
  onOpenTools,
}) => {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const actions = [
    {
      category: 'Modes & Views',
      items: [
        { label: 'Switch to Chat Mode', icon: MessageSquare, action: () => onSelectMode('chat') },
        { label: 'Switch to Work / Split Code Mode', icon: Code2, action: () => onSelectMode('work') },
        { label: 'Open Team Meeting (All Hands 12-Agent Matrix)', icon: Users2, action: () => onSelectMode('team') },
      ],
    },
    {
      category: 'Conversations & Environments',
      items: [
        { label: 'Switch to Task Manager App', icon: FolderClosed, action: () => onSelectProject('proj-task-mgr') },
        { label: 'Switch to Automate Product Research', icon: FolderClosed, action: () => onSelectProject('proj-research') },
        { label: 'Switch to E-commerce Dashboard', icon: FolderClosed, action: () => onSelectProject('proj-ecom') },
      ],
    },
    {
      category: 'Audio / Video Hologram',
      items: [
        { label: 'Start Voice Call with Aetherius', icon: Phone, action: onStartVoiceCall },
        { label: 'Start Real-time Face-to-Face Video Call', icon: Video, action: onStartVideoCall },
      ],
    },
    {
      category: 'Settings & Keybindings',
      items: [
        ...(onOpenTools
          ? [
              {
                label: 'Configure Keyboard Shortcuts (Keybindings)',
                icon: Keyboard,
                action: onOpenTools,
              },
              {
                label: 'Agent Tools & Model Permissions',
                icon: Sliders,
                action: onOpenTools,
              },
            ]
          : []),
      ],
    },
    {
      category: 'Appearance & Themes',
      items: [
        { label: 'Theme: Dark', icon: Palette, action: () => onSelectTheme('dark') },
        { label: 'Theme: Dark Light', icon: Palette, action: () => onSelectTheme('dark-light') },
        { label: 'Theme: Aurora Glass', icon: Palette, action: () => onSelectTheme('aurora') },
        { label: 'Theme: Amber Terminal', icon: Palette, action: () => onSelectTheme('amber') },
      ],
    },
  ];

  const searchQuery = (query || '').toLowerCase();
  const filtered = actions
    .map((cat) => ({
      ...cat,
      items: (cat.items || []).filter((item) =>
        (item.label || '').toLowerCase().includes(searchQuery)
      ),
    }))
    .filter((cat) => cat.items.length > 0);

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-start justify-center pt-24 px-4 select-none animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center px-4 py-3 border-b border-slate-800">
          <Search className="w-4 h-4 text-slate-400 mr-3" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command, tool, or search..."
            className="flex-1 bg-transparent border-none text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            ESC
          </kbd>
        </div>

        {/* Action list */}
        <div className="max-h-96 overflow-y-auto p-2 space-y-3">
          {filtered.map((cat) => (
            <div key={cat.category}>
              <div className="text-[10px] font-semibold text-slate-500 px-3 py-1 uppercase tracking-wider">
                {cat.category}
              </div>
              <div className="space-y-0.5">
                {cat.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.label}
                      onClick={() => {
                        item.action();
                        onClose();
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs text-slate-300 hover:text-white hover:bg-slate-800 text-left transition-colors"
                    >
                      <Icon className="w-4 h-4 text-cyan-400 shrink-0" />
                      <span className="flex-1">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
