import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Terminal as TerminalIcon,
  Play,
  RotateCcw,
  Trash2,
  Plus,
  X,
  Sparkles,
  ChevronDown,
  Layers,
  Copy,
  Check,
  Split,
  Folder,
  Search,
  ChevronUp,
  Sliders,
  Palette,
  Activity,
  CheckCircle2,
  Cpu,
  Filter
} from 'lucide-react';
import { TerminalLine, TerminalPalette, TerminalPaletteId } from '../types';
import { TERMINAL_PALETTES, DEFAULT_TERMINAL_PALETTE_ID } from '../data/terminalThemes';

export interface ShellSession {
  id: string;
  title: string;
  type: 'bash' | 'node' | 'server' | 'python' | 'zsh';
  status: 'running' | 'idle';
  activeTaskName?: string;
  lastExitCode?: number;
  duration?: string;
  lines: TerminalLine[];
  inputVal: string;
  cwd: string;
  commandHistory: string[];
}

const INITIAL_SESSIONS: ShellSession[] = [
  {
    id: 'session-server',
    title: '1: dev-server',
    type: 'server',
    status: 'running',
    activeTaskName: 'vite --host (PID 4182)',
    lastExitCode: 0,
    duration: 'active (24m)',
    cwd: 'task-manager',
    inputVal: '',
    commandHistory: ['npm run dev', 'npm list --depth=0'],
    lines: [
      { id: 'l1', type: 'info', text: '▶ aetherius-vite v5.2.0 ready in 184ms' },
      { id: 'l2', type: 'success', text: '  ➜  Local:   http://localhost:5173/' },
      { id: 'l3', type: 'info', text: '  ➜  Network: http://192.168.1.104:5173/' },
      { id: 'l4', type: 'success', text: '  ✓ HMR active (ready for fast refresh)' },
      { id: 'l5', type: 'info', text: '[vite] 12 modules transformed.' },
    ],
  },
  {
    id: 'session-bash',
    title: '2: bash',
    type: 'bash',
    status: 'idle',
    activeTaskName: 'idle',
    lastExitCode: 0,
    duration: '0.04s',
    cwd: 'task-manager',
    inputVal: '',
    commandHistory: ['git status', 'ls -la', 'git branch -a'],
    lines: [
      { id: 'b1', type: 'info', text: 'Aetherius Integrated Terminal v2.4.1 (x86_64-linux-gnu)' },
      { id: 'b2', type: 'command', text: 'task-manager git:(main) ➜ git status' },
      { id: 'b3', type: 'info', text: 'On branch main' },
      { id: 'b4', type: 'success', text: 'Your branch is up to date with origin/main.' },
      { id: 'b5', type: 'warn', text: 'Changes not staged for commit:' },
      { id: 'b6', type: 'info', text: '  modified:   src/components/TaskList.tsx' },
    ],
  },
  {
    id: 'session-test',
    title: '3: vitest runner',
    type: 'node',
    status: 'idle',
    activeTaskName: 'vitest run',
    lastExitCode: 0,
    duration: '1.42s',
    cwd: 'task-manager',
    inputVal: '',
    commandHistory: ['npm test', 'npx vitest run --coverage'],
    lines: [
      { id: 't1', type: 'info', text: '▶ vitest run --reporter=verbose' },
      { id: 't2', type: 'success', text: '  ✔ src/components/TaskList.test.tsx (6 passed)' },
      { id: 't3', type: 'success', text: '  ✔ src/hooks/useTasks.test.ts (4 passed)' },
      { id: 't4', type: 'success', text: '  ✔ src/lib/utils.test.ts (2 passed)' },
      { id: 't5', type: 'success', text: 'Test Files  3 passed (3) | Tests 12 passed (12)' },
      { id: 't6', type: 'info', text: 'Duration    1.42s' },
    ],
  },
];

interface TerminalPanelProps {
  paletteId?: TerminalPaletteId;
  onSelectPalette?: (paletteId: TerminalPaletteId) => void;
  onOpenSettings?: () => void;
}

