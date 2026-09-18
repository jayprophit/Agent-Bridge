export type ViewMode = 'chat' | 'work' | 'team';

export type ThemeType = 'dark' | 'dark-light' | 'light' | 'white' | 'aurora' | 'amber' | 'frosted';

export type SurfaceTab = 'code' | 'browser' | 'preview' | 'database' | 'terminal' | 'version-control';
export type RightSurfaceTab = SurfaceTab;

export interface CommitItem {
  id: string;
  hash: string;
  shortHash: string;
  message: string;
  author: {
    name: string;
    email: string;
    avatarUrl?: string;
  };
  timestamp: string;
  relativeTime: string;
  branch: string;
  changes: {
    filesCount: number;
    additions: number;
    deletions: number;
  };
  files: string[];
}

export interface GitFileChange {
  path: string;
  status: 'modified' | 'added' | 'deleted' | 'untracked';
  staged: boolean;
  additions: number;
  deletions: number;
  diffSnippet?: string;
}

export interface PlanStep {
  id: string;
  title: string;
  status: 'completed' | 'in_progress' | 'pending' | 'failed';
  time?: string;
  substeps?: string[];
}

export interface CodeChip {
  name: string;
  changes: string;
  filePath: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  timestamp: string;
  text?: string;
  plan?: {
    title: string;
    steps: PlanStep[];
  };
  codeChips?: CodeChip[];
  actionButtons?: {
    label: string;
    action: string;
    primary?: boolean;
  }[];
  terminalCommand?: {
    command: string;
    completed?: boolean;
  };
  progressBar?: {
    label: string;
    progress: number;
    steps: string[];
    eta?: string;
  };
}

export interface ProjectSession {
  id: string;
  name: string;
  type: string;
  active?: boolean;
  pinned?: boolean;
  lastActive: string;
  environment: string;
  defaultTab?: SurfaceTab;
}

export interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: FileItem[];
  language?: string;
  content?: string;
  modified?: boolean;
}

export interface TaskItem {
  id: string;
  title: string;
  status: 'todo' | 'in-progress' | 'review' | 'done';
  priority: 'High' | 'Medium' | 'Low';
  tag: string;
  dueDate: string;
  assignee?: string;
}

export interface TeamAgent {
  id: string;
  name: string;
  role: string;
  specialty: string;
  avatarUrl: string;
  status: 'active' | 'in_call' | 'reviewing' | 'idle';
  currentTask: string;
  recentActivity: string;
  progress?: number;
  speaking?: boolean;
  speechText?: string;
}

export interface TerminalLine {
  id: string;
  type: 'info' | 'success' | 'warn' | 'error' | 'command' | 'step';
  text: string;
  time?: string;
}

export type KeybindingCategory = 'Navigation' | 'Editor' | 'View' | 'Agent & Tools';

export interface KeybindingItem {
  id: string;
  name: string;
  description: string;
  category: KeybindingCategory;
  defaultKey: string;
  currentKey: string;
}

export type TerminalPaletteId =
  | 'dracula'
  | 'solarized-dark'
  | 'one-dark'
  | 'monokai'
  | 'cyberpunk'
  | 'nord-dark';

export interface TerminalPalette {
  id: TerminalPaletteId;
  name: string;
  description: string;
  bg: string;
  fg: string;
  prompt: string;
  command: string;
  step: string;
  success: string;
  warn: string;
  error: string;
  tabBg: string;
  activeTabBg: string;
  border: string;
  statusBarBg: string;
  selection: string;
  cursor: string;
}

export interface FileRevision {
  id: string;
  timestamp: number;
  dateFormatted: string;
  summary: string;
  content: string;
  addedLinesCount: number;
  removedLinesCount: number;
}

export interface WorkspaceRoot {
  id: string;
  name: string;
  path: string;
  files: FileItem[];
  isDefault?: boolean;
  isRemovable?: boolean;
  badge?: string;
}
