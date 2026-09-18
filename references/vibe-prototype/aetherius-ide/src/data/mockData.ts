import { ProjectSession, ChatMessage, FileItem, TaskItem, TeamAgent, TerminalLine } from '../types';

export const INITIAL_PROJECTS: ProjectSession[] = [
  {
    id: 'task-manager',
    name: 'Task Manager App',
    type: 'React • TypeScript',
    active: true,
    lastActive: 'Active session',
    environment: 'task-manager',
    defaultTab: 'preview',
  },
  {
    id: 'product-research',
    name: 'Automate Product Research',
    type: 'Next.js • Puppeteer',
    active: false,
    lastActive: 'Active session',
    environment: 'browser-automation',
    defaultTab: 'browser',
  },
  {
    id: 'ecommerce-dash',
    name: 'E-commerce Dashboard',
    type: 'Next.js • 3h ago',
    pinned: true,
    lastActive: '3h ago',
    environment: 'ecommerce-dash',
    defaultTab: 'preview',
  },
  {
    id: 'image-generator',
    name: 'AI Image Generator',
    type: 'React • 1d ago',
    pinned: true,
    lastActive: '1d ago',
    environment: 'image-gen',
    defaultTab: 'code',
  },
  {
    id: 'marketing-site',
    name: 'Marketing Website',
    type: 'Next.js • 2d ago',
    pinned: true,
    lastActive: '2d ago',
    environment: 'marketing',
    defaultTab: 'preview',
  },
  {
    id: 'data-analysis',
    name: 'Data Analysis Tool',
    type: 'Python • Streamlit',
    lastActive: 'Last active 5h ago',
    environment: 'data-analytics',
    defaultTab: 'database',
  },
  {
    id: 'portfolio-site',
    name: 'Portfolio Website',
    type: 'Astro • Tailwind',
    lastActive: 'Last active 1d ago',
    environment: 'portfolio',
    defaultTab: 'preview',
  },
  {
    id: 'slack-bot',
    name: 'Slack Bot',
    type: 'Node.js • Bolt',
    lastActive: 'Last active 2d ago',
    environment: 'slack-bot',
    defaultTab: 'terminal',
  },
  {
    id: 'mobile-app',
    name: 'Mobile App Prototype',
    type: 'React Native',
    lastActive: 'Last active 3d ago',
    environment: 'mobile-proto',
    defaultTab: 'preview',
  },
];

