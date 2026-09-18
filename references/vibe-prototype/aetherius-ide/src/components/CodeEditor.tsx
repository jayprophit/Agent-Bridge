import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  FileCode2,
  Copy,
  Check,
  Play,
  Save,
  Search,
  X,
  Clock,
  CheckCircle2,
  Loader2,
  Sparkles,
  Edit3,
  Eye,
  GitBranch,
  AlertCircle,
  FileText,
  Folder,
  Code,
  ChevronRight,
  ChevronDown,
  FolderOpen,
  ArrowUp
} from 'lucide-react';
import { FileItem, ThemeType } from '../types';

export interface CodeEditorProps {
  files: FileItem[];
  activeFilePath: string;
  onSelectFile: (path: string) => void;
  onCodeChange?: (path: string, content: string) => void;
  onRunCode?: () => void;
  theme?: ThemeType;
}

export const SYNTAX_THEMES: Record<
  ThemeType,
  {
    name: string;
    paletteLabel: string;
    editorBg: string;
    editorText: string;
    headerBg: string;
    tabActive: string;
    tabInactive: string;
    gutterBg: string;
    gutterText: string;
    border: string;
    statusBarBg: string;
    keyword: string;
    type: string;
    string: string;
    number: string;
    comment: string;
    fn: string;
    operator: string;
    variable: string;
    activeLineBg: string;
    badgeBg: string;
    badgeText: string;
  }
