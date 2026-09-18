import React, { useState } from 'react';
import {
  GitBranch,
  GitCommit,
  GitPullRequest,
  Check,
  Plus,
  Minus,
  RotateCcw,
  Clock,
  User,
  FolderGit2,
  FileCode2,
  CheckCircle2,
  ArrowUpRight,
  Search,
  Tag,
  ChevronRight,
  ChevronDown,
  Layers,
  Sparkles
} from 'lucide-react';
import { CommitItem, GitFileChange, ThemeType } from '../types';

interface VersionControlPanelProps {
  projectName?: string;
  theme?: ThemeType;
  onOpenFile?: (path: string) => void;
}

const INITIAL_CHANGES: GitFileChange[] = [
  {
    path: '/src/components/InteractivePreview.tsx',
    status: 'modified',
    staged: false,
    additions: 46,
    deletions: 8,
    diffSnippet: `+ import { TaskCompletionTrendChart } from './TaskCompletionTrendChart';\n+ <TaskCompletionTrendChart tasks={tasks} />`,
  },
  {
    path: '/src/components/TaskCompletionTrendChart.tsx',
    status: 'added',
    staged: true,
    additions: 218,
    deletions: 0,
    diffSnippet: `+ export const TaskCompletionTrendChart: React.FC = () => {\n+   const svg = d3.select(svgRef.current);\n+ }`,
  },
  {
    path: '/src/components/CodeEditor.tsx',
    status: 'modified',
    staged: false,
    additions: 142,
    deletions: 24,
    diffSnippet: `+ // Debounced 3s auto-save\n+ autoSaveTimerRef.current = setTimeout(() => save(), 3000);`,
  },
  {
    path: '/src/types.ts',
    status: 'modified',
    staged: true,
    additions: 32,
    deletions: 2,
    diffSnippet: `+ export type SurfaceTab = ... | 'version-control';\n+ export interface CommitItem { ... }`,
  },
];

const INITIAL_COMMITS: CommitItem[] = [
  {
    id: 'c-1',
    hash: '8f3a2c19e54d89a7',
    shortHash: '8f3a2c1',
    message: 'feat: implement interactive Kanban board and status swimlanes',
    author: {
      name: 'Dev Specialist',
      email: 'dev@aetherius.ai',
      avatarUrl:
        'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80',
    },
    timestamp: '2026-09-12T10:31:00Z',
    relativeTime: '25m ago',
    branch: 'main',
    changes: { filesCount: 3, additions: 184, deletions: 12 },
    files: [
      '/src/components/KanbanBoard.tsx',
      '/src/components/TaskList.tsx',
      '/src/types.ts',
    ],
  },
  {
    id: 'c-2',
    hash: '4b7e91a0c283d5f1',
    shortHash: '4b7e91a',
    message: 'feat: add task priority tags, date filters, and multi-status toggle',
    author: {
      name: 'Luna',
      email: 'luna@aetherius.ai',
      avatarUrl:
        'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=100&auto=format&fit=crop&q=80',
    },
    timestamp: '2026-09-12T10:15:00Z',
    relativeTime: '45m ago',
    branch: 'main',
    changes: { filesCount: 2, additions: 92, deletions: 18 },
    files: ['/src/components/TaskList.tsx', '/src/hooks/useTasks.ts'],
  },
  {
    id: 'c-3',
    hash: '1e9a7c33b8210f92',
    shortHash: '1e9a7c3',
    message: 'chore: initialize React 19 + TypeScript + Tailwind workspace with Vite',
    author: {
      name: 'Atlas Project Lead',
      email: 'atlas@aetherius.ai',
      avatarUrl:
        'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80',
    },
    timestamp: '2026-09-12T09:40:00Z',
    relativeTime: '1h 20m ago',
    branch: 'main',
    changes: { filesCount: 8, additions: 412, deletions: 0 },
    files: ['/package.json', '/src/App.tsx', '/src/index.css', '/vite.config.ts'],
  },
];

