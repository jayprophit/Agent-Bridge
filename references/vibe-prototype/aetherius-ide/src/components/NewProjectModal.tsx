import React, { useState } from 'react';
import {
  X,
  Plus,
  Layers,
  FileCode2,
  Server,
  BookOpen,
  Terminal,
  Check,
  Sparkles,
  ArrowRight,
  FolderPlus
} from 'lucide-react';
import { FileItem, ProjectSession } from '../types';

export interface ProjectTemplate {
  id: string;
  name: string;
  category: 'React App' | 'Node.js API' | 'Documentation Site' | 'Python Script';
  badge: string;
  icon: React.ElementType;
  description: string;
  features: string[];
  starterFiles: FileItem[];
  defaultFilePath: string;
}

export const PROJECT_TEMPLATES: ProjectTemplate[] = [
  {
    id: 'react-app',
    name: 'React 19 + Vite App',
    category: 'React App',
    badge: 'Frontend SPA',
    icon: FileCode2,
    description:
      'Modern, performant client-side application with React 19, Vite, Tailwind CSS, and Lucide icons.',
    features: ['React 19 + TypeScript', 'Tailwind CSS utility styling', 'Motion animations', 'Vite dev server'],
    defaultFilePath: '/src/App.tsx',
    starterFiles: [
      {
        name: 'src',
        path: '/src',
        type: 'folder',
        children: [
          {
            name: 'App.tsx',
            path: '/src/App.tsx',
            type: 'file',
            language: 'typescript',
            content: `import React, { useState } from 'react';\n\nexport default function App() {\n  const [count, setCount] = useState(0);\n  return (\n    <div className="p-8 max-w-xl mx-auto text-center font-sans">\n      <h1 className="text-3xl font-bold text-slate-100">Welcome to React 19</h1>\n      <p className="mt-2 text-slate-400">Created with Aetherius IDE</p>\n      <button \n        onClick={() => setCount(c => c + 1)}\n        className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg"\n      >\n        Clicked {count} times\n      </button>\n    </div>\n  );\n}`,
          },
          {
            name: 'main.tsx',
            path: '/src/main.tsx',
            type: 'file',
            language: 'typescript',
            content: `import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App';\n\nReactDOM.createRoot(document.getElementById('root')!).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>\n);`,
          },
        ],
      },
      {
        name: 'package.json',
        path: '/package.json',
        type: 'file',
        language: 'json',
        content: `{\n  "name": "my-react-app",\n  "private": true,\n  "version": "0.1.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build"\n  }\n}`,
      },
    ],
  },
  {
    id: 'node-api',
    name: 'Node.js REST API',
    category: 'Node.js API',
    badge: 'Backend Microservice',
    icon: Server,
    description:
      'High-throughput Express backend with TypeScript, structured routers, middleware validation, and CORS.',
    features: ['Express 4.x + TypeScript', 'JSON API endpoints', 'CORS & Logging middleware', 'Clean route architecture'],
    defaultFilePath: '/src/server.ts',
    starterFiles: [
      {
        name: 'src',
        path: '/src',
        type: 'folder',
        children: [
          {
            name: 'server.ts',
            path: '/src/server.ts',
            type: 'file',
            language: 'typescript',
            content: `import express from 'express';\n\nconst app = express();\nconst PORT = 3000;\n\napp.use(express.json());\n\napp.get('/api/health', (req, res) => {\n  res.json({ status: 'ok', uptime: process.uptime(), timestamp: new Date() });\n});\n\napp.get('/api/items', (req, res) => {\n  res.json([\n    { id: 1, name: 'Item Alpha', status: 'ready' },\n    { id: 2, name: 'Item Beta', status: 'in-progress' }\n  ]);\n});\n\napp.listen(PORT, () => {\n  console.log(\`Server listening on http://localhost:\${PORT}\`);\n});`,
          },
          {
            name: 'routes.ts',
            path: '/src/routes.ts',
            type: 'file',
            language: 'typescript',
            content: `import { Router } from 'express';\n\nexport const apiRouter = Router();\napiRouter.get('/version', (req, res) => res.json({ version: '1.0.0' }));`,
          },
        ],
      },
      {
        name: 'package.json',
        path: '/package.json',
        type: 'file',
        language: 'json',
        content: `{\n  "name": "node-api-service",\n  "version": "1.0.0",\n  "main": "src/server.ts",\n  "scripts": {\n    "dev": "tsx watch src/server.ts"\n  }\n}`,
      },
    ],
  },
  {
    id: 'doc-site',
    name: 'Documentation Site',
    category: 'Documentation Site',
    badge: 'Docs & Knowledge',
    icon: BookOpen,
    description:
      'Structured technical documentation portal with markdown rendering, table of contents, and dark theme.',
    features: ['Markdown & MDX parsing', 'Nested category sidebar', 'Search indexing', 'Mobile responsive layout'],
    defaultFilePath: '/docs/getting-started.md',
    starterFiles: [
      {
        name: 'docs',
        path: '/docs',
        type: 'folder',
        children: [
          {
            name: 'getting-started.md',
            path: '/docs/getting-started.md',
            type: 'file',
            language: 'markdown',
            content: `# Getting Started\n\nWelcome to the developer documentation.\n\n## Quick Start\n\n\`\`\`bash\nnpm install\nnpm run dev\n\`\`\`\n\n### Key Concepts\n- Real-time agent collaboration\n- Instant hot-reloading dev server\n- Automated test runner`,
          },
          {
            name: 'architecture.md',
            path: '/docs/architecture.md',
            type: 'file',
            language: 'markdown',
            content: `# Architecture Overview\n\nThis project employs a modular layered design with separate presentation and state layers.`,
          },
        ],
      },
      {
        name: 'README.md',
        path: '/README.md',
        type: 'file',
        language: 'markdown',
        content: `# Technical Documentation\n\nGenerated with Aetherius Doc Engine.`,
      },
    ],
  },
  {
    id: 'python-script',
    name: 'Python Data Script & API',
    category: 'Python Script',
    badge: 'Data & Scripting',
    icon: Terminal,
    description:
      'FastAPI and pandas scripting environment for data transformations, automated analytics, and endpoints.',
    features: ['Python 3.12 / FastAPI', 'Data analysis with Pandas', 'Automated data pipelines', 'Type hints with Pydantic'],
    defaultFilePath: '/main.py',
    starterFiles: [
      {
        name: 'main.py',
        path: '/main.py',
        type: 'file',
        language: 'python',
        content: `from fastapi import FastAPI\nimport datetime\n\napp = FastAPI(title="Data Service")\n\n@app.get("/")\ndef root():\n    return {"message": "Data script active", "time": datetime.datetime.now().isoformat()}\n\n@app.get("/analyze")\ndef analyze(metric: str = "velocity"):\n    return {"metric": metric, "score": 98.4, "status": "optimal"}`,
      },
      {
        name: 'requirements.txt',
        path: '/requirements.txt',
        type: 'file',
        language: 'text',
        content: `fastapi>=0.110.0\nuvicorn>=0.28.0\npydantic>=2.6.0\npandas>=2.2.0`,
      },
    ],
  },
];