export const INITIAL_MESSAGES: Record<string, ChatMessage[]> = {
  'task-manager': [
    {
      id: 'msg-1',
      sender: 'user',
      timestamp: '10:24 AM',
      text: 'Build a modern task manager with React and TypeScript. Include add/edit/delete, filtering, and local storage.',
    },
    {
      id: 'msg-2',
      sender: 'agent',
      timestamp: '10:24 AM',
      text: "I'll create a modern task manager for you with React and TypeScript, including all the features you requested. Here's my plan:",
      plan: {
        title: 'Task Manager Implementation',
        steps: [
          { id: 'p1', title: 'Set up the project structure with Vite + React + TypeScript', status: 'completed', time: 'Completed • 10:24 AM' },
          { id: 'p2', title: 'Implement core task functionality (add/edit/delete)', status: 'completed', time: 'Completed • 10:26 AM' },
          { id: 'p3', title: 'Add filtering (all, active, completed)', status: 'in_progress', time: 'In progress...' },
          { id: 'p4', title: 'Implement local storage persistence', status: 'pending' },
          { id: 'p5', title: 'Add beautiful UI with modern design', status: 'pending' },
          { id: 'p6', title: 'Test the application', status: 'pending' },
        ],
      },
      codeChips: [
        { name: 'TaskList.tsx', changes: '+28', filePath: '/src/components/TaskList.tsx' },
        { name: 'TaskForm.tsx', changes: '+24', filePath: '/src/components/TaskForm.tsx' },
        { name: 'FilterTabs.tsx', changes: '+18', filePath: '/src/components/FilterTabs.tsx' },
        { name: 'types.ts', changes: '+15', filePath: '/src/types.ts' },
      ],
      actionButtons: [
        { label: 'Yes, proceed →', action: 'proceed', primary: true },
        { label: 'Show plan first', action: 'plan' },
        { label: 'Review changes', action: 'review' },
      ],
    },
    {
      id: 'msg-3',
      sender: 'user',
      timestamp: '10:31 AM',
      text: 'Add bulk actions to the task list (select multiple, mark complete, delete). Also let us toggle between list and Kanban view!',
    },
    {
      id: 'msg-4',
      sender: 'agent',
      timestamp: '10:31 AM',
      text: "I'll implement bulk actions for the task list and provide a responsive Kanban board view with status columns. Here's what I'm executing:",
      plan: {
        title: 'Bulk Actions & Kanban View',
        steps: [
          { id: 'b1', title: 'Add multi-select state management', status: 'completed', time: 'Completed • 10:31 AM' },
          { id: 'b2', title: 'Implement bulk action toolbar', status: 'completed', time: 'Completed • 10:32 AM' },
          { id: 'b3', title: 'Create interactive Kanban board view', status: 'in_progress', time: 'In progress...' },
          { id: 'b4', title: 'Add column drag and drop reordering', status: 'pending' },
        ],
      },
      codeChips: [
        { name: 'TaskList.tsx', changes: '+86', filePath: '/src/components/TaskList.tsx' },
        { name: 'KanbanBoard.tsx', changes: '+114', filePath: '/src/components/KanbanBoard.tsx' },
        { name: 'useTasks.ts', changes: '+24', filePath: '/src/hooks/useTasks.ts' },
      ],
      actionButtons: [
        { label: 'Review changes', action: 'review' },
        { label: 'Run the app', action: 'run', primary: true },
      ],
    },
  ],
  'product-research': [
    {
      id: 'pr-1',
      sender: 'user',
      timestamp: '10:27 AM',
      text: 'Go to the e-commerce site and research wireless headphones under $200. Compare the top 5 options and create a table for me with pros, cons, and ratings.',
    },
    {
      id: 'pr-2',
      sender: 'agent',
      timestamp: '10:27 AM',
      text: "I'll browse the e-commerce site, search for wireless headphones under $200, compare the top 5 options, and create a detailed comparison table for you.\n\nStarting the browser automation now...",
      plan: {
        title: 'Browser Automation Workflow',
        steps: [
          { id: 's1', title: 'Opening e-commerce website', status: 'completed', time: '10:28 AM' },
          { id: 's2', title: 'Searching for wireless headphones under $200', status: 'in_progress', time: 'In progress...' },
          { id: 's3', title: 'Extracting product details and reviews', status: 'pending' },
          { id: 's4', title: 'Comparing top 5 options', status: 'pending' },
          { id: 's5', title: 'Creating a comparison table with pros, cons, and ratings', status: 'pending' },
        ],
      },
      actionButtons: [
        { label: 'View Live Browser', action: 'open_browser', primary: true },
        { label: 'Pause Automation', action: 'pause_bot' },
      ],
    },
  ],
};

