import React, { useState } from 'react';
import {
  Files,
  Search,
  GitBranch,
  PlayCircle,
  Boxes,
  Settings,
  ChevronRight,
  ChevronDown,
  FileCode2,
  Folder,
  FolderOpen,
  Plus,
  RefreshCw,
  MoreVertical,
  X,
  FilePlus,
  FolderPlus,
  Check,
  Play,
  RotateCcw,
  Bug,
  Package,
  Layers,
  Sparkles
} from 'lucide-react';
import { FileItem } from '../types';

export type VSCodeView = 'explorer' | 'search' | 'source-control' | 'debug' | 'extensions';

interface VSCodeSidePanelProps {
  files: FileItem[];
  activeFilePath: string;
  projectName?: string;
  onSelectFile: (path: string) => void;
  onOpenFileSearch?: () => void;
  onOpenNewProjectModal?: () => void;
  onSelectTab?: (tab: string) => void;
}

export const VSCodeSidePanel: React.FC<VSCodeSidePanelProps> = ({
  files,
  activeFilePath,
  projectName = 'TASK-MANAGER-APP',
  onSelectFile,
  onOpenFileSearch,
  onOpenNewProjectModal,
  onSelectTab,
}) => {
  const [activeView, setActiveView] = useState<VSCodeView>('explorer');
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({
    '/src': true,
    '/src/components': true,
    '/src/hooks': true,
    '/docs': true,
  });

  // Explorer sections collapsible state
  const [openEditorsExpanded, setOpenEditorsExpanded] = useState(true);
  const [projectTreeExpanded, setProjectTreeExpanded] = useState(true);
  const [outlineExpanded, setOutlineExpanded] = useState(false);

  // Search input state
  const [searchWorkspaceQuery, setSearchWorkspaceQuery] = useState('');
  const [replaceQuery, setReplaceQuery] = useState('');
  const [matchCase, setMatchCase] = useState(false);
  const [useRegex, setUseRegex] = useState(false);

  // Quick Inline New File state
  const [isAddingFile, setIsAddingFile] = useState(false);
  const [newFileName, setNewFileName] = useState('');

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: !prev[path],
    }));
  };

  const handleCreateFileSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFileName.trim()) {
      setIsAddingFile(false);
      return;
    }
    const createdPath = `/src/${newFileName.trim()}`;
    onSelectFile(createdPath);
    setNewFileName('');
    setIsAddingFile(false);
  };

  // Render tree item recursively
  const renderTreeItem = (item: FileItem, depth = 0) => {
    if (item.type === 'folder') {
      const isExpanded = !!expandedFolders[item.path];
      return (
        <div key={item.path}>
          <div
            onClick={() => toggleFolder(item.path)}
            className="group flex items-center gap-1.5 py-1 px-2 hover:bg-slate-900/90 text-slate-300 hover:text-white cursor-pointer transition-colors text-xs font-mono select-none"
            style={{ paddingLeft: `${depth * 14 + 10}px` }}
          >
            {isExpanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-slate-500 group-hover:text-slate-300 shrink-0" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-slate-300 shrink-0" />
            )}
            {isExpanded ? (
              <FolderOpen className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            ) : (
              <Folder className="w-3.5 h-3.5 text-blue-400/80 shrink-0" />
            )}
            <span className="truncate">{item.name}</span>
          </div>

          {isExpanded && item.children && (
            <div>{item.children.map((child) => renderTreeItem(child, depth + 1))}</div>
          )}
        </div>
      );
    }

    // File node
    const isSelected = item.path === activeFilePath;
    return (
      <div
        key={item.path}
        onClick={() => onSelectFile(item.path)}
        className={`group flex items-center justify-between py-1 px-2 text-xs font-mono cursor-pointer transition-colors select-none ${
          isSelected
            ? 'bg-blue-600/20 text-cyan-300 font-semibold border-l-2 border-blue-500'
            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
        }`}
        style={{ paddingLeft: `${depth * 14 + 18}px` }}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <FileCode2
            className={`w-3.5 h-3.5 shrink-0 ${
              item.name.endsWith('.tsx')
                ? 'text-cyan-400'
                : item.name.endsWith('.ts')
                ? 'text-blue-400'
                : item.name.endsWith('.json')
                ? 'text-amber-400'
                : item.name.endsWith('.css')
                ? 'text-sky-300'
                : 'text-slate-400'
            }`}
          />
          <span className="truncate">{item.name}</span>
        </div>

        {item.modified && (
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" title="Modified" />
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full shrink-0 select-none z-20">
      {/* VS Code / Cursor / Devin style Left Activity Bar */}
      <aside className="w-12 bg-slate-950 border-r border-slate-800/90 flex flex-col items-center justify-between py-2 shrink-0 z-20">
        {/* Top Icons */}
        <div className="flex flex-col items-center gap-1 w-full">
          <button
            onClick={() => setActiveView('explorer')}
            className={`relative p-2.5 rounded-lg transition-all ${
              activeView === 'explorer'
                ? 'text-white bg-slate-900'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
            title="Explorer (Ctrl+Shift+E)"
          >
            {activeView === 'explorer' && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-500 rounded-r-full" />
            )}
            <Files className="w-5 h-5" />
          </button>

          <button
            onClick={() => setActiveView('search')}
            className={`relative p-2.5 rounded-lg transition-all ${
              activeView === 'search'
                ? 'text-white bg-slate-900'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
            title="Search Across Files (Ctrl+Shift+F)"
          >
            {activeView === 'search' && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-500 rounded-r-full" />
            )}
            <Search className="w-5 h-5" />
          </button>

          <button
            onClick={() => {
              setActiveView('source-control');
              if (onSelectTab) onSelectTab('version-control');
            }}
            className={`relative p-2.5 rounded-lg transition-all ${
              activeView === 'source-control'
                ? 'text-white bg-slate-900'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
            title="Source Control / Git (Ctrl+Shift+G)"
          >
            {activeView === 'source-control' && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-500 rounded-r-full" />
            )}
            <GitBranch className="w-5 h-5" />
            <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-cyan-400" />
          </button>

          <button
            onClick={() => setActiveView('debug')}
            className={`relative p-2.5 rounded-lg transition-all ${
              activeView === 'debug'
                ? 'text-white bg-slate-900'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
            title="Run and Debug (Ctrl+Shift+D)"
          >
            {activeView === 'debug' && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-500 rounded-r-full" />
            )}
            <PlayCircle className="w-5 h-5" />
          </button>

          <button
            onClick={() => setActiveView('extensions')}
            className={`relative p-2.5 rounded-lg transition-all ${
              activeView === 'extensions'
                ? 'text-white bg-slate-900'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
            title="Extensions & Packages (Ctrl+Shift+X)"
          >
            {activeView === 'extensions' && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-500 rounded-r-full" />
            )}
            <Boxes className="w-5 h-5" />
          </button>
        </div>

        {/* Bottom Settings */}
        <div className="flex flex-col items-center gap-2">
          {onOpenNewProjectModal && (
            <button
              onClick={onOpenNewProjectModal}
              className="p-2 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-900 transition-colors"
              title="New Project from Template"
            >
              <Plus className="w-4 h-4" />
            </button>
          )}

          <div
            className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-900 transition-colors cursor-pointer"
            title="IDE Settings"
          >
            <Settings className="w-4 h-4" />
          </div>
        </div>
      </aside>

      {/* Primary VS Code Sidebar Panel */}
      <aside className="w-60 sm:w-64 bg-[#0d1117] border-r border-slate-800/90 flex flex-col justify-between overflow-hidden">
        {/* VIEW 1: EXPLORER */}
        {activeView === 'explorer' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden">
            {/* Header */}
            <div className="h-9 px-3 border-b border-slate-800/80 flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-slate-400 shrink-0">
              <span className="truncate">EXPLORER</span>
              <div className="flex items-center gap-1 text-slate-400">
                <button
                  onClick={() => setIsAddingFile(true)}
                  className="p-1 rounded hover:bg-slate-800 hover:text-slate-200 transition-colors"
                  title="New File"
                >
                  <FilePlus className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onOpenNewProjectModal}
                  className="p-1 rounded hover:bg-slate-800 hover:text-slate-200 transition-colors"
                  title="New Project"
                >
                  <FolderPlus className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => {}}
                  className="p-1 rounded hover:bg-slate-800 hover:text-slate-200 transition-colors"
                  title="Refresh Explorer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Tree Area */}
            <div className="flex-1 overflow-y-auto py-1">
              {/* OPEN EDITORS Section */}
              <div>
                <div
                  onClick={() => setOpenEditorsExpanded(!openEditorsExpanded)}
                  className="flex items-center gap-1 px-2 py-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200"
                >
                  {openEditorsExpanded ? (
                    <ChevronDown className="w-3 h-3 text-slate-500" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-slate-500" />
                  )}
                  <span>Open Editors</span>
                </div>

                {openEditorsExpanded && (
                  <div className="pl-4 pr-2 py-0.5 space-y-0.5">
                    <div
                      onClick={() => onSelectFile(activeFilePath)}
                      className="flex items-center justify-between py-1 px-1.5 rounded text-xs font-mono text-cyan-300 bg-blue-600/15 border border-blue-500/30 cursor-pointer"
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <FileCode2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                        <span className="truncate">{activeFilePath.split('/').pop()}</span>
                      </div>
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                    </div>
                  </div>
                )}
              </div>

              {/* PROJECT FOLDER TREE Section */}
              <div className="mt-2">
                <div
                  onClick={() => setProjectTreeExpanded(!projectTreeExpanded)}
                  className="flex items-center gap-1 px-2 py-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200"
                >
                  {projectTreeExpanded ? (
                    <ChevronDown className="w-3 h-3 text-slate-500" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-slate-500" />
                  )}
                  <span className="truncate">{projectName}</span>
                </div>

                {/* Inline New File Form */}
                {isAddingFile && (
                  <form onSubmit={handleCreateFileSubmit} className="px-3 py-1.5">
                    <div className="flex items-center gap-1 bg-slate-900 border border-blue-500 rounded p-1">
                      <FileCode2 className="w-3 h-3 text-blue-400" />
                      <input
                        type="text"
                        value={newFileName}
                        onChange={(e) => setNewFileName(e.target.value)}
                        placeholder="filename.tsx"
                        autoFocus
                        className="bg-transparent text-xs font-mono text-white focus:outline-none w-full"
                      />
                    </div>
                  </form>
                )}

                {projectTreeExpanded && (
                  <div className="py-1">{files.map((item) => renderTreeItem(item, 0))}</div>
                )}
              </div>

              {/* OUTLINE Section */}
              <div className="mt-2 border-t border-slate-800/80 pt-1">
                <div
                  onClick={() => setOutlineExpanded(!outlineExpanded)}
                  className="flex items-center gap-1 px-2 py-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200"
                >
                  {outlineExpanded ? (
                    <ChevronDown className="w-3 h-3 text-slate-500" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-slate-500" />
                  )}
                  <span>Outline</span>
                </div>

                {outlineExpanded && (
                  <div className="pl-6 pr-3 py-1 space-y-1 text-xs font-mono text-slate-400">
                    <div className="flex items-center gap-1.5 hover:text-cyan-300 cursor-pointer">
                      <span className="text-purple-400 font-bold text-[10px]">C</span>
                      <span>TaskList</span>
                    </div>
                    <div className="flex items-center gap-1.5 hover:text-cyan-300 cursor-pointer">
                      <span className="text-blue-400 font-bold text-[10px]">f</span>
                      <span>handleAddTask</span>
                    </div>
                    <div className="flex items-center gap-1.5 hover:text-cyan-300 cursor-pointer">
                      <span className="text-amber-400 font-bold text-[10px]">v</span>
                      <span>taskStats</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* VIEW 2: SEARCH */}
        {activeView === 'search' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden p-3 space-y-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              SEARCH WORKSPACE
            </div>

            <div className="space-y-2">
              <div className="relative">
                <input
                  type="text"
                  value={searchWorkspaceQuery}
                  onChange={(e) => setSearchWorkspaceQuery(e.target.value)}
                  placeholder="Search (Ctrl+F)..."
                  className="w-full bg-slate-900 border border-slate-800 rounded p-2 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="relative">
                <input
                  type="text"
                  value={replaceQuery}
                  onChange={(e) => setReplaceQuery(e.target.value)}
                  placeholder="Replace..."
                  className="w-full bg-slate-900 border border-slate-800 rounded p-2 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <span>Match Case</span>
                <span>Regex</span>
                <span>Whole Word</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto pt-2 border-t border-slate-800 text-xs text-slate-500">
              {searchWorkspaceQuery ? (
                <div className="space-y-2">
                  <div className="text-slate-300 font-mono text-[11px]">
                    3 results across 2 files
                  </div>
                  <div className="p-2 rounded bg-slate-900/60 font-mono text-[11px] text-slate-300">
                    <div className="font-semibold text-cyan-400">TaskList.tsx:14</div>
                    <div className="text-slate-400 truncate">const tasks = useTasks();</div>
                  </div>
                  <div className="p-2 rounded bg-slate-900/60 font-mono text-[11px] text-slate-300">
                    <div className="font-semibold text-cyan-400">types.ts:28</div>
                    <div className="text-slate-400 truncate">export interface TaskItem ...</div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-6">Type above to search all project files</div>
              )}
            </div>
          </div>
        )}

        {/* VIEW 3: SOURCE CONTROL */}
        {activeView === 'source-control' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden p-3 space-y-3">
            <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-slate-400">
              <span>SOURCE CONTROL</span>
              <span className="font-mono text-[10px] text-cyan-400">git (main)</span>
            </div>

            <div className="space-y-2">
              <input
                type="text"
                placeholder="Commit message (Enter to commit)"
                className="w-full bg-slate-900 border border-slate-800 rounded p-2 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={() => {
                  if (onSelectTab) onSelectTab('version-control');
                }}
                className="w-full py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-semibold flex items-center justify-center gap-1.5"
              >
                <GitBranch className="w-3.5 h-3.5" />
                <span>Open Git Workspace</span>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto pt-2 border-t border-slate-800 space-y-2 text-xs font-mono">
              <div className="text-slate-400 font-bold uppercase text-[10px]">
                Changed Files (2)
              </div>
              <div className="p-1.5 rounded bg-slate-900/50 flex items-center justify-between text-slate-300">
                <span className="truncate">InteractivePreview.tsx</span>
                <span className="text-[10px] text-amber-400">M</span>
              </div>
              <div className="p-1.5 rounded bg-slate-900/50 flex items-center justify-between text-slate-300">
                <span className="truncate">CodeEditor.tsx</span>
                <span className="text-[10px] text-blue-400">M</span>
              </div>
            </div>
          </div>
        )}

        {/* VIEW 4: RUN & DEBUG */}
        {activeView === 'debug' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden p-3 space-y-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              RUN AND DEBUG
            </div>
            <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-white">Vite: Dev Server</span>
                <span className="text-[10px] text-emerald-400 font-mono">Port 3000</span>
              </div>
              <button className="w-full py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-semibold flex items-center justify-center gap-1.5">
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Start Debugging</span>
              </button>
            </div>
          </div>
        )}

        {/* VIEW 5: EXTENSIONS */}
        {activeView === 'extensions' && (
          <div className="flex-1 flex flex-col h-full overflow-hidden p-3 space-y-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              EXTENSIONS
            </div>
            <div className="space-y-2 overflow-y-auto">
              {[
                { name: 'Tailwind CSS IntelliSense', author: 'Tailwind Labs', installed: true },
                { name: 'Antigravity Gemini AI Copilot', author: 'Google DeepMind', installed: true },
                { name: 'TypeScript Next LSP', author: 'Microsoft', installed: true },
                { name: 'Prettier - Code formatter', author: 'Prettier', installed: true },
              ].map((ext, idx) => (
                <div key={idx} className="p-2 bg-slate-900/60 border border-slate-800 rounded text-xs">
                  <div className="font-semibold text-slate-200">{ext.name}</div>
                  <div className="text-[10px] text-slate-500">{ext.author}</div>
                  <span className="inline-block mt-1 text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">
                    Installed
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
};
