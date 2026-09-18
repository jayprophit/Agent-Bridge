/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import {
  INITIAL_PROJECTS,
  INITIAL_MESSAGES,
  INITIAL_FILES,
} from './data/mockData';
import { ViewMode, ThemeType, RightSurfaceTab, ChatMessage, TeamAgent, FileItem, KeybindingItem } from './types';
import { DEFAULT_KEYBINDINGS } from './data/keybindings';
import { doesEventMatchKeybinding } from './utils/keybindingUtils';
import { Header } from './components/Header';
import { SidebarRail } from './components/SidebarRail';
import { ProjectsDrawer } from './components/ProjectsDrawer';
import { AgentSidePanel } from './components/AgentSidePanel';
import { VSCodeSidePanel } from './components/VSCodeSidePanel';
import { TeamSidePanel } from './components/TeamSidePanel';
import { ChatPanel } from './components/ChatPanel';
import { InteractivePreview } from './components/InteractivePreview';
import { CodeEditor } from './components/CodeEditor';
import { BrowserSurface } from './components/BrowserSurface';
import { TerminalPanel } from './components/TerminalPanel';
import { VersionControlPanel } from './components/VersionControlPanel';
import { TeamMeetingView } from './components/TeamMeetingView';
import { VoiceVideoCallModal } from './components/VoiceVideoCallModal';
import { CommandPaletteModal } from './components/CommandPaletteModal';
import { ToolsDrawer } from './components/ToolsDrawer';
import { NewProjectModal, ProjectTemplate } from './components/NewProjectModal';
import { PerformanceDashboardModal } from './components/PerformanceDashboardModal';
import { ShareModal } from './components/ShareModal';
import { WorkspaceBreadcrumbs } from './components/WorkspaceBreadcrumbs';
import {
  Eye,
  FileCode2,
  Globe,
  Terminal as TerminalIcon,
  GitBranch,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  Bot,
  Sparkles,
  CheckCircle2,
  FolderPlus,
  Activity
} from 'lucide-react';

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>('work');
  const [theme, setTheme] = useState<ThemeType>('dark');
  const [projects, setProjects] = useState(INITIAL_PROJECTS);
  const [activeProjectId, setActiveProjectId] = useState('task-manager');
  const [activeModelId, setActiveModelId] = useState('gemini-2.5-pro');
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES['task-manager'] || []);
  const [activeRightTab, setActiveRightTab] = useState<RightSurfaceTab>('preview');
  const [activeFilePath, setActiveFilePath] = useState('/src/components/TaskList.tsx');
  const [files, setFiles] = useState<FileItem[]>(INITIAL_FILES);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [callModal, setCallModal] = useState<'voice' | 'video' | null>(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isToolsDrawerOpen, setIsToolsDrawerOpen] = useState(false);
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [isPerfModalOpen, setIsPerfModalOpen] = useState(false);
  const [isShareOpen, setIsShareOpen] = useState(false);
  const [isChatSplitOpen, setIsChatSplitOpen] = useState(false);
  const [saveToastMessage, setSaveToastMessage] = useState<string | null>(null);

  // Persistent Keybindings State
  const [keybindings, setKeybindings] = useState<KeybindingItem[]>(() => {
    try {
      const saved = localStorage.getItem('aetherius_ide_keybindings');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          return DEFAULT_KEYBINDINGS.map((def) => {
            const found = parsed.find((p: any) => p.id === def.id);
            return found && typeof found.currentKey === 'string'
              ? { ...def, currentKey: found.currentKey }
              : def;
          });
        }
      }
    } catch (e) {
      console.warn('Failed to load keybindings from localStorage', e);
    }
    return DEFAULT_KEYBINDINGS;
  });

  const handleUpdateKeybinding = (id: string, newKey: string) => {
    setKeybindings((prev) => {
      const updated = prev.map((item) =>
        item.id === id ? { ...item, currentKey: newKey } : item
      );
      try {
        localStorage.setItem('aetherius_ide_keybindings', JSON.stringify(updated));
      } catch (e) {
        console.warn('Failed to persist keybindings', e);
      }
      return updated;
    });
  };

  const handleResetKeybinding = (id: string) => {
    setKeybindings((prev) => {
      const updated = prev.map((item) =>
        item.id === id ? { ...item, currentKey: item.defaultKey } : item
      );
      try {
        localStorage.setItem('aetherius_ide_keybindings', JSON.stringify(updated));
      } catch (e) {
        console.warn('Failed to persist keybindings', e);
      }
      return updated;
    });
  };

  const handleResetAllKeybindings = () => {
    const updated = DEFAULT_KEYBINDINGS.map((d) => ({ ...d }));
    setKeybindings(updated);
    try {
      localStorage.removeItem('aetherius_ide_keybindings');
    } catch (e) {
      console.warn('Failed to clear keybindings from localStorage', e);
    }
    setSaveToastMessage('Reset all keyboard shortcuts to defaults');
    setTimeout(() => setSaveToastMessage(null), 2500);
  };

  const activeProject = projects.find((p) => p.id === activeProjectId) || projects[0];

  // Global Keyboard Shortcuts Listener with dynamic keybindings
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Avoid firing single-key shortcuts when typing into inputs or textareas
      const target = e.target as HTMLElement | null;
      const isInputFocused =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable);

      // Helper to check if event matches a specific configured action
      const matches = (actionId: string) => {
        const kb = keybindings.find((k) => k.id === actionId);
        if (!kb) return false;

        // If typing in input and shortcut doesn't require Ctrl/Cmd/Alt, don't hijack input
        if (isInputFocused && !e.ctrlKey && !e.metaKey && !e.altKey) {
          return false;
        }

        return doesEventMatchKeybinding(e, kb.currentKey);
      };

      // Command Palette (toggle)
      if (matches('command_palette')) {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
        return;
      }

      // Quick Open / File Search
      if (matches('quick_open')) {
        e.preventDefault();
        setIsCommandPaletteOpen(true);
        return;
      }

      // Save Active File
      if (matches('save_file')) {
        e.preventDefault();
        const activeName = activeFilePath.split('/').pop() || 'file';
        setSaveToastMessage(`Saved ${activeName} to workspace`);
        setTimeout(() => setSaveToastMessage(null), 2500);
        return;
      }

      // Toggle Sidebar Explorer
      if (matches('toggle_sidebar')) {
        e.preventDefault();
        setIsSidebarOpen((prev) => !prev);
        return;
      }

      // Toggle Split Copilot Chat
      if (matches('toggle_chat_split')) {
        e.preventDefault();
        setIsChatSplitOpen((prev) => !prev);
        return;
      }

      // IDE Performance & Telemetry Dashboard
      if (matches('perf_dashboard')) {
        e.preventDefault();
        setIsPerfModalOpen((prev) => !prev);
        return;
      }

      // Agent Tools & Keybinding Settings
      if (matches('toggle_tools')) {
        e.preventDefault();
        setIsToolsDrawerOpen((prev) => !prev);
        return;
      }

      // Switch Modes
      if (matches('mode_chat')) {
        e.preventDefault();
        setViewMode('chat');
        return;
      }
      if (matches('mode_work')) {
        e.preventDefault();
        setViewMode('work');
        return;
      }
      if (matches('mode_team')) {
        e.preventDefault();
        setViewMode('team');
        return;
      }

      // Switch Surfaces
      if (matches('surface_preview')) {
        e.preventDefault();
        setActiveRightTab('preview');
        return;
      }
      if (matches('surface_code')) {
        e.preventDefault();
        setActiveRightTab('code');
        return;
      }
      if (matches('surface_terminal')) {
        e.preventDefault();
        setActiveRightTab('terminal');
        return;
      }
      if (matches('surface_git')) {
        e.preventDefault();
        setActiveRightTab('version-control');
        return;
      }
      if (matches('surface_browser')) {
        e.preventDefault();
        setActiveRightTab('browser');
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeFilePath, keybindings]);

  // Project Template Initialization Handler
  const handleCreateProject = ({
    name,
    description,
    template,
  }: {
    name: string;
    description: string;
    template: ProjectTemplate;
  }) => {
    const newId = `proj-${Date.now()}`;
    const newProject = {
      id: newId,
      name,
      type: template.badge,
      active: true,
      lastActive: 'Just created',
      environment: newId,
      defaultTab: 'code' as RightSurfaceTab,
    };

    setProjects((prev) => [newProject, ...prev]);
    setActiveProjectId(newId);
    setFiles(template.starterFiles);
    setActiveFilePath(template.defaultFilePath);
    setActiveRightTab('code');
    setViewMode('work');
    setSaveToastMessage(`Initialized "${name}" from ${template.category} template`);
    setTimeout(() => setSaveToastMessage(null), 3000);
  };

  // Auto-saved file persistence handler
  const handleCodeChange = (path: string, newContent: string) => {
    setFiles((prevFiles) => {
      const updateRecursive = (items: FileItem[]): FileItem[] => {
        return items.map((item) => {
          if (item.path === path) {
            return { ...item, content: newContent, modified: true };
          }
          if (item.children) {
            return { ...item, children: updateRecursive(item.children) };
          }
          return item;
        });
      };
      return updateRecursive(prevFiles);
    });
  };

  // Handle new message from user in chat
  const handleSendMessage = (text: string) => {
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);

    // Simulated autonomous agent response
    setTimeout(() => {
      let agentMsg: ChatMessage;

      if (text.toLowerCase().includes('kanban') || text.toLowerCase().includes('board')) {
        agentMsg = {
          id: `msg-${Date.now() + 1}`,
          sender: 'agent',
          text: `I've synthesized the Kanban Board component with 4 status swimlanes (To Do, In Progress, Review, Done). The component has been wired directly into the TaskFlow view.`,
          timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          codeChips: [
            { name: 'KanbanBoard.tsx', changes: '+42 lines', filePath: '/src/components/KanbanBoard.tsx' },
            { name: 'types.ts', changes: '+6 lines', filePath: '/src/types.ts' },
          ],
          actionButtons: [
            { label: 'View Kanban in Code', action: 'open_code_kanban', primary: true },
            { label: 'Test Drag & Drop', action: 'test_dnd' },
          ],
        };
        setActiveFilePath('/src/components/KanbanBoard.tsx');
      } else if (text.toLowerCase().includes('terminal') || text.toLowerCase().includes('build')) {
        agentMsg = {
          id: `msg-${Date.now() + 1}`,
          sender: 'agent',
          text: `Executing production build checks in sandbox container. All 786 modules transformed and ready.`,
          timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          actionButtons: [{ label: 'Open Terminal', action: 'open_terminal', primary: true }],
        };
        setActiveRightTab('terminal');
      } else if (text.toLowerCase().includes('browse') || text.toLowerCase().includes('search') || text.toLowerCase().includes('product')) {
        agentMsg = {
          id: `msg-${Date.now() + 1}`,
          sender: 'agent',
          text: `Launching headless browser automation on https://shop.aetherius.com to inspect e-commerce products and pricing.`,
          timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          actionButtons: [{ label: 'View Browser Sandbox', action: 'open_browser', primary: true }],
        };
        setActiveRightTab('browser');
      } else {
        agentMsg = {
          id: `msg-${Date.now() + 1}`,
          sender: 'agent',
          text: `I understand: "${text}". I have analyzed the repository structure, verified TypeScript interfaces, and staged the appropriate modifications for you.`,
          timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          plan: {
            title: 'Refinement Plan',
            steps: [
              { id: 's1', title: `Analyze requirement: ${text.slice(0, 40)}...`, status: 'completed', time: 'Just now' },
              { id: 's2', title: 'Compile AST & check type safety', status: 'completed', time: 'Just now' },
              { id: 's3', title: 'Update components and state hooks', status: 'in_progress', time: 'In progress' },
              { id: 's4', title: 'Verify live preview output', status: 'pending' },
            ],
          },
          actionButtons: [
            { label: 'Yes, proceed →', action: 'proceed', primary: true },
            { label: 'Show plan first', action: 'show_plan' },
          ],
        };
      }

      setMessages((prev) => [...prev, agentMsg]);
    }, 600);
  };

  const handleSelectCodeChip = (filePath: string) => {
    setActiveFilePath(filePath);
    setActiveRightTab('code');
    if (viewMode === 'chat') {
      setViewMode('work');
    }
  };

  const handleActionClick = (action: string) => {
    if (action === 'open_code_kanban') {
      setActiveFilePath('/src/components/KanbanBoard.tsx');
      setActiveRightTab('code');
    } else if (action === 'open_terminal') {
      setActiveRightTab('terminal');
    } else if (action === 'open_browser') {
      setActiveRightTab('browser');
    } else if (action === 'proceed') {
      setActiveRightTab('preview');
    }
  };

  const handleSelectProject = (projectId: string) => {
    setActiveProjectId(projectId);
    if (INITIAL_MESSAGES[projectId]) {
      setMessages(INITIAL_MESSAGES[projectId]);
    }
    const proj = projects.find((p) => p.id === projectId);
    if (proj?.defaultTab) {
      setActiveRightTab(proj.defaultTab as RightSurfaceTab);
    } else if (projectId === 'product-research') {
      setActiveRightTab('browser');
    } else {
      setActiveRightTab('preview');
    }
  };

  const handleNewChat = () => {
    const newId = `proj-${Date.now()}`;
    const newProj = {
      id: newId,
      name: 'New Sandbox Environment',
      type: 'React • Vite',
      lastActive: 'Just now',
    };
    setProjects([newProj, ...projects]);
    setActiveProjectId(newId);
    setMessages([
      {
        id: 'welcome',
        sender: 'agent',
        text: 'New isolated environment initialized! What would you like to build or automate together today?',
        timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        actionButtons: [
          { label: 'Build full-stack dashboard', action: 'proceed', primary: true },
          { label: 'Automate web workflow', action: 'open_browser' },
        ],
      },
    ]);
  };

  return (
    <div
      className={`flex flex-col h-screen w-screen overflow-hidden font-sans ${
        theme === 'amber'
          ? 'bg-[#120d04] text-amber-200'
          : theme === 'aurora'
          ? 'bg-[#06141d] text-cyan-200'
          : theme === 'light' || theme === 'white'
          ? 'bg-slate-100 text-slate-900'
          : 'bg-slate-950 text-slate-100'
      }`}
    >
      {/* Universal Top Header */}
      <Header
        mode={viewMode}
        onModeChange={(m) => setViewMode(m)}
        theme={theme}
        onThemeChange={(t) => setTheme(t)}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        onOpenSettings={() => setIsToolsDrawerOpen(true)}
        onOpenModelsDrawer={() => setIsToolsDrawerOpen(true)}
        onOpenPerformanceDashboard={() => setIsPerfModalOpen(true)}
        onOpenNewProjectModal={() => setIsNewProjectModalOpen(true)}
        onOpenShare={() => setIsShareOpen(true)}
      />

      {/* Main App Canvas */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Environment-Specific Left Side Panel */}
        {isSidebarOpen && (
          <div className="h-full shrink-0 flex">
            {viewMode === 'chat' && (
              <AgentSidePanel
                projects={projects}
                activeProjectId={activeProjectId}
                onSelectProject={handleSelectProject}
                onNewChat={handleNewChat}
                onOpenNewProjectModal={() => setIsNewProjectModalOpen(true)}
                activeModelId={activeModelId}
                onModelChange={setActiveModelId}
              />
            )}

            {viewMode === 'work' && (
              <VSCodeSidePanel
                files={files}
                activeFilePath={activeFilePath}
                projectName={activeProject.name.toUpperCase().replace(/\s+/g, '-')}
                onSelectFile={(path) => {
                  setActiveFilePath(path);
                  setActiveRightTab('code');
                }}
                onOpenFileSearch={() => setIsCommandPaletteOpen(true)}
                onOpenNewProjectModal={() => setIsNewProjectModalOpen(true)}
                onSelectTab={(tab) => setActiveRightTab(tab as RightSurfaceTab)}
              />
            )}

            {viewMode === 'team' && (
              <TeamSidePanel
                onJoinMeeting={() => {}}
                onTalkToAgent={(agent) => {
                  setViewMode('chat');
                  handleSendMessage(`@${agent.name} Let's discuss your progress on ${agent.currentTask}`);
                }}
                onStartVideoCall={() => setCallModal('video')}
              />
            )}
          </div>
        )}

        {/* Floating Sidebar Toggle Button */}
        <button
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="absolute top-2 left-2 z-30 p-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-slate-300 hover:text-cyan-400 transition-colors shadow-lg"
          title={isSidebarOpen ? 'Hide Left Sidebar (Ctrl+B)' : 'Show Left Sidebar (Ctrl+B)'}
        >
          {isSidebarOpen ? <PanelLeftClose className="w-3.5 h-3.5" /> : <PanelLeftOpen className="w-3.5 h-3.5" />}
        </button>

        {/* View Mode Router: Main Center & Right Work Canvas */}
        {viewMode === 'team' ? (
          /* 12-Agent All-Hands Team Meeting Screen */
          <div className="flex-1 flex flex-col overflow-hidden">
            <TeamMeetingView
              onLeaveMeeting={() => setViewMode('work')}
              onTalkToAgent={(agent: TeamAgent) => {
                setViewMode('chat');
                handleSendMessage(`@${agent.name} Let's discuss your progress on ${agent.currentTask}`);
              }}
            />
          </div>
        ) : viewMode === 'chat' ? (
          /* Full Screen Autonomous Agent & Chat Environment */
          <div className="flex-1 flex flex-col overflow-hidden">
            <ChatPanel
              messages={messages}
              environment={(activeProject?.name || 'task-manager').toLowerCase().replace(/\s+/g, '-')}
              onEnvironmentChange={() => {}}
              onSendMessage={handleSendMessage}
              onSelectCodeChip={handleSelectCodeChip}
              onActionClick={handleActionClick}
              theme={theme}
              onStartVoiceCall={() => setCallModal('voice')}
              onStartVideoCall={() => setCallModal('video')}
              onOpenTools={() => setIsToolsDrawerOpen(true)}
              activeModelId={activeModelId}
              onModelChange={setActiveModelId}
            />
          </div>
        ) : (
          /* Work / IDE Mode with VS Code style Left Panel and Center Surfaces */
          <div className="flex-1 flex overflow-hidden">
            {/* Optional AI Copilot Split Chat */}
            {isChatSplitOpen && (
              <div className="w-80 lg:w-96 border-r border-slate-800/90 flex flex-col h-full shrink-0 overflow-hidden">
                <ChatPanel
                  messages={messages}
                  environment={(activeProject?.name || 'task-manager').toLowerCase().replace(/\s+/g, '-')}
                  onEnvironmentChange={() => {}}
                  onSendMessage={handleSendMessage}
                  onSelectCodeChip={handleSelectCodeChip}
                  onActionClick={handleActionClick}
                  theme={theme}
                  onStartVoiceCall={() => setCallModal('voice')}
                  onStartVideoCall={() => setCallModal('video')}
                  onOpenTools={() => setIsToolsDrawerOpen(true)}
                  activeModelId={activeModelId}
                  onModelChange={setActiveModelId}
                />
              </div>
            )}

            {/* Main Center IDE Surface */}
            <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
              {/* Right Surface Navigation Tabs */}
              <div className="h-9.5 bg-slate-950 border-b border-slate-800/90 px-3 flex items-center justify-between shrink-0 select-none">
                <div className="flex items-center gap-1.5 overflow-x-auto pl-7 sm:pl-0">
                  <button
                    onClick={() => setActiveRightTab('preview')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                      activeRightTab === 'preview'
                        ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>Preview</span>
                  </button>

                  <button
                    onClick={() => setActiveRightTab('code')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                      activeRightTab === 'code'
                        ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <FileCode2 className="w-3.5 h-3.5" />
                    <span>&lt; /&gt; Code</span>
                  </button>

                  <button
                    onClick={() => setActiveRightTab('version-control')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                      activeRightTab === 'version-control'
                        ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <GitBranch className="w-3.5 h-3.5" />
                    <span>Version Control</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  </button>

                  <button
                    onClick={() => setActiveRightTab('terminal')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                      activeRightTab === 'terminal'
                        ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <TerminalIcon className="w-3.5 h-3.5" />
                    <span>Terminal</span>
                  </button>

                  <button
                    onClick={() => setActiveRightTab('browser')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                      activeRightTab === 'browser'
                        ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <Globe className="w-3.5 h-3.5" />
                    <span>Browser</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  </button>
                </div>

                <div className="flex items-center gap-2 text-slate-400 text-xs font-mono">
                  {/* AI Copilot Side Chat Toggle */}
                  <button
                    onClick={() => setIsChatSplitOpen(!isChatSplitOpen)}
                    className={`px-2 py-0.5 rounded-md text-xs flex items-center gap-1.5 border transition-all ${
                      isChatSplitOpen
                        ? 'bg-blue-600/20 text-cyan-300 border-blue-500/40'
                        : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
                    }`}
                    title="Toggle AI Agent Chat alongside code"
                  >
                    <Bot className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="hidden sm:inline">AI Copilot</span>
                  </button>

                  <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] text-cyan-400 hidden sm:inline">
                    localhost:5173
                  </span>
                </div>
              </div>

              {/* Breadcrumbs Navigation Bar (VS Code / Devin style) */}
              <WorkspaceBreadcrumbs
                activeFilePath={activeFilePath}
                projectName={activeProject?.name || 'project'}
                files={files}
                onSelectFile={(path) => setActiveFilePath(path)}
                activeRightTab={activeRightTab}
              />

              {/* Surface Body Component */}
              <div className="flex-1 flex overflow-hidden">
                {activeRightTab === 'preview' && (
                  <InteractivePreview projectName={activeProject.name} />
                )}
                {activeRightTab === 'code' && (
                  <CodeEditor
                    files={files}
                    activeFilePath={activeFilePath}
                    onSelectFile={(path) => setActiveFilePath(path)}
                    onCodeChange={handleCodeChange}
                    onRunCode={() => setActiveRightTab('preview')}
                    theme={theme}
                  />
                )}
                {activeRightTab === 'version-control' && (
                  <VersionControlPanel
                    projectName={activeProject.name}
                    theme={theme}
                    onOpenFile={(path) => {
                      setActiveFilePath(path);
                      setActiveRightTab('code');
                    }}
                  />
                )}
                {activeRightTab === 'terminal' && <TerminalPanel />}
                {activeRightTab === 'browser' && <BrowserSurface />}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Share Project Collaboration Modal */}
      <ShareModal
        isOpen={isShareOpen}
        onClose={() => setIsShareOpen(false)}
        projectName={activeProject.name}
      />

      {/* Global Shortcut Save Notification Toast */}
      {saveToastMessage && (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 border border-emerald-500/40 text-emerald-300 text-xs font-mono shadow-2xl animate-fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{saveToastMessage}</span>
        </div>
      )}

      {/* Template Selection Modal for New Projects */}
      <NewProjectModal
        isOpen={isNewProjectModalOpen}
        onClose={() => setIsNewProjectModalOpen(false)}
        onCreateProject={handleCreateProject}
      />

      {/* IDE Internal Performance & Telemetry Dashboard */}
      <PerformanceDashboardModal
        isOpen={isPerfModalOpen}
        onClose={() => setIsPerfModalOpen(false)}
      />

      {/* Full-Screen Voice / Video Call Modal */}
      {callModal && (
        <VoiceVideoCallModal type={callModal} onClose={() => setCallModal(null)} />
      )}

      {/* Command Palette Modal (⌘K) */}
      <CommandPaletteModal
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onSelectMode={(m) => setViewMode(m)}
        onSelectProject={handleSelectProject}
        onSelectTheme={(t) => setTheme(t)}
        onStartVoiceCall={() => setCallModal('voice')}
        onStartVideoCall={() => setCallModal('video')}
        onOpenTools={() => setIsToolsDrawerOpen(true)}
      />

      {/* Agent Tools & Configuration Drawer with Keybindings Rebinding */}
      <ToolsDrawer
        isOpen={isToolsDrawerOpen}
        onClose={() => setIsToolsDrawerOpen(false)}
        keybindings={keybindings}
        onUpdateKeybinding={handleUpdateKeybinding}
        onResetKeybinding={handleResetKeybinding}
        onResetAllKeybindings={handleResetAllKeybindings}
        selectedModel={activeModelId}
        onSelectModel={setActiveModelId}
      />
    </div>
  );
}