export const TerminalPanel: React.FC<TerminalPanelProps> = ({
  paletteId = DEFAULT_TERMINAL_PALETTE_ID,
  onSelectPalette,
  onOpenSettings,
}) => {
  const [sessions, setSessions] = useState<ShellSession[]>(INITIAL_SESSIONS);
  const [activeSessionId, setActiveSessionId] = useState<string>('session-server');
  const [showNewTabMenu, setShowNewTabMenu] = useState(false);
  const [showPaletteMenu, setShowPaletteMenu] = useState(false);

  // Command History Navigation State
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [tempDraftInput, setTempDraftInput] = useState<string>('');

  // Search & Filter State
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterOnlyMatches, setFilterOnlyMatches] = useState(false);

  const terminalEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const activeSession =
    sessions.find((s) => s.id === activeSessionId) || sessions[0] || INITIAL_SESSIONS[0];

  const currentPalette: TerminalPalette =
    TERMINAL_PALETTES[paletteId] || TERMINAL_PALETTES[DEFAULT_TERMINAL_PALETTE_ID];

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession.lines]);

  // Reset history index when active session changes
  useEffect(() => {
    setHistoryIndex(-1);
    setTempDraftInput('');
  }, [activeSessionId]);

  // Auto-focus search input when opened
  useEffect(() => {
    if (isSearchOpen) {
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
  }, [isSearchOpen]);

  // Command executor for the active session
  const handleCommand = (cmd: string) => {
    const trimmed = cmd.trim();
    if (!trimmed) return;

    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const newCommandEntry: TerminalLine = {
      id: `cmd-${Date.now()}`,
      type: 'command',
      text: `${activeSession.cwd} git:(main) ➜ ${trimmed}`,
      time,
    };

    let responses: TerminalLine[] = [];
    let updatedTaskName = trimmed.split(' ')[0] || 'process';
    let updatedStatus: 'running' | 'idle' = 'idle';
    let exitCode = 0;
    let duration = '0.12s';

    if (trimmed === 'clear') {
      setSessions((prev) =>
        prev.map((s) => (s.id === activeSessionId ? { ...s, lines: [], inputVal: '' } : s))
      );
      setHistoryIndex(-1);
      return;
    } else if (trimmed === 'npm test' || trimmed === 'vitest') {
      updatedTaskName = 'vitest runner';
      updatedStatus = 'idle';
      duration = '0.94s';
      responses = [
        { id: `r1-${Date.now()}`, type: 'step', text: '▶ Running test suite with vitest...' },
        { id: `r2-${Date.now()}`, type: 'success', text: '  ✔ src/components/TaskList.test.tsx (6 tests passed)' },
        { id: `r3-${Date.now()}`, type: 'success', text: '  ✔ src/hooks/useTasks.test.ts (4 tests passed)' },
        { id: `r4-${Date.now()}`, type: 'success', text: '  Test Files  2 passed (2)' },
        { id: `r5-${Date.now()}`, type: 'success', text: '  Tests       10 passed (10) in 0.88s' },
      ];
    } else if (trimmed === 'git status') {
      updatedTaskName = 'git status';
      updatedStatus = 'idle';
      duration = '0.05s';
      responses = [
        { id: `r1-${Date.now()}`, type: 'info', text: 'On branch main' },
        { id: `r2-${Date.now()}`, type: 'info', text: 'Your branch is up to date with origin/main.' },
        { id: `r3-${Date.now()}`, type: 'warn', text: 'Changes not staged for commit:' },
        { id: `r4-${Date.now()}`, type: 'info', text: '  modified:   src/components/TaskList.tsx' },
        { id: `r5-${Date.now()}`, type: 'info', text: '  modified:   src/types.ts' },
      ];
    } else if (trimmed === 'npm run build') {
      updatedTaskName = 'vite build';
      updatedStatus = 'idle';
      duration = '2.14s';
      responses = [
        { id: `r1-${Date.now()}`, type: 'step', text: '▶ Building for production with Vite...' },
        { id: `r2-${Date.now()}`, type: 'info', text: '  ✓ 786 modules transformed.' },
        { id: `r3-${Date.now()}`, type: 'success', text: '  dist/index.html            0.45 kB' },
        { id: `r4-${Date.now()}`, type: 'success', text: '  dist/assets/index.js      214.67 kB' },
        { id: `r5-${Date.now()}`, type: 'success', text: '  ✔ Build completed in 2.12s' },
      ];
    } else if (trimmed === 'npm run dev') {
      updatedTaskName = 'vite --host (PID 5120)';
      updatedStatus = 'running';
      duration = 'active';
      responses = [
        { id: `r1-${Date.now()}`, type: 'step', text: '▶ aetherius-vite v5.2.0 server restarting...' },
        { id: `r2-${Date.now()}`, type: 'success', text: '  ➜  Local:   http://localhost:5173/' },
        { id: `r3-${Date.now()}`, type: 'info', text: '  ➜  Network: http://192.168.1.104:5173/' },
      ];
    } else if (trimmed === 'ls' || trimmed === 'dir') {
      updatedTaskName = 'ls';
      responses = [
        { id: `r1-${Date.now()}`, type: 'info', text: 'node_modules/   src/   public/   package.json   tsconfig.json   vite.config.ts' },
      ];
    } else if (trimmed.startsWith('echo ')) {
      updatedTaskName = 'echo';
      responses = [
        { id: `r1-${Date.now()}`, type: 'info', text: trimmed.slice(5) },
      ];
    } else if (trimmed === 'node -v') {
      updatedTaskName = 'node';
      responses = [
        { id: `r1-${Date.now()}`, type: 'success', text: 'v20.12.2' },
      ];
    } else if (trimmed === 'python -V' || trimmed === 'python3 --version') {
      updatedTaskName = 'python';
      responses = [
        { id: `r1-${Date.now()}`, type: 'success', text: 'Python 3.11.8' },
      ];
    } else {
      updatedTaskName = trimmed;
      responses = [
        { id: `r1-${Date.now()}`, type: 'info', text: `Executed: ${trimmed}` },
        { id: `r2-${Date.now()}`, type: 'success', text: `Completed successfully (exit code 0)` },
      ];
    }

    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== activeSessionId) return s;
        // Append to session command history if distinct from previous
        const history = [...s.commandHistory];
        if (history[history.length - 1] !== trimmed) {
          history.push(trimmed);
        }
        return {
          ...s,
          lines: [...s.lines, newCommandEntry, ...responses],
          inputVal: '',
          activeTaskName: updatedTaskName,
          status: updatedStatus,
          lastExitCode: exitCode,
          duration,
          commandHistory: history,
        };
      })
    );

    setHistoryIndex(-1);
    setTempDraftInput('');
  };

  // Keyboard navigation for command prompt (Enter, ArrowUp, ArrowDown)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const history = activeSession.commandHistory || [];

    if (e.key === 'Enter') {
      e.preventDefault();
      handleCommand(activeSession.inputVal);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length === 0) return;

      // Save user's current draft if starting navigation from bottom
      if (historyIndex === -1) {
        setTempDraftInput(activeSession.inputVal);
      }

      const nextIndex =
        historyIndex === -1
          ? history.length - 1
          : Math.max(0, historyIndex - 1);

      setHistoryIndex(nextIndex);
      const recalled = history[nextIndex] || '';
      setSessions((prev) =>
        prev.map((s) => (s.id === activeSessionId ? { ...s, inputVal: recalled } : s))
      );
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex === -1) return;

      if (historyIndex < history.length - 1) {
        const nextIndex = historyIndex + 1;
        setHistoryIndex(nextIndex);
        const recalled = history[nextIndex] || '';
        setSessions((prev) =>
          prev.map((s) => (s.id === activeSessionId ? { ...s, inputVal: recalled } : s))
        );
      } else {
        // Returned past newest command: restore draft input
        setHistoryIndex(-1);
        setSessions((prev) =>
          prev.map((s) => (s.id === activeSessionId ? { ...s, inputVal: tempDraftInput } : s))
        );
      }
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
      e.preventDefault();
      setIsSearchOpen(true);
    }
  };

  // Add new terminal tab session
  const handleAddNewSession = (type: ShellSession['type']) => {
    const count = sessions.length + 1;
    const newId = `session-${Date.now()}`;
    const title = `${count}: ${type}`;

    const newSession: ShellSession = {
      id: newId,
      title,
      type,
      status: 'idle',
      activeTaskName: 'idle',
      lastExitCode: 0,
      duration: '0.01s',
      cwd: 'task-manager',
      inputVal: '',
      commandHistory: [],
      lines: [
        {
          id: `init-${Date.now()}`,
          type: 'info',
          text: `Opened new ${type} session #${count} in /task-manager (Palette: ${currentPalette.name})`,
        },
      ],
    };

    setSessions((prev) => [...prev, newSession]);
    setActiveSessionId(newId);
    setShowNewTabMenu(false);
  };

  // Close tab session
  const handleCloseSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (sessions.length <= 1) return;

    const remaining = sessions.filter((s) => s.id !== id);
    setSessions(remaining);

    if (activeSessionId === id) {
      setActiveSessionId(remaining[0].id);
    }
  };

  // Clear current active session output
  const handleClearCurrent = () => {
    setSessions((prev) =>
      prev.map((s) => (s.id === activeSessionId ? { ...s, lines: [] } : s))
    );
  };

  // Search matches computation
  const { filteredLines, matchCount } = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) {
      return { filteredLines: activeSession.lines, matchCount: 0 };
    }

    let count = 0;
    const linesToProcess = activeSession.lines.map((l) => {
      const textLower = l.text.toLowerCase();
      let matchIdx = textLower.indexOf(q);
      let matchesInLine = 0;
      while (matchIdx !== -1) {
        matchesInLine++;
        matchIdx = textLower.indexOf(q, matchIdx + q.length);
      }
      count += matchesInLine;
      return { ...l, hasMatch: matchesInLine > 0 };
    });

    const displayLines = filterOnlyMatches
      ? linesToProcess.filter((l) => l.hasMatch)
      : linesToProcess;

    return { filteredLines: displayLines, matchCount: count };
  }, [activeSession.lines, searchQuery, filterOnlyMatches]);

  // Highlight matches within a line string
  const renderLineTextWithHighlights = (text: string) => {
    if (!searchQuery.trim()) return text;

    const q = searchQuery.trim();
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let keyIdx = 0;

    while (remaining) {
      const lower = remaining.toLowerCase();
      const matchIndex = lower.indexOf(q.toLowerCase());
      if (matchIndex === -1) {
        parts.push(remaining);
        break;
      }
      if (matchIndex > 0) {
        parts.push(remaining.substring(0, matchIndex));
      }
      const matchedSnippet = remaining.substring(matchIndex, matchIndex + q.length);
      parts.push(
        <mark
          key={keyIdx++}
          className="bg-amber-400 text-slate-950 font-bold px-0.5 rounded-sm shadow-sm"
        >
          {matchedSnippet}
        </mark>
      );
      remaining = remaining.substring(matchIndex + q.length);
    }

    return parts;
  };

  return (
    <div
      style={{
        backgroundColor: currentPalette.bg,
        color: currentPalette.fg,
      }}
      className="flex-1 flex flex-col h-full font-mono text-xs overflow-hidden select-text transition-colors duration-200"
    >
      {/* Terminal Tab Bar */}
      <div
        style={{
          backgroundColor: currentPalette.tabBg,
          borderColor: currentPalette.border,
        }}
        className="h-9 border-b px-2 flex items-center justify-between shrink-0 select-none"
      >
        {/* Left: Tab Sessions List */}
        <div className="flex items-center gap-1 overflow-x-auto py-0.5">
          {sessions.map((sess) => {
            const isActive = sess.id === activeSessionId;
            return (
              <div
                key={sess.id}
                onClick={() => setActiveSessionId(sess.id)}
                style={{
                  backgroundColor: isActive ? currentPalette.activeTabBg : 'transparent',
                  borderColor: isActive ? currentPalette.border : 'transparent',
                  color: isActive ? currentPalette.command : currentPalette.fg,
                }}
                className={`group flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] cursor-pointer transition-all border ${
                  isActive ? 'font-semibold shadow-sm' : 'opacity-70 hover:opacity-100'
                }`}
                title={sess.title}
              >
                {/* Status Dot */}
                <span
                  style={{
                    backgroundColor:
                      sess.status === 'running' ? currentPalette.prompt : '#64748b',
                  }}
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    sess.status === 'running' ? 'animate-pulse' : ''
                  }`}
                />

                <TerminalIcon className="w-3 h-3 shrink-0" />
                <span className="truncate max-w-[130px]">{sess.title}</span>

                {/* Close Tab Button */}
                {sessions.length > 1 && (
                  <button
                    type="button"
                    onClick={(e) => handleCloseSession(sess.id, e)}
                    title="Close session"
                    className="p-0.5 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800/60 transition-colors ml-0.5"
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                )}
              </div>
            );
          })}

          {/* Plus button to Add Tab */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowNewTabMenu(!showNewTabMenu)}
              title="Open New Terminal Shell Session"
              className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex items-center"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>

            {showNewTabMenu && (
              <div
                style={{
                  backgroundColor: currentPalette.statusBarBg,
                  borderColor: currentPalette.border,
                }}
                className="absolute left-0 top-full mt-1 w-36 py-1 rounded-lg border shadow-xl z-50 text-[11px] font-sans"
              >
                <button
                  onClick={() => handleAddNewSession('bash')}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/10 text-slate-200 flex items-center gap-2"
                >
                  <TerminalIcon className="w-3 h-3 text-cyan-400" />
                  <span>bash</span>
                </button>
                <button
                  onClick={() => handleAddNewSession('zsh')}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/10 text-slate-200 flex items-center gap-2"
                >
                  <TerminalIcon className="w-3 h-3 text-blue-400" />
                  <span>zsh</span>
                </button>
                <button
                  onClick={() => handleAddNewSession('node')}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/10 text-slate-200 flex items-center gap-2"
                >
                  <TerminalIcon className="w-3 h-3 text-emerald-400" />
                  <span>node</span>
                </button>
                <button
                  onClick={() => handleAddNewSession('python')}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/10 text-slate-200 flex items-center gap-2"
                >
                  <TerminalIcon className="w-3 h-3 text-amber-400" />
                  <span>python</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right: Search, Palette Switcher & Quick Controls */}
        <div className="flex items-center gap-1 text-slate-400">
          {/* Search Toggle */}
          <button
            type="button"
            onClick={() => setIsSearchOpen(!isSearchOpen)}
            className={`p-1.5 rounded transition-colors ${
              isSearchOpen || searchQuery
                ? 'bg-blue-600/30 text-cyan-300'
                : 'hover:bg-white/10 text-slate-400 hover:text-white'
            }`}
            title="Search Terminal Output (Ctrl+F)"
          >
            <Search className="w-3.5 h-3.5" />
          </button>

          {/* Quick Theme Selector Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowPaletteMenu(!showPaletteMenu)}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-white/10 text-[10px] text-slate-300 border border-white/10 transition-colors"
              title="Select Terminal ANSI Palette"
            >
              <Palette className="w-3 h-3 text-cyan-400" />
              <span className="hidden sm:inline font-sans">{currentPalette.name}</span>
              <ChevronDown className="w-2.5 h-2.5 opacity-70" />
            </button>

            {showPaletteMenu && (
              <div
                style={{
                  backgroundColor: currentPalette.statusBarBg,
                  borderColor: currentPalette.border,
                }}
                className="absolute right-0 top-full mt-1 w-52 py-1 rounded-xl border shadow-2xl z-50 text-[11px] font-sans"
              >
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-white/10 flex items-center justify-between">
                  <span>Terminal Palettes</span>
                  {onOpenSettings && (
                    <button
                      onClick={() => {
                        setShowPaletteMenu(false);
                        onOpenSettings();
                      }}
                      className="text-cyan-400 hover:underline"
                    >
                      Settings
                    </button>
                  )}
                </div>
                {Object.values(TERMINAL_PALETTES).map((pal) => (
                  <button
                    key={pal.id}
                    onClick={() => {
                      if (onSelectPalette) onSelectPalette(pal.id);
                      setShowPaletteMenu(false);
                    }}
                    className={`w-full text-left px-3 py-1.5 flex items-center justify-between hover:bg-white/10 transition-colors ${
                      paletteId === pal.id ? 'bg-white/15 text-white font-semibold' : 'text-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0 border border-white/20"
                        style={{ backgroundColor: pal.prompt }}
                      />
                      <span>{pal.name}</span>
                    </div>
                    {paletteId === pal.id && <Check className="w-3 h-3 text-cyan-400" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => handleCommand('npm run dev')}
            className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-[10px] text-emerald-400 border border-emerald-500/30 transition-colors"
            title="Restart Dev Server"
          >
            <Play className="w-2.5 h-2.5 fill-current" />
            <span className="hidden sm:inline">Restart</span>
          </button>

          <button
            type="button"
            onClick={handleClearCurrent}
            title="Clear Console Output (Ctrl+L)"
            className="p-1.5 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Terminal Search / Filter Toolbar (Expandable) */}
      {isSearchOpen && (
        <div
          style={{
            backgroundColor: currentPalette.statusBarBg,
            borderColor: currentPalette.border,
          }}
          className="px-3 py-1.5 border-b flex items-center justify-between gap-2 text-xs shrink-0 select-none animate-in slide-in-from-top-1 duration-150"
        >
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative flex-1 flex items-center bg-black/40 rounded-md border border-white/15 px-2 py-1">
              <Search className="w-3.5 h-3.5 text-slate-400 mr-1.5 shrink-0" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search terminal output history..."
                className="bg-transparent text-xs text-white placeholder-slate-500 focus:outline-none w-full font-mono"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-slate-400 hover:text-white"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            {/* Match Counter Badge */}
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                matchCount > 0
                  ? 'bg-amber-400/20 text-amber-300 border border-amber-400/40'
                  : searchQuery
                  ? 'bg-rose-500/20 text-rose-300'
                  : 'bg-white/5 text-slate-400'
              }`}
            >
              {searchQuery
                ? matchCount > 0
                  ? `${matchCount} match${matchCount === 1 ? '' : 'es'}`
                  : 'No matches'
                : 'Type to search'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Filter Lines vs Highlight Only toggle */}
            <button
              onClick={() => setFilterOnlyMatches(!filterOnlyMatches)}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors border ${
                filterOnlyMatches
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'bg-white/5 text-slate-300 border-white/10 hover:bg-white/10'
              }`}
              title="Filter to show only lines with matches"
            >
              <Filter className="w-3 h-3" />
              <span className="hidden sm:inline">Filter Lines</span>
            </button>

            <button
              onClick={() => {
                setIsSearchOpen(false);
                setSearchQuery('');
                setFilterOnlyMatches(false);
              }}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/10"
              title="Close Search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Terminal Log Output Viewport */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1 text-[11px] leading-relaxed">
        {filteredLines.length === 0 ? (
          <div className="text-center py-8 text-slate-500 font-sans italic text-xs">
            {searchQuery
              ? `No lines match "${searchQuery}"`
              : 'Terminal ready. Type a command below.'}
          </div>
        ) : (
          filteredLines.map((l) => {
            let textColor = currentPalette.fg;
            if (l.type === 'step') textColor = currentPalette.step;
            else if (l.type === 'success') textColor = currentPalette.success;
            else if (l.type === 'warn') textColor = currentPalette.warn;
            else if (l.type === 'error') textColor = currentPalette.error;
            else if (l.type === 'command') textColor = currentPalette.command;

            return (
              <div
                key={l.id}
                style={{ color: textColor }}
                className={`leading-normal ${
                  l.type === 'step' || l.type === 'command' ? 'font-bold' : ''
                }`}
              >
                {renderLineTextWithHighlights(l.text)}
              </div>
            );
          })
        )}
        <div ref={terminalEndRef} />
      </div>

      {/* Interactive Command Input Line with History Navigation */}
      <div
        style={{
          backgroundColor: currentPalette.statusBarBg,
          borderColor: currentPalette.border,
        }}
        className="px-3 py-2 border-t flex items-center gap-2 shrink-0"
      >
        <span style={{ color: currentPalette.prompt }} className="font-bold text-xs">
          ➜
        </span>
        <span style={{ color: currentPalette.command }} className="text-[11px] font-semibold">
          {activeSession.cwd}
        </span>
        <span className="text-slate-500 font-sans text-[10px]">git:(main)</span>
        <input
          ref={inputRef}
          type="text"
          value={activeSession.inputVal}
          onChange={(e) => {
            const val = e.target.value;
            setSessions((prev) =>
              prev.map((s) => (s.id === activeSessionId ? { ...s, inputVal: val } : s))
            );
          }}
          onKeyDown={handleKeyDown}
          placeholder={`Type a command... (Use ↑/↓ for history, Enter to run)`}
          className="flex-1 bg-transparent border-none text-[11px] placeholder-slate-500 focus:outline-none font-mono"
          style={{ color: currentPalette.fg }}
        />

        {/* History badge indicator */}
        {activeSession.commandHistory.length > 0 && (
          <span
            title="Press ↑ or ↓ to navigate past commands"
            className="text-[10px] text-slate-500 px-1.5 py-0.5 rounded bg-white/5 hidden md:inline select-none"
          >
            {historyIndex !== -1
              ? `History ${historyIndex + 1}/${activeSession.commandHistory.length}`
              : `↑/↓ History (${activeSession.commandHistory.length})`}
          </span>
        )}
      </div>

      {/* Modern Status Bar displaying CWD, Shell Type, Process Status, Exit Code */}
      <div
        style={{
          backgroundColor: currentPalette.statusBarBg,
          borderColor: currentPalette.border,
        }}
        className="h-6 border-t px-3 flex items-center justify-between text-[11px] font-mono select-none shrink-0"
      >
        {/* Left indicators: CWD & Shell */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-slate-300">
            <Folder className="w-3 h-3 text-cyan-400" />
            <span className="font-semibold text-cyan-300">/{activeSession.cwd}</span>
          </div>

          <span className="text-slate-600">|</span>

          <div className="flex items-center gap-1 text-slate-400">
            <TerminalIcon className="w-3 h-3 text-emerald-400" />
            <span className="uppercase text-[10px] font-semibold text-slate-300">
              {activeSession.type}
            </span>
          </div>

          <span className="text-slate-600">|</span>

          {/* Active Process / Task indicator */}
          <div className="flex items-center gap-1.5">
            <span
              style={{
                backgroundColor:
                  activeSession.status === 'running' ? currentPalette.prompt : '#64748b',
              }}
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                activeSession.status === 'running' ? 'animate-ping' : ''
              }`}
            />
            <span
              style={{
                color:
                  activeSession.status === 'running' ? currentPalette.prompt : currentPalette.fg,
              }}
              className="font-medium text-[10px]"
            >
              {activeSession.status === 'running' ? 'Active:' : 'Status:'}{' '}
              {activeSession.activeTaskName || 'idle'}
            </span>
          </div>
        </div>

        {/* Right indicators: Last Exit Code, Theme Name, Uptime */}
        <div className="flex items-center gap-3 text-slate-400">
          <div className="flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span className="text-[10px]">exit {activeSession.lastExitCode ?? 0}</span>
          </div>

          <span className="text-slate-600">|</span>

          <div className="flex items-center gap-1 text-[10px]">
            <Activity className="w-3 h-3 text-cyan-400" />
            <span>{activeSession.duration || '0.04s'}</span>
          </div>

          <span className="text-slate-600">|</span>

          {/* Active Palette Name */}
          <div
            onClick={() => setShowPaletteMenu(!showPaletteMenu)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-white/10 cursor-pointer text-[10px] transition-colors"
            title="Change ANSI Palette"
          >
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: currentPalette.command }}
            />
            <span className="text-slate-300 font-sans">{currentPalette.name}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