interface NewProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateProject: (project: {
    name: string;
    description: string;
    template: ProjectTemplate;
  }) => void;
}

export const NewProjectModal: React.FC<NewProjectModalProps> = ({
  isOpen,
  onClose,
  onCreateProject,
}) => {
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('react-app');
  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');

  if (!isOpen) return null;

  const selectedTemplate =
    PROJECT_TEMPLATES.find((t) => t.id === selectedTemplateId) || PROJECT_TEMPLATES[0];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const finalName = projectName.trim() || selectedTemplate.name;
    onCreateProject({
      name: finalName,
      description: projectDescription.trim() || selectedTemplate.description,
      template: selectedTemplate,
    });
    onClose();
  };

  return (
    <div
      id="new-project-modal-backdrop"
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        id="new-project-modal-content"
        className="w-full max-w-3xl bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30 flex items-center justify-center shadow-[0_0_15px_rgba(37,99,235,0.3)]">
              <FolderPlus className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Create New Project
              </h2>
              <p className="text-xs text-slate-400">
                Choose a project template to initialize your workspace & starter files
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Template Selection Grid */}
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-2.5">
              1. Select Project Template
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {PROJECT_TEMPLATES.map((tmpl) => {
                const isSelected = tmpl.id === selectedTemplateId;
                const Icon = tmpl.icon;
                return (
                  <div
                    key={tmpl.id}
                    onClick={() => {
                      setSelectedTemplateId(tmpl.id);
                      if (!projectName) {
                        setProjectName(tmpl.name);
                      }
                    }}
                    className={`p-4 rounded-xl border cursor-pointer transition-all duration-150 relative ${
                      isSelected
                        ? 'bg-blue-600/15 border-blue-500 ring-1 ring-blue-500 shadow-[0_0_20px_rgba(37,99,235,0.25)]'
                        : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2.5">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                            isSelected
                              ? 'bg-blue-600 text-white'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          <Icon className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-sm font-bold text-slate-100">{tmpl.name}</div>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-cyan-400 border border-slate-700">
                            {tmpl.badge}
                          </span>
                        </div>
                      </div>

                      {isSelected && (
                        <div className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0">
                          <Check className="w-3 h-3" />
                        </div>
                      )}
                    </div>

                    <p className="text-xs text-slate-400 line-clamp-2 mb-3 leading-relaxed">
                      {tmpl.description}
                    </p>

                    <div className="flex flex-wrap gap-1.5">
                      {tmpl.features.map((feat, idx) => (
                        <span
                          key={idx}
                          className="text-[10px] px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800"
                        >
                          {feat}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Project Details Form */}
          <div className="space-y-4 pt-2 border-t border-slate-800/80">
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider">
              2. Project Details
            </label>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder={`e.g., ${selectedTemplate.name}`}
                  className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-sans"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Description (Optional)
                </label>
                <input
                  type="text"
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="e.g., Client dashboard portal with live charts"
                  className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-sans"
                />
              </div>
            </div>

            {/* Template Starter Files Preview */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-xl">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                <span className="font-semibold text-slate-300">
                  Included Starter Files ({selectedTemplate.starterFiles.length})
                </span>
                <span className="font-mono text-[10px] text-cyan-400">
                  Initial Entry: {selectedTemplate.defaultFilePath}
                </span>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-mono">
                {selectedTemplate.starterFiles.map((file) => (
                  <span
                    key={file.path}
                    className="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 flex items-center gap-1.5"
                  >
                    <FileCode2 className="w-3 h-3 text-blue-400" />
                    {file.name}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="pt-4 border-t border-slate-800 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-900 border border-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center gap-2 shadow-[0_0_20px_rgba(37,99,235,0.4)] transition-all cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Create Project</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