> = {
  dark: {
    name: 'One Dark Pro',
    paletteLabel: 'Dark • One Dark Pro',
    editorBg: 'bg-[#0d1117]',
    editorText: 'text-slate-200',
    headerBg: 'bg-slate-950',
    tabActive: 'bg-[#0d1117] border-blue-500 text-white shadow-sm',
    tabInactive: 'border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-200',
    gutterBg: 'bg-[#090d13]',
    gutterText: 'text-slate-600',
    border: 'border-slate-800',
    statusBarBg: 'bg-slate-950',
    keyword: '#c678dd',
    type: '#4ec9b0',
    string: '#98c379',
    number: '#d19a66',
    comment: '#6b7280',
    fn: '#61afef',
    operator: '#e5c07b',
    variable: '#e06c75',
    activeLineBg: 'bg-slate-900/40',
    badgeBg: 'bg-blue-500/15',
    badgeText: 'text-blue-400',
  },
  'dark-light': {
    name: 'Charcoal Modern',
    paletteLabel: 'Dark Light • Charcoal Slate',
    editorBg: 'bg-[#181e29]',
    editorText: 'text-slate-100',
    headerBg: 'bg-[#10141c]',
    tabActive: 'bg-[#181e29] border-sky-400 text-white shadow-sm',
    tabInactive: 'border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200',
    gutterBg: 'bg-[#131720]',
    gutterText: 'text-slate-500',
    border: 'border-slate-700/80',
    statusBarBg: 'bg-[#10141c]',
    keyword: '#f472b6',
    type: '#38bdf8',
    string: '#34d399',
    number: '#fbbf24',
    comment: '#64748b',
    fn: '#818cf8',
    operator: '#cbd5e1',
    variable: '#f87171',
    activeLineBg: 'bg-slate-800/50',
    badgeBg: 'bg-sky-500/15',
    badgeText: 'text-sky-400',
  },
  light: {
    name: 'GitHub Light',
    paletteLabel: 'Light • GitHub Light',
    editorBg: 'bg-[#f8fafc]',
    editorText: 'text-slate-900',
    headerBg: 'bg-slate-200/90',
    tabActive: 'bg-[#f8fafc] border-blue-600 text-slate-900 shadow-sm font-semibold',
    tabInactive: 'border-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900',
    gutterBg: 'bg-slate-100',
    gutterText: 'text-slate-400',
    border: 'border-slate-300',
    statusBarBg: 'bg-slate-200',
    keyword: '#9333ea',
    type: '#0284c7',
    string: '#16a34a',
    number: '#ea580c',
    comment: '#64748b',
    fn: '#2563eb',
    operator: '#475569',
    variable: '#dc2626',
    activeLineBg: 'bg-slate-200/60',
    badgeBg: 'bg-blue-100',
    badgeText: 'text-blue-700',
  },
  white: {
    name: 'Minimalist Monochrome',
    paletteLabel: 'White • Clean Paper',
    editorBg: 'bg-[#ffffff]',
    editorText: 'text-neutral-900',
    headerBg: 'bg-neutral-100',
    tabActive: 'bg-[#ffffff] border-neutral-800 text-neutral-900 shadow-sm font-semibold',
    tabInactive: 'border-transparent text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900',
    gutterBg: 'bg-neutral-50',
    gutterText: 'text-neutral-400',
    border: 'border-neutral-200',
    statusBarBg: 'bg-neutral-100',
    keyword: '#7c3aed',
    type: '#0891b2',
    string: '#059669',
    number: '#d97706',
    comment: '#94a3b8',
    fn: '#1d4ed8',
    operator: '#334155',
    variable: '#e11d48',
    activeLineBg: 'bg-neutral-100/80',
    badgeBg: 'bg-neutral-200',
    badgeText: 'text-neutral-800',
  },
  aurora: {
    name: 'Aurora Cyberpunk',
    paletteLabel: 'Aurora • Neon Cyan',
    editorBg: 'bg-[#06141d]',
    editorText: 'text-cyan-100',
    headerBg: 'bg-[#040e15]',
    tabActive: 'bg-[#06141d] border-cyan-400 text-cyan-200 shadow-[0_0_10px_rgba(6,182,212,0.3)]',
    tabInactive: 'border-transparent text-cyan-700 hover:bg-[#081b27] hover:text-cyan-300',
    gutterBg: 'bg-[#030b11]',
    gutterText: 'text-cyan-800',
    border: 'border-cyan-950',
    statusBarBg: 'bg-[#040e15]',
    keyword: '#06b6d4',
    type: '#2dd4bf',
    string: '#a7f3d0',
    number: '#f43f5e',
    comment: '#155e75',
    fn: '#38bdf8',
    operator: '#67e8f9',
    variable: '#ec4899',
    activeLineBg: 'bg-cyan-950/40',
    badgeBg: 'bg-cyan-500/20',
    badgeText: 'text-cyan-300',
  },
  amber: {
    name: 'CRT Amber Phosphor',
    paletteLabel: 'Amber • CRT Terminal',
    editorBg: 'bg-[#120d04]',
    editorText: 'text-amber-100',
    headerBg: 'bg-[#0d0902]',
    tabActive: 'bg-[#120d04] border-amber-500 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.3)]',
    tabInactive: 'border-transparent text-amber-700 hover:bg-[#1a1306] hover:text-amber-300',
    gutterBg: 'bg-[#0a0701]',
    gutterText: 'text-amber-900',
    border: 'border-amber-950',
    statusBarBg: 'bg-[#0d0902]',
    keyword: '#f59e0b',
    type: '#fbbf24',
    string: '#fde68a',
    number: '#fef08a',
    comment: '#92400e',
    fn: '#d97706',
    operator: '#fcd34d',
    variable: '#ea580c',
    activeLineBg: 'bg-amber-950/30',
    badgeBg: 'bg-amber-500/20',
    badgeText: 'text-amber-300',
  },
  frosted: {
    name: 'Frosted Glass Indigo',
    paletteLabel: 'Frosted • Translucent Indigo',
    editorBg: 'bg-[#0f172a]',
    editorText: 'text-slate-100',
    headerBg: 'bg-slate-950/90',
    tabActive: 'bg-[#0f172a] border-indigo-400 text-white shadow-sm',
    tabInactive: 'border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-200',
    gutterBg: 'bg-slate-950/70',
    gutterText: 'text-slate-600',
    border: 'border-slate-800/80',
    statusBarBg: 'bg-slate-950/90',
    keyword: '#818cf8',
    type: '#a5b4fc',
    string: '#6ee7b7',
    number: '#fde047',
    comment: '#64748b',
    fn: '#67e8f9',
    operator: '#c7d2fe',
    variable: '#f472b6',
    activeLineBg: 'bg-indigo-950/30',
    badgeBg: 'bg-indigo-500/20',
    badgeText: 'text-indigo-300',
  },
};