export const INITIAL_FILES: FileItem[] = [
  {
    name: 'src',
    path: '/src',
    type: 'folder',
    children: [
      {
        name: 'components',
        path: '/src/components',
        type: 'folder',
        children: [
          {
            name: 'TaskList.tsx',
            path: '/src/components/TaskList.tsx',
            type: 'file',
            language: 'typescript',
            modified: true,
            content: `import React, { useState, useEffect } from 'react';
import { Plus, Check, Trash2, Edit3, Search } from 'lucide-react';
import { useTasks } from '../hooks/useTasks';
import { Task, Filter } from '../types';

export function TaskList() {
  const { tasks, addTask, updateTask, deleteTask, setFilter, filter } = useTasks();
  const [newTask, setNewTask] = useState('');

  const filteredTasks = tasks.filter(task => {
    if (filter === 'all') return true;
    if (filter === 'active') return !task.completed;
    if (filter === 'completed') return task.completed;
    return true;
  });

  const handleAddTask = () => {
    if (!newTask.trim()) return;
    addTask({
      id: crypto.randomUUID(),
      title: newTask.trim(),
      completed: false,
      createdAt: new Date().toISOString()
    });
    setNewTask('');
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">TaskFlow</h1>
          <p className="text-slate-400 text-sm">Stay focused. Get things done.</p>
        </div>
      </div>
    </div>
  );
}`,
          },
          {
            name: 'TaskItem.tsx',
            path: '/src/components/TaskItem.tsx',
            type: 'file',
            language: 'typescript',
            content: `import React, { useState } from 'react';
import { Check, Trash2, Edit3 } from 'lucide-react';

interface TaskItemProps {
  task: {
    id: string;
    title: string;
    completed: boolean;
    tag?: string;
  };
  onToggle: (id: string) => void;
  onEdit: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export const TaskItem: React.FC<TaskItemProps> = ({
  task,
  onToggle,
  onEdit,
  onDelete
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(task.title);

  return (
    <div className="flex items-center justify-between p-3.5 bg-slate-900/60 rounded-xl border border-slate-800/80 hover:border-slate-700 transition-all">
      <div className="flex items-center gap-3">
        <button
          onClick={() => onToggle(task.id)}
          className={\`w-5 h-5 rounded-md border flex items-center justify-center \${
            task.completed ? 'bg-blue-600 border-blue-500 text-white' : 'border-slate-600 hover:border-slate-400'
          }\`}
        >
          {task.completed && <Check className="w-3.5 h-3.5" />}
        </button>
        <span className={\`text-sm font-medium \${task.completed ? 'line-through text-slate-500' : 'text-slate-200'}\`}>
          {task.title}
        </span>
      </div>
    </div>
  );
};`,
          },
          {
            name: 'KanbanBoard.tsx',
            path: '/src/components/KanbanBoard.tsx',
            type: 'file',
            language: 'typescript',
            content: `import React, { useState, useMemo } from 'react';
import { Task, TaskStatus } from '@/types/task';

interface KanbanBoardProps {
  tasks: Task[];
  onTaskMove: (id: string, status: TaskStatus) => void;
}

export function KanbanBoard({ tasks, onTaskMove }: KanbanBoardProps) {
  const columns: { id: TaskStatus; title: string; count: number }[] = [
    { id: 'todo', title: 'To Do', count: 3 },
    { id: 'in-progress', title: 'In Progress', count: 2 },
    { id: 'review', title: 'Review', count: 1 },
    { id: 'done', title: 'Done', count: 4 }
  ];

  return (
    <div className="grid grid-cols-4 gap-4 p-4">
      {columns.map(col => (
        <div key={col.id} className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-sm text-slate-200">{col.title}</h3>
            <span className="text-xs bg-slate-800 px-2 py-0.5 rounded-full text-slate-400">{col.count}</span>
          </div>
        </div>
      ))}
    </div>
  );
}`,
          },
        ],
      },
      {
        name: 'hooks',
        path: '/src/hooks',
        type: 'folder',
        children: [
          {
            name: 'useTasks.ts',
            path: '/src/hooks/useTasks.ts',
            type: 'file',
            language: 'typescript',
            content: `import { useState, useEffect } from 'react';
import { Task } from '../types';

export function useTasks() {
  const [tasks, setTasks] = useState<Task[]>(() => {
    const saved = localStorage.getItem('aetherius-tasks');
    return saved ? JSON.parse(saved) : [];
  });
  const [filter, setFilter] = useState<'all' | 'active' | 'completed'>('all');

  useEffect(() => {
    localStorage.setItem('aetherius-tasks', JSON.stringify(tasks));
  }, [tasks]);

  const addTask = (task: Task) => setTasks(prev => [task, ...prev]);
  const deleteTask = (id: string) => setTasks(prev => prev.filter(t => t.id !== id));
  const updateTask = (id: string, updates: Partial<Task>) =>
    setTasks(prev => prev.map(t => t.id === id ? { ...t, ...updates } : t));

  return { tasks, addTask, deleteTask, updateTask, filter, setFilter };
}`,
          },
        ],
      },
      {
        name: 'types.ts',
        path: '/src/types.ts',
        type: 'file',
        language: 'typescript',
        content: `export interface Task {
  id: string;
  title: string;
  completed: boolean;
  priority?: 'High' | 'Medium' | 'Low';
  tag?: string;
  createdAt: string;
}

export type Filter = 'all' | 'active' | 'completed';`,
      },
      {
        name: 'App.tsx',
        path: '/src/App.tsx',
        type: 'file',
        language: 'typescript',
        content: `import React from 'react';
import { TaskList } from './components/TaskList';

export default function App() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <TaskList />
    </main>
  );
}`,
      },
    ],
  },
  {
    name: 'package.json',
    path: '/package.json',
    type: 'file',
    language: 'json',
    content: `{
  "name": "aetherius-task-manager",
  "version": "0.1.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^19.0.0",
    "lucide-react": "^0.546.0"
  }
}`,
  },
];