export const VersionControlPanel: React.FC<VersionControlPanelProps> = ({
  projectName = 'Task Manager App',
  theme = 'dark',
  onOpenFile,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'staging' | 'history'>('staging');
  const [fileChanges, setFileChanges] = useState<GitFileChange[]>(INITIAL_CHANGES);
  const [commits, setCommits] = useState<CommitItem[]>(INITIAL_COMMITS);
  const [commitMessage, setCommitMessage] = useState('');
  const [selectedCommitId, setSelectedCommitId] = useState<string | null>('c-1');
  const [searchFilter, setSearchFilter] = useState('');
  const [justCommitted, setJustCommitted] = useState(false);

  // Staged vs Unstaged lists
  const stagedFiles = fileChanges.filter((f) => f.staged);
  const unstagedFiles = fileChanges.filter((f) => !f.staged);

  // Toggle stage for single file
  const handleToggleStage = (path: string) => {
    setFileChanges((prev) =>
      prev.map((f) => (f.path === path ? { ...f, staged: !f.staged } : f))
    );
  };

  // Stage all
  const handleStageAll = () => {
    setFileChanges((prev) => prev.map((f) => ({ ...f, staged: true })));
  };

  // Unstage all
  const handleUnstageAll = () => {
    setFileChanges((prev) => prev.map((f) => ({ ...f, staged: false })));
  };

  // Commit Staged Changes
  const handleCommit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commitMessage.trim() || stagedFiles.length === 0) return;

    const newHash = Math.random().toString(16).substring(2, 10);
    const totalAdditions = stagedFiles.reduce((acc, f) => acc + f.additions, 0);
    const totalDeletions = stagedFiles.reduce((acc, f) => acc + f.deletions, 0);

    const newCommit: CommitItem = {
      id: `c-${Date.now()}`,
      hash: `${newHash}f3108c90`,
      shortHash: newHash.substring(0, 7),
      message: commitMessage.trim(),
      author: {
        name: 'You (Aetherius Developer)',
        email: 'you@aetherius.ai',
        avatarUrl:
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100&auto=format&fit=crop&q=80',
      },
      timestamp: new Date().toISOString(),
      relativeTime: 'Just now',
      branch: 'main',
      changes: {
        filesCount: stagedFiles.length,
        additions: totalAdditions,
        deletions: totalDeletions,
      },
      files: stagedFiles.map((f) => f.path),
    };

    setCommits([newCommit, ...commits]);
    setFileChanges((prev) => prev.filter((f) => !f.staged));
    setCommitMessage('');
    setJustCommitted(true);
    setTimeout(() => setJustCommitted(false), 3000);
  };

  // Filtered commits
  const filteredCommits = commits.filter((c) => {
    const filter = (searchFilter || '').toLowerCase();
    return (
      (c.message || '').toLowerCase().includes(filter) ||
      (c.shortHash || '').toLowerCase().includes(filter) ||
      (c.author?.name || '').toLowerCase().includes(filter)
    );
  });

  const selectedCommit = commits.find((c) => c.id === selectedCommitId) || commits[0];

  return (
    <div
      id="version-control-workspace"
      className="flex-1 flex flex-col h-full bg-[#0b0f17] text-slate-100 overflow-hidden select-none"
    >
      {/* Top Header Bar */}
      <div className="h-11 bg-slate-950 border-b border-slate-800 px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-bold text-white tracking-tight">
              Version Control
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
              git (main)
            </span>
          </div>

          <div className="h-4 w-px bg-slate-800 hidden sm:block" />

          {/* Sub-tab switcher: Staging vs Commit History */}
          <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-xs">
            <button
              onClick={() => setActiveSubTab('staging')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                activeSubTab === 'staging'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Changes</span>
              {fileChanges.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] font-mono">
                  {fileChanges.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveSubTab('history')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                activeSubTab === 'history'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Clock className="w-3.5 h-3.5" />
              <span>Commit History</span>
              <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] font-mono">
                {commits.length}
              </span>
            </button>
          </div>
        </div>

        {/* Branch / Sync Status */}
        <div className="flex items-center gap-2.5 text-xs text-slate-400">
          <span className="flex items-center gap-1 text-[11px] font-mono text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Up to date with origin/main
          </span>
        </div>
      </div>

      {/* Main Content Area */}
      {activeSubTab === 'staging' ? (
        /* STAGING & CHANGES VIEW */
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left Column: Staging Controls & File Lists */}
          <div className="w-full md:w-80 lg:w-96 border-r border-slate-800/80 flex flex-col h-full bg-slate-950/60 overflow-hidden shrink-0">
            {/* Commit Message Box */}
            <div className="p-3 border-b border-slate-800 bg-slate-900/40">
              <form onSubmit={handleCommit} className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider">
                    Commit Staged Changes
                  </label>
                  {stagedFiles.length > 0 && (
                    <span className="text-[10px] font-mono text-cyan-400">
                      {stagedFiles.length} staged
                    </span>
                  )}
                </div>

                <textarea
                  value={commitMessage}
                  onChange={(e) => setCommitMessage(e.target.value)}
                  placeholder="Commit message (e.g., feat: add completion trends chart)..."
                  rows={2}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-sans resize-none"
                />

                <button
                  type="submit"
                  disabled={stagedFiles.length === 0 || !commitMessage.trim()}
                  className={`w-full py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                    stagedFiles.length > 0 && commitMessage.trim()
                      ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_12px_rgba(37,99,235,0.4)] cursor-pointer'
                      : 'bg-slate-800/80 text-slate-500 cursor-not-allowed border border-slate-800'
                  }`}
                >
                  <GitCommit className="w-3.5 h-3.5" />
                  <span>Commit to main</span>
                </button>

                {justCommitted && (
                  <div className="p-2 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[11px] flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Successfully committed to main!</span>
                  </div>
                )}
              </form>
            </div>

            {/* Staged Changes Section */}
            <div className="flex-1 overflow-y-auto p-3 space-y-4">
              {/* STAGED LIST */}
              <div>
                <div className="flex items-center justify-between pb-1.5 border-b border-slate-800/80 text-xs text-slate-400 font-semibold">
                  <div className="flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Staged Changes ({stagedFiles.length})</span>
                  </div>
                  {stagedFiles.length > 0 && (
                    <button
                      onClick={handleUnstageAll}
                      className="text-[10px] text-slate-400 hover:text-rose-400 hover:underline transition-colors"
                      title="Unstage all files"
                    >
                      Unstage All
                    </button>
                  )}
                </div>

                {stagedFiles.length === 0 ? (
                  <div className="py-4 text-center text-slate-600 text-[11px] italic">
                    No files staged. Click '+' on changes below to stage.
                  </div>
                ) : (
                  <div className="space-y-1.5 mt-2">
                    {stagedFiles.map((file) => (
                      <div
                        key={file.path}
                        className="flex items-center justify-between p-2 rounded-lg bg-slate-900/80 hover:bg-slate-900 border border-slate-800 text-xs font-mono group transition-colors"
                      >
                        <div
                          className="flex items-center gap-2 min-w-0 cursor-pointer"
                          onClick={() => onOpenFile && onOpenFile(file.path)}
                        >
                          <span
                            className={`w-4 h-4 rounded text-[9px] font-bold flex items-center justify-center shrink-0 ${
                              file.status === 'added'
                                ? 'bg-emerald-500/20 text-emerald-400'
                                : 'bg-blue-500/20 text-blue-400'
                            }`}
                          >
                            {file.status === 'added' ? 'A' : 'M'}
                          </span>
                          <span className="text-slate-200 truncate" title={file.path}>
                            {file.path.split('/').pop()}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[10px] text-emerald-400 font-mono">
                            +{file.additions}
                          </span>
                          {file.deletions > 0 && (
                            <span className="text-[10px] text-rose-400 font-mono">
                              -{file.deletions}
                            </span>
                          )}
                          <button
                            onClick={() => handleToggleStage(file.path)}
                            className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                            title="Unstage file"
                          >
                            <Minus className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* UNSTAGED CHANGES LIST */}
              <div>
                <div className="flex items-center justify-between pb-1.5 border-b border-slate-800/80 text-xs text-slate-400 font-semibold">
                  <div className="flex items-center gap-1.5">
                    <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
                    <span>Working Changes ({unstagedFiles.length})</span>
                  </div>
                  {unstagedFiles.length > 0 && (
                    <button
                      onClick={handleStageAll}
                      className="text-[10px] text-blue-400 hover:text-blue-300 hover:underline transition-colors"
                      title="Stage all files"
                    >
                      Stage All
                    </button>
                  )}
                </div>

                {unstagedFiles.length === 0 ? (
                  <div className="py-4 text-center text-slate-600 text-[11px] italic">
                    Working directory clean.
                  </div>
                ) : (
                  <div className="space-y-1.5 mt-2">
                    {unstagedFiles.map((file) => (
                      <div
                        key={file.path}
                        className="flex items-center justify-between p-2 rounded-lg bg-slate-900/50 hover:bg-slate-900 border border-slate-800/80 text-xs font-mono group transition-colors"
                      >
                        <div
                          className="flex items-center gap-2 min-w-0 cursor-pointer"
                          onClick={() => onOpenFile && onOpenFile(file.path)}
                        >
                          <span className="w-4 h-4 rounded text-[9px] font-bold flex items-center justify-center shrink-0 bg-amber-500/20 text-amber-400">
                            M
                          </span>
                          <span className="text-slate-300 truncate" title={file.path}>
                            {file.path.split('/').pop()}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[10px] text-emerald-400 font-mono">
                            +{file.additions}
                          </span>
                          {file.deletions > 0 && (
                            <span className="text-[10px] text-rose-400 font-mono">
                              -{file.deletions}
                            </span>
                          )}
                          <button
                            onClick={() => handleToggleStage(file.path)}
                            className="p-1 rounded text-slate-400 hover:text-emerald-400 hover:bg-slate-800 transition-colors"
                            title="Stage file"
                          >
                            <Plus className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right Column: Diff & Staging Preview */}
          <div className="flex-1 flex flex-col h-full bg-[#080c14] overflow-hidden">
            <div className="h-10 bg-slate-950 border-b border-slate-800 px-4 flex items-center justify-between text-xs text-slate-400 shrink-0">
              <span className="font-semibold text-slate-200">
                Staged Diff Summary
              </span>
              <span className="font-mono text-[11px] text-cyan-400">
                {stagedFiles.length} file(s) staged for commit
              </span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {stagedFiles.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-500">
                  <FolderGit2 className="w-12 h-12 stroke-[1.2] mb-3 text-slate-600" />
                  <div className="text-sm font-semibold text-slate-300 mb-1">
                    No files staged for commit
                  </div>
                  <p className="text-xs text-slate-500 max-w-sm">
                    Select files from the left panel using '+' to stage changes, review diffs,
                    and commit them directly to the repository.
                  </p>
                </div>
              ) : (
                stagedFiles.map((file) => (
                  <div
                    key={file.path}
                    className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-lg"
                  >
                    <div className="px-3.5 py-2 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-xs font-mono">
                      <div className="flex items-center gap-2">
                        <FileCode2 className="w-3.5 h-3.5 text-blue-400" />
                        <span className="text-slate-200 font-medium">{file.path}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px]">
                        <span className="text-emerald-400">+{file.additions}</span>
                        <span className="text-rose-400">-{file.deletions}</span>
                      </div>
                    </div>

                    <div className="p-3 font-mono text-xs text-slate-300 bg-slate-950/40 whitespace-pre leading-relaxed overflow-x-auto">
                      {file.diffSnippet ||
                        `@@ -1,4 +1,7 @@\n+ // Staged changes for ${file.path}\n+ import React from 'react';`}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      ) : (
        /* COMMIT HISTORY VIEW */
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left Column: Commit Timeline List */}
          <div className="w-full md:w-96 lg:w-[420px] border-r border-slate-800/80 flex flex-col h-full bg-slate-950/60 overflow-hidden shrink-0">
            {/* Search Commits Bar */}
            <div className="p-3 border-b border-slate-800 bg-slate-900/40">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs">
                <Search className="w-3.5 h-3.5 text-slate-500" />
                <input
                  type="text"
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  placeholder="Filter commits by message, hash, author..."
                  className="bg-transparent text-xs text-slate-200 placeholder-slate-500 focus:outline-none w-full font-mono"
                />
              </div>
            </div>

            {/* Commit Items Timeline */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {filteredCommits.map((commit, idx) => {
                const isSelected = commit.id === selectedCommit.id;
                return (
                  <div
                    key={commit.id}
                    onClick={() => setSelectedCommitId(commit.id)}
                    className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-blue-600/15 border-blue-500/50 shadow-md'
                        : 'bg-slate-900/60 hover:bg-slate-900 border-slate-800/80'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2">
                        <GitCommit
                          className={`w-3.5 h-3.5 ${
                            isSelected ? 'text-blue-400' : 'text-slate-500'
                          }`}
                        />
                        <span className="font-mono text-[11px] font-semibold text-cyan-400">
                          {commit.shortHash}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {commit.relativeTime}
                      </span>
                    </div>

                    <div className="font-medium text-slate-200 line-clamp-2 leading-snug mb-2">
                      {commit.message}
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                      <div className="flex items-center gap-1.5">
                        <img
                          src={commit.author.avatarUrl}
                          alt={commit.author.name}
                          className="w-4 h-4 rounded-full object-cover"
                        />
                        <span className="text-slate-300 text-[10px] font-medium truncate max-w-[120px]">
                          {commit.author.name}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 font-mono text-[10px]">
                        <span className="text-emerald-400">+{commit.changes.additions}</span>
                        <span className="text-rose-400">-{commit.changes.deletions}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Detailed Selected Commit Inspection */}
          <div className="flex-1 flex flex-col h-full bg-[#080c14] overflow-hidden">
            {selectedCommit ? (
              <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-3xl">
                {/* Commit Header Card */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <GitCommit className="w-5 h-5 text-cyan-400" />
                      <span className="font-mono text-sm font-bold text-white">
                        {selectedCommit.hash}
                      </span>
                    </div>

                    <span className="px-2.5 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/30 text-[11px] font-mono">
                      branch: {selectedCommit.branch}
                    </span>
                  </div>

                  <h2 className="text-base font-bold text-slate-100 leading-snug">
                    {selectedCommit.message}
                  </h2>

                  <div className="flex items-center justify-between flex-wrap gap-3 pt-2 text-xs text-slate-400">
                    <div className="flex items-center gap-2">
                      <img
                        src={selectedCommit.author.avatarUrl}
                        alt={selectedCommit.author.name}
                        className="w-6 h-6 rounded-full object-cover ring-1 ring-slate-700"
                      />
                      <div>
                        <div className="font-semibold text-slate-200">
                          {selectedCommit.author.name}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {selectedCommit.author.email}
                        </div>
                      </div>
                    </div>

                    <div className="text-right text-[11px] font-mono text-slate-400">
                      <div>{new Date(selectedCommit.timestamp).toLocaleString()}</div>
                      <div className="text-slate-500">({selectedCommit.relativeTime})</div>
                    </div>
                  </div>
                </div>

                {/* Changed Files in this Commit */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                    <span>Changed Files ({selectedCommit.files.length})</span>
                    <div className="font-mono text-[11px] flex items-center gap-2">
                      <span className="text-emerald-400">
                        +{selectedCommit.changes.additions} lines
                      </span>
                      <span className="text-rose-400">
                        -{selectedCommit.changes.deletions} lines
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {selectedCommit.files.map((file, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs font-mono hover:bg-slate-900 transition-colors"
                      >
                        <div className="flex items-center gap-2.5">
                          <FileCode2 className="w-4 h-4 text-cyan-400" />
                          <span className="text-slate-200">{file}</span>
                        </div>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                          Modified
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500 text-xs">
                Select a commit from the history list to inspect.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