export const CodeEditor: React.FC<CodeEditorProps> = ({
  files,
  activeFilePath,
  onSelectFile,
  onCodeChange,
  onRunCode,
  theme = 'dark',
}) => {
  const [copied, setCopied] = useState(false);
  const [openTabs, setOpenTabs] = useState<string[]>([
    '/src/components/TaskList.tsx',
    '/src/components/KanbanBoard.tsx',
    '/src/hooks/useTasks.ts',
    '/src/types.ts',
  ]);

  // Editor mode: 'edit' or 'highlight'
  const [editorMode, setEditorMode] = useState<'edit' | 'highlight'>('edit');

  // Search & Filter files in directory
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Debounced Auto-Save States
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved');
  const [lastSavedTime, setLastSavedTime] = useState<string>(
    new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  );
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);

  // File Breadcrumb Dropdown State & Click-outside ref
  const [activeBreadcrumbDropdown, setActiveBreadcrumbDropdown] = useState<string | null>(null);
  const breadcrumbContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        breadcrumbContainerRef.current &&
        !breadcrumbContainerRef.current.contains(e.target as Node)
      ) {
        setActiveBreadcrumbDropdown(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Compute structured breadcrumb segments from activeFilePath
  const breadcrumbSegments = useMemo(() => {
    const rawParts = activeFilePath.split('/').filter(Boolean);
    const segments: { name: string; fullPath: string; isFolder: boolean }[] = [
      { name: 'workspace', fullPath: '/', isFolder: true },
    ];

    let runningPath = '';
    for (let i = 0; i < rawParts.length; i++) {
      runningPath += '/' + rawParts[i];
      const isFile = i === rawParts.length - 1;
      segments.push({
        name: rawParts[i],
        fullPath: runningPath,
        isFolder: !isFile,
      });
    }
    return segments;
  }, [activeFilePath]);

  // Helper to retrieve contents of a folder path from files tree
  const getFolderItems = (targetPath: string): FileItem[] => {
    if (!targetPath || targetPath === '/' || targetPath === 'workspace') {
      return files;
    }
    const findFolder = (list: FileItem[]): FileItem | null => {
      for (const item of list) {
        if (item.type === 'folder') {
          if (item.path === targetPath) return item;
          if (item.children) {
            const match = findFolder(item.children);
            if (match) return match;
          }
        }
      }
      return null;
    };
    const folder = findFolder(files);
    return folder?.children || [];
  };

  // Helper to navigate back up to parent directory
  const handleNavigateUp = () => {
    const parts = activeFilePath.split('/').filter(Boolean);
    if (parts.length <= 1) return;
    parts.pop(); // remove current file
    const parentPath = '/' + parts.join('/');
    const siblingItems = getFolderItems(parentPath);
    const firstFile = siblingItems.find((item) => item.type === 'file');
    if (firstFile) {
      onSelectFile(firstFile.path);
    }
  };

  // Helper to recursively flatten all project files
  const allProjectFiles = useMemo(() => {
    const list: FileItem[] = [];
    const traverse = (items: FileItem[]) => {
      for (const item of items) {
        if (item.type === 'file') {
          list.push(item);
        }
        if (item.children) {
          traverse(item.children);
        }
      }
    };
    traverse(files);
    return list;
  }, [files]);

  // Filtered files for search bar
  const filteredFiles = useMemo(() => {
    if (!searchQuery.trim()) return allProjectFiles;
    const q = searchQuery.toLowerCase();
    return allProjectFiles.filter(
      (f) => f.name.toLowerCase().includes(q) || f.path.toLowerCase().includes(q)
    );
  }, [searchQuery, allProjectFiles]);

  // Find active file
  const findFileByPath = (items: FileItem[], path: string): FileItem | null => {
    for (const item of items) {
      if (item.path === path) return item;
      if (item.children) {
        const found = findFileByPath(item.children, path);
        if (found) return found;
      }
    }
    return null;
  };

  const activeFile = findFileByPath(files, activeFilePath) || {
    name: 'TaskList.tsx',
    path: '/src/components/TaskList.tsx',
    type: 'file',
    language: 'typescript',
    content: `// Select a file to view code`,
  };

  const [currentCode, setCurrentCode] = useState(activeFile.content || '');

  // Keep code state synced when activeFilePath changes
  useEffect(() => {
    const file = findFileByPath(files, activeFilePath);
    if (file && file.content !== undefined) {
      // Check localStorage for persisted unsaved draft if any
      const cached = localStorage.getItem(`aetherius_file_${activeFilePath}`);
      setCurrentCode(cached !== null ? cached : file.content);
      setSaveStatus('saved');
      if (!openTabs.includes(file.path)) {
        setOpenTabs((prev) => [...prev, file.path]);
      }
    }
  }, [activeFilePath, files]);

  // Close search dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Keyboard shortcut ⌘P to open file search, ⌘S to save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = (e.key || '').toLowerCase();
      if ((e.metaKey || e.ctrlKey) && key === 'p') {
        e.preventDefault();
        setIsSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
      if ((e.metaKey || e.ctrlKey) && key === 's') {
        e.preventDefault();
        triggerImmediateSave();
      }
      if (e.key === 'Escape') {
        setIsSearchOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentCode, activeFilePath]);

  // Immediate Save helper
  const triggerImmediateSave = () => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    setSaveStatus('saving');
    // Persist to local state & storage
    try {
      localStorage.setItem(`aetherius_file_${activeFilePath}`, currentCode);
    } catch {
      // ignore storage errors
    }
    if (onCodeChange) {
      onCodeChange(activeFilePath, currentCode);
    }
    setTimeout(() => {
      setSaveStatus('saved');
      setLastSavedTime(
        new Date().toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      );
    }, 400);
  };

  // Debounced Auto-Save Handler: triggers save 3 seconds after typing
  const handleCodeInput = (newVal: string) => {
    setCurrentCode(newVal);
    setSaveStatus('unsaved');

    // Reset the 3-second debounced timer
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    autoSaveTimerRef.current = setTimeout(() => {
      setSaveStatus('saving');
      try {
        localStorage.setItem(`aetherius_file_${activeFilePath}`, newVal);
      } catch {
        // ignore
      }
      if (onCodeChange) {
        onCodeChange(activeFilePath, newVal);
      }
      setTimeout(() => {
        setSaveStatus('saved');
        setLastSavedTime(
          new Date().toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })
        );
      }, 350);
    }, 3000); // 3000ms debounced auto-save as requested
  };

  // Copy code to clipboard
  const handleCopy = () => {
    navigator.clipboard.writeText(currentCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Close a file tab
  const handleCloseTab = (e: React.MouseEvent, path: string) => {
    e.stopPropagation();
    const updated = openTabs.filter((t) => t !== path);
    setOpenTabs(updated);
    if (path === activeFilePath && updated.length > 0) {
      onSelectFile(updated[updated.length - 1]);
    }
  };

  // Select file from search dropdown
  const handleOpenFile = (path: string) => {
    onSelectFile(path);
    if (!openTabs.includes(path)) {
      setOpenTabs((prev) => [...prev, path]);
    }
    setIsSearchOpen(false);
    setSearchQuery('');
  };

  // Current syntax palette configuration
  const currentPalette = SYNTAX_THEMES[theme] || SYNTAX_THEMES.dark;

  // Syntax colorizer with custom theme palette
  const renderHighlightedLines = (code: string) => {
    const lines = code.split('\n');
    return lines.map((line, idx) => {
      const lineNum = idx + 1;
      const isAdded =
        line.includes('crypto.randomUUID') ||
        line.includes('KanbanBoard') ||
        line.includes('useTasks');

      return (
        <div
          key={idx}
          className={`flex items-start hover:${currentPalette.activeLineBg} px-3 font-mono text-xs leading-6 ${
            isAdded ? 'border-l-2 border-emerald-500 bg-emerald-500/5' : ''
          }`}
        >
          <span
            className={`w-10 text-right pr-4 ${currentPalette.gutterText} select-none shrink-0 font-mono text-[11px]`}
          >
            {lineNum}
          </span>
          <span className={`${currentPalette.editorText} whitespace-pre overflow-x-auto`}>
            {highlightSyntaxWithPalette(line, currentPalette)}
          </span>
        </div>
      );
    });
  };

  const highlightSyntaxWithPalette = (
    line: string,
    palette: typeof SYNTAX_THEMES['dark']
  ) => {
    const words = line.split(/(\s+|[(),{};[\].<>:=])/);
    return words.map((token, i) => {
      if (
        [
          'import',
          'export',
          'default',
          'function',
          'const',
          'let',
          'var',
          'return',
          'if',
          'else',
          'type',
          'interface',
          'from',
          'as',
          'new',
          'async',
          'await',
        ].includes(token)
      ) {
        return (
          <span key={i} style={{ color: palette.keyword }} className="font-semibold">
            {token}
          </span>
        );
      }
      if (
        [
          'string',
          'boolean',
          'number',
          'any',
          'void',
          'React',
          'FC',
          'Task',
          'TaskItem',
          'TaskStatus',
          'Filter',
          'Props',
        ].includes(token)
      ) {
        return (
          <span key={i} style={{ color: palette.type }}>
            {token}
          </span>
        );
      }
      if (['true', 'false', 'null', 'undefined'].includes(token) || /^\d+$/.test(token)) {
        return (
          <span key={i} style={{ color: palette.number }} className="font-medium">
            {token}
          </span>
        );
      }
      if (token.startsWith('"') || token.startsWith("'") || token.startsWith('`')) {
        return (
          <span key={i} style={{ color: palette.string }}>
            {token}
          </span>
        );
      }
      if (token.startsWith('//')) {
        return (
          <span key={i} style={{ color: palette.comment }} className="italic">
            {token}
          </span>
        );
      }
      if (
        [
          'useState',
          'useEffect',
          'useTasks',
          'useMemo',
          'useRef',
          'useCallback',
          'addTask',
          'updateTask',
          'deleteTask',
        ].includes(token)
      ) {
        return (
          <span key={i} style={{ color: palette.fn }} className="font-medium">
            {token}
          </span>
        );
      }
      return token;
    });
  };

  // Line count for editor gutter
  const lineCount = currentCode.split('\n').length;

  return (
    <div
      id="code-editor-root"
      className={`flex-1 flex flex-col h-full ${currentPalette.editorBg} ${currentPalette.editorText} select-text overflow-hidden`}
    >
      {/* Tab bar and Header controls */}
      <div
        className={`h-11 ${currentPalette.headerBg} border-b ${currentPalette.border} flex items-center justify-between px-2 select-none shrink-0 gap-2`}
      >
        {/* Open File Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto flex-1 py-1">
          {openTabs.map((tabPath) => {
            const fileName = tabPath.split('/').pop() || tabPath;
            const isActive = tabPath === activeFilePath;
            return (
              <div
                key={tabPath}
                onClick={() => onSelectFile(tabPath)}
                className={`group flex items-center gap-2 px-3 py-1.5 rounded-t-lg text-xs font-mono cursor-pointer border-t-2 transition-all whitespace-nowrap ${
                  isActive ? currentPalette.tabActive : currentPalette.tabInactive
                }`}
              >
                <FileCode2 className="w-3.5 h-3.5 text-blue-400" />
                <span>{fileName}</span>
                {isActive && saveStatus === 'unsaved' && (
                  <span
                    className="w-2 h-2 rounded-full bg-amber-400 animate-pulse ml-0.5"
                    title="Unsaved changes"
                  />
                )}
                {isActive && saveStatus === 'saved' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 ml-0.5" />
                )}
                <button
                  onClick={(e) => handleCloseTab(e, tabPath)}
                  className="p-0.5 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Search Bar & Auto-Save status & Quick Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Quick File Search in Directory Header */}
          <div className="relative" ref={searchContainerRef}>
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs transition-all ${
                isSearchOpen
                  ? 'bg-slate-900 border-blue-500 ring-1 ring-blue-500'
                  : 'bg-slate-900/80 border-slate-800 hover:border-slate-700 text-slate-400'
              }`}
            >
              <Search className="w-3.5 h-3.5 text-slate-400" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onFocus={() => setIsSearchOpen(true)}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setIsSearchOpen(true);
                }}
                placeholder="Filter files... (⌘P)"
                className="bg-transparent text-xs text-slate-200 placeholder-slate-500 focus:outline-none w-28 sm:w-36 font-mono"
              />
              {searchQuery && (
                <button
                  onClick={() => {
                    setSearchQuery('');
                    searchInputRef.current?.focus();
                  }}
                  className="text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            {/* Quick File Search Dropdown Results */}
            {isSearchOpen && (
              <div className="absolute right-0 top-full mt-1.5 w-72 max-h-80 overflow-y-auto rounded-xl bg-slate-900 border border-slate-700 shadow-2xl z-50 p-1.5 space-y-1">
                <div className="px-2 py-1 text-[10px] font-mono text-slate-400 border-b border-slate-800 flex items-center justify-between">
                  <span>Project Files ({filteredFiles.length})</span>
                  <span>ESC to close</span>
                </div>
                {filteredFiles.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-500">
                    No files matching "{searchQuery}"
                  </div>
                ) : (
                  filteredFiles.map((f) => {
                    const isCurrent = f.path === activeFilePath;
                    return (
                      <button
                        key={f.path}
                        onClick={() => handleOpenFile(f.path)}
                        className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-left text-xs font-mono transition-colors ${
                          isCurrent
                            ? 'bg-blue-600/20 text-cyan-300 border border-blue-500/30'
                            : 'hover:bg-slate-800 text-slate-300'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <FileCode2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                          <div className="truncate">
                            <div className="font-semibold truncate">{f.name}</div>
                            <div className="text-[10px] text-slate-500 truncate">
                              {f.path}
                            </div>
                          </div>
                        </div>
                        {isCurrent && (
                          <span className="text-[10px] text-blue-400 font-sans font-semibold">
                            Open
                          </span>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>

          {/* Debounced Auto-Save Indicator */}
          <div
            onClick={triggerImmediateSave}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/80 border border-slate-800 text-[11px] font-mono cursor-pointer hover:border-slate-700 transition-colors"
            title="Click or press ⌘S to save immediately"
          >
            {saveStatus === 'saving' && (
              <>
                <Loader2 className="w-3 h-3 text-cyan-400 animate-spin" />
                <span className="text-cyan-400 hidden sm:inline">Saving...</span>
              </>
            )}
            {saveStatus === 'saved' && (
              <>
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span className="text-emerald-400 hidden sm:inline">Saved</span>
              </>
            )}
            {saveStatus === 'unsaved' && (
              <>
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                <span className="text-amber-400 hidden sm:inline">Auto-save (3s)</span>
              </>
            )}
          </div>

          {/* Mode Switcher: Live Edit vs Highlighted */}
          <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-xs">
            <button
              onClick={() => setEditorMode('edit')}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                editorMode === 'edit'
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Interactive Live Code Editor with Auto-Save"
            >
              <Edit3 className="w-3 h-3" />
              <span>Edit</span>
            </button>
            <button
              onClick={() => setEditorMode('highlight')}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                editorMode === 'highlight'
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Syntax Highlighted View"
            >
              <Eye className="w-3 h-3" />
              <span>Syntax</span>
            </button>
          </div>

          {/* Run Code Button */}
          {onRunCode && (
            <button
              onClick={onRunCode}
              title="Run in Sandbox Preview"
              className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 border border-emerald-500/40 text-xs font-medium transition-colors"
            >
              <Play className="w-3 h-3 fill-current" />
              <span className="hidden sm:inline">Run</span>
            </button>
          )}

          {/* Copy Code */}
          <button
            onClick={handleCopy}
            title="Copy Code"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Interactive File Breadcrumb Bar */}
      <div
        ref={breadcrumbContainerRef}
        className={`px-3 py-1.5 ${currentPalette.headerBg} border-b ${currentPalette.border} text-[11px] font-mono text-slate-400 flex items-center justify-between select-none shrink-0 relative z-30`}
      >
        {/* Left: Breadcrumbs path with clickable folder depth & dropdowns */}
        <div className="flex items-center gap-1 overflow-x-auto py-0.5">
          {/* Quick Navigate Back to Parent Folder Button */}
          {breadcrumbSegments.length > 2 && (
            <button
              onClick={handleNavigateUp}
              title="Navigate up to parent directory"
              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-cyan-400 mr-1 transition-colors flex items-center gap-1"
            >
              <ArrowUp className="w-3 h-3" />
            </button>
          )}

          {breadcrumbSegments.map((seg, idx) => {
            const isLast = idx === breadcrumbSegments.length - 1;
            const isDropdownOpen = activeBreadcrumbDropdown === seg.fullPath;
            const folderItems = seg.isFolder ? getFolderItems(seg.fullPath) : [];

            return (
              <div key={seg.fullPath} className="relative flex items-center">
                {idx > 0 && (
                  <ChevronRight className="w-3 h-3 text-slate-600 mx-0.5 shrink-0" />
                )}

                <button
                  type="button"
                  onClick={() => {
                    if (seg.isFolder) {
                      setActiveBreadcrumbDropdown(isDropdownOpen ? null : seg.fullPath);
                    }
                  }}
                  className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors ${
                    isLast
                      ? 'text-cyan-300 font-semibold bg-slate-900/60 border border-slate-800'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 cursor-pointer'
                  }`}
                  title={seg.isFolder ? `Click to browse files in ${seg.name}` : seg.fullPath}
                >
                  {seg.isFolder ? (
                    isDropdownOpen ? (
                      <FolderOpen className="w-3 h-3 text-blue-400" />
                    ) : (
                      <Folder className="w-3 h-3 text-blue-400" />
                    )
                  ) : (
                    <FileCode2 className="w-3 h-3 text-cyan-400" />
                  )}
                  <span>{seg.name}</span>
                  {seg.isFolder && (
                    <ChevronDown className="w-2.5 h-2.5 text-slate-500 ml-0.5" />
                  )}
                </button>

                {/* Sibling items Dropdown when folder clicked */}
                {isDropdownOpen && seg.isFolder && (
                  <div className="absolute left-0 top-full mt-1 w-56 max-h-64 overflow-y-auto rounded-xl bg-slate-900 border border-slate-700 shadow-2xl z-50 p-1.5 space-y-0.5">
                    <div className="px-2 py-1 text-[10px] font-mono text-slate-400 border-b border-slate-800 flex items-center justify-between">
                      <span className="truncate">{seg.name} directory</span>
                      <span>{folderItems.length} items</span>
                    </div>

                    {folderItems.length === 0 ? (
                      <div className="p-2 text-center text-xs text-slate-500">
                        No files in folder
                      </div>
                    ) : (
                      folderItems.map((item) => {
                        const isCurrentActive = item.path === activeFilePath;
                        return (
                          <button
                            key={item.path}
                            onClick={() => {
                              if (item.type === 'file') {
                                onSelectFile(item.path);
                                setActiveBreadcrumbDropdown(null);
                              } else {
                                setActiveBreadcrumbDropdown(item.path);
                              }
                            }}
                            className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-left text-xs font-mono transition-colors ${
                              isCurrentActive
                                ? 'bg-blue-600/20 text-cyan-300 border border-blue-500/30'
                                : 'hover:bg-slate-800 text-slate-300'
                            }`}
                          >
                            <div className="flex items-center gap-1.5 min-w-0">
                              {item.type === 'folder' ? (
                                <Folder className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                              ) : (
                                <FileCode2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                              )}
                              <span className="truncate">{item.name}</span>
                            </div>
                            {item.type === 'folder' && (
                              <ChevronRight className="w-3 h-3 text-slate-500" />
                            )}
                            {isCurrentActive && (
                              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                            )}
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right: Active Syntax Palette Badge & File Metadata */}
        <div className="flex items-center gap-2 text-[10px] shrink-0 ml-2">
          <span
            className={`px-2 py-0.5 rounded-full font-mono font-medium ${currentPalette.badgeBg} ${currentPalette.badgeText}`}
          >
            Palette: {currentPalette.name}
          </span>
          <span className="text-slate-500 hidden sm:inline">TypeScript JSX</span>
          <span className="text-slate-500 hidden sm:inline">UTF-8</span>
        </div>
      </div>

      {/* Code Viewport: Live Editor or Syntax Highlighted */}
      <div className="flex-1 overflow-hidden relative flex">
        {editorMode === 'edit' ? (
          /* Live Interactive Code Textarea with line numbers */
          <div className="flex-1 flex overflow-hidden relative font-mono text-xs">
            {/* Gutter Line Numbers */}
            <div
              className={`w-12 ${currentPalette.gutterBg} ${currentPalette.gutterText} py-3 select-none text-right pr-3 font-mono shrink-0 overflow-hidden leading-6 border-r ${currentPalette.border}`}
            >
              {Array.from({ length: lineCount }).map((_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>

            {/* Editable Textarea */}
            <textarea
              value={currentCode}
              onChange={(e) => handleCodeInput(e.target.value)}
              onKeyDown={(e) => {
                // Support Tab key indentation
                if (e.key === 'Tab') {
                  e.preventDefault();
                  const target = e.target as HTMLTextAreaElement;
                  const start = target.selectionStart;
                  const end = target.selectionEnd;
                  const newVal = currentCode.substring(0, start) + '  ' + currentCode.substring(end);
                  handleCodeInput(newVal);
                  setTimeout(() => {
                    target.selectionStart = target.selectionEnd = start + 2;
                  }, 0);
                }
              }}
              spellCheck={false}
              className={`flex-1 p-3 bg-transparent ${currentPalette.editorText} resize-none focus:outline-none font-mono leading-6 whitespace-pre overflow-auto`}
              placeholder="// Write or edit your code here... Changes auto-save every 3 seconds"
            />
          </div>
        ) : (
          /* Read-only High-fidelity Syntax Highlighted View */
          <div className="flex-1 overflow-auto py-3">{renderHighlightedLines(currentCode)}</div>
        )}
      </div>

      {/* Bottom Status Bar */}
      <div
        className={`h-6 ${currentPalette.statusBarBg} border-t ${currentPalette.border} px-3 flex items-center justify-between text-[11px] font-mono text-slate-400 select-none shrink-0`}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1 text-slate-300">
            <GitBranch className="w-3 h-3 text-cyan-400" />
            <span>main</span>
          </div>

          <div className="flex items-center gap-1.5">
            {saveStatus === 'saved' ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                <span>Auto-saved at {lastSavedTime}</span>
              </span>
            ) : saveStatus === 'saving' ? (
              <span className="text-cyan-400 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Auto-saving changes...</span>
              </span>
            ) : (
              <span className="text-amber-400 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>Unsaved changes • Saving in 3s</span>
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <span>Lines: {lineCount}</span>
          <span>Spaces: 2</span>
          <span className="text-cyan-400">{currentPalette.name}</span>
        </div>
      </div>
    </div>
  );
};