export const INITIAL_TASKS: TaskItem[] = [
  { id: 't1', title: 'Design the new landing page', status: 'todo', priority: 'High', tag: 'Web', dueDate: 'Apr 12', assignee: 'Luna' },
  { id: 't2', title: 'Implement user authentication', status: 'in-progress', priority: 'Medium', tag: 'Backend', dueDate: 'Apr 10', assignee: 'Dev' },
  { id: 't3', title: 'Create product demo video', status: 'todo', priority: 'Medium', tag: 'Marketing', dueDate: 'Apr 15', assignee: 'Aria' },
  { id: 't4', title: 'Plan Q2 roadmap & milestones', status: 'done', priority: 'Low', tag: 'Planning', dueDate: 'Apr 8', assignee: 'Atlas' },
  { id: 't5', title: 'Update documentation & API specs', status: 'todo', priority: 'Low', tag: 'Docs', dueDate: 'Apr 16', assignee: 'Echo' },
  { id: 't6', title: 'Review pull requests & security audit', status: 'review', priority: 'Medium', tag: 'Development', dueDate: 'Apr 14', assignee: 'Nova' },
];

export const TEAM_AGENTS: TeamAgent[] = [
  {
    id: 'agent-atlas',
    name: 'Atlas',
    role: 'Project Lead',
    specialty: 'Coordination & Architecture',
    avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200&auto=format&fit=crop&q=80',
    status: 'active',
    currentTask: 'Coordinating sprint delivery and cross-agent tasks',
    recentActivity: 'Reviewed task manager specifications',
    speaking: true,
    speechText: 'Sprint roadmap is on schedule. Luna and Dev are aligned on component architecture.',
  },
  {
    id: 'agent-luna',
    name: 'Luna',
    role: 'Design',
    specialty: 'UI/UX & Creative Systems',
    avatarUrl: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=200&auto=format&fit=crop&q=80',
    status: 'active',
    currentTask: 'Refining high-contrast dark theme color palette',
    recentActivity: 'Published new Kanban visual design system',
    speaking: false,
    speechText: 'I tuned the border radiuses and active card glow for optimal focus.',
  },
  {
    id: 'agent-dev',
    name: 'Dev',
    role: 'Development',
    specialty: 'Full-Stack & Systems Engineering',
    avatarUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200&auto=format&fit=crop&q=80',
    status: 'active',
    currentTask: 'Optimizing state re-renders and local storage caching',
    recentActivity: 'Committed useTasks hook and bulk selection reducer',
  },
  {
    id: 'agent-aria',
    name: 'Aria',
    role: 'Research',
    specialty: 'Deep Research & Market Data',
    avatarUrl: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=200&auto=format&fit=crop&q=80',
    status: 'in_call',
    currentTask: 'Analyzing wireless headphones pricing under $200',
    recentActivity: 'Found 32 options, compiling comparative specs',
  },
  {
    id: 'agent-sage',
    name: 'Sage',
    role: 'Strategy',
    specialty: 'Product Strategy & GTM',
    avatarUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=200&auto=format&fit=crop&q=80',
    status: 'active',
    currentTask: 'Refining go-to-market and positioning',
    recentActivity: 'Generated strategic recommendations for v1 launch',
  },
  {
    id: 'agent-orion',
    name: 'Orion',
    role: 'Data',
    specialty: 'Data Pipelines & Analytics',
    avatarUrl: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200&auto=format&fit=crop&q=80',
    status: 'active',
    currentTask: 'Monitoring automated telemetry and latency',
    recentActivity: 'Analyzed benchmark latency across LLM models',
  },
  {
    id: 'agent-nova',
    name: 'Nova',
    role: 'QA & Testing',
    specialty: 'Automated E2E & Code Review',
    avatarUrl: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200&auto=format&fit=crop&q=80',
    status: 'reviewing',
    currentTask: 'Executing automated test suite across browsers',
    recentActivity: '0 bugs found on task completion and delete operations',
  },
  {
    id: 'agent-kai',
    name: 'Kai',
    role: 'Operations',
    specialty: 'Cloud Deployments & SRE',
    avatarUrl: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=200&auto=format&fit=crop&q=80',
    status: 'active',
    currentTask: 'Managing Cloud Run container lifecycle',
    recentActivity: 'Vite dev server healthy on port 3000',
  },
];

