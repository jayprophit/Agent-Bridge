import React from 'react';
import {
  Home,
  FolderClosed,
  LayoutGrid,
  Layers,
  Send,
  Settings,
  Sparkles,
  Zap,
  GitBranch,
} from 'lucide-react';

interface SidebarRailProps {
  activeTab: string;
  onSelectTab: (tab: string) => void;
  onOpenSettings: () => void;
}

export const SidebarRail: React.FC<SidebarRailProps> = ({
  activeTab,
  onSelectTab,
  onOpenSettings,
}) => {
  const navItems = [
    { id: 'home', label: 'Home', icon: Home },
    { id: 'projects', label: 'Projects', icon: FolderClosed },
    { id: 'version-control', label: 'Git', icon: GitBranch },
    { id: 'templates', label: 'Templates', icon: LayoutGrid },
    { id: 'integrations', label: 'Integrations', icon: Layers },
    { id: 'deployments', label: 'Deployments', icon: Send },
  ];

  return (
    <aside className="w-16 bg-slate-950 border-r border-slate-800/80 flex flex-col items-center justify-between py-3 shrink-0 select-none z-20">
      {/* Top Nav Icons */}
      <div className="flex flex-col items-center gap-2 w-full">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`relative group flex flex-col items-center justify-center w-12 h-12 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-[0_0_15px_rgba(59,130,246,0.2)]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
              title={item.label}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-blue-500 rounded-r-full" />
              )}
              <Icon className="w-5 h-5" />
              <span className="text-[9px] mt-1 font-medium">{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Bottom Settings & Usage */}
      <div className="flex flex-col items-center gap-3 w-full px-2">
        <button
          onClick={onOpenSettings}
          className={`flex flex-col items-center justify-center w-12 h-12 rounded-xl transition-all text-slate-400 hover:text-slate-200 hover:bg-slate-900 ${
            activeTab === 'settings' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : ''
          }`}
          title="Settings"
        >
          <Settings className="w-5 h-5" />
          <span className="text-[9px] mt-1 font-medium">Settings</span>
        </button>

        {/* Pro Plan Usage Bar (from screenshots: Usage 68% Pro Plan) */}
        <div className="w-full bg-slate-900/90 rounded-lg p-1.5 border border-slate-800 text-center">
          <div className="flex items-center justify-between text-[8px] text-slate-400 mb-1">
            <span>Usage</span>
            <span className="font-mono text-cyan-400">68%</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-blue-500 to-cyan-400 h-full rounded-full"
              style={{ width: '68%' }}
            />
          </div>
          <div className="mt-1 text-[8px] font-semibold text-slate-300">Pro Plan</div>
        </div>
      </div>
    </aside>
  );
};