export const INITIAL_TERMINAL_LINES: TerminalLine[] = [
  { id: 't-1', type: 'info', text: '[10:24:12] ▶ Starting Aetherius Agent', time: '10:24:12' },
  { id: 't-2', type: 'info', text: '           Environment: task-manager', time: '10:24:12' },
  { id: 't-3', type: 'info', text: '           Runtime: Node.js v22.14.0', time: '10:24:12' },
  { id: 't-4', type: 'info', text: '           Working directory: /workspace/projects/task-manager', time: '10:24:12' },
  { id: 't-5', type: 'step', text: '▶ 1 Checking environment', time: '10:24:13' },
  { id: 't-6', type: 'success', text: '  ✔ Node.js version: v22.14.0' },
  { id: 't-7', type: 'success', text: '  ✔ npm version: 10.9.0' },
  { id: 't-8', type: 'success', text: '  ✔ Project detected: React + TypeScript + Vite' },
  { id: 't-9', type: 'success', text: '  ✔ Environment variables: .env.local' },
  { id: 't-10', type: 'step', text: '▶ 2 Installing dependencies', time: '10:24:13' },
  { id: 't-11', type: 'command', text: '  ▷ npm install' },
  { id: 't-12', type: 'info', text: '  added 142 packages, and audited 143 packages in 1.8s' },
  { id: 't-13', type: 'success', text: '  found 0 vulnerabilities' },
  { id: 't-14', type: 'step', text: '▶ 3 Building application', time: '10:24:18' },
  { id: 't-15', type: 'command', text: '  ▷ npm run build' },
  { id: 't-16', type: 'info', text: '  vite build --mode production' },
  { id: 't-17', type: 'info', text: '  ✓ 786 modules transformed.' },
  { id: 't-18', type: 'success', text: '  dist/index.html                   0.45 kB │ gzip: 0.32 kB' },
  { id: 't-19', type: 'success', text: '  dist/assets/index-8f3a2c.js       214.67 kB │ gzip: 68.21 kB' },
  { id: 't-20', type: 'success', text: '  ✓ built in 4.27s' },
  { id: 't-21', type: 'step', text: '▶ 4 Starting development server', time: '10:24:18' },
  { id: 't-22', type: 'command', text: '  ▷ npm run dev' },
  { id: 't-23', type: 'success', text: '  VITE v6.2.3  ready in 387ms' },
  { id: 't-24', type: 'info', text: '  ➜  Local:   http://localhost:3000/' },
  { id: 't-25', type: 'info', text: '  ➜  Network: http://172.17.0.2:3000/' },
  { id: 't-26', type: 'success', text: '  ✔ Development server is running!' },
];
