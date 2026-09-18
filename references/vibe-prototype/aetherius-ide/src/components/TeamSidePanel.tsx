import React, { useState } from 'react';
import {
  Users,
  Radio,
  Calendar,
  FileText,
  Activity,
  Sparkles,
  CheckCircle2,
  Video,
  Mic,
  Plus,
  Hash,
  MessageSquare,
  ShieldCheck,
  Zap,
  PhoneCall
} from 'lucide-react';
import { TEAM_AGENTS } from '../data/mockData';
import { TeamAgent } from '../types';

interface TeamSidePanelProps {
  onJoinMeeting?: () => void;
  onTalkToAgent?: (agent: TeamAgent) => void;
  onStartVoiceCall?: () => void;
  onStartVideoCall?: () => void;
}

export const TeamSidePanel: React.FC<TeamSidePanelProps> = ({
  onJoinMeeting,
  onTalkToAgent,
  onStartVoiceCall,
  onStartVideoCall,
}) => {
  const [activeTeamTab, setActiveTeamTab] = useState<'stage' | 'channels' | 'roster' | 'notes'>('stage');
  const [activeChannel, setActiveChannel] = useState('all-hands');

  const teamRail = [
    { id: 'stage', label: 'Stage', icon: Users },
    { id: 'channels', label: 'Rooms', icon: Radio },
    { id: 'roster', label: 'Roster', icon: Activity },
    { id: 'notes', label: 'Notes', icon: FileText },
  ];

  const channels = [
    { id: 'all-hands', name: '🎙️ Main All-Hands Room', active: true, count: 12 },
    { id: 'dev-war-room', name: '💻 Dev & Backend War Room', active: false, count: 4 },
    { id: 'design-critique', name: '🎨 Design & UX Critique', active: false, count: 3 },
    { id: 'qa-lab', name: '🧪 QA & Performance Lab', active: false, count: 2 },
  ];

  return (
    <div className="flex h-full shrink-0 select-none z-20">
      {/* Team Navigation Rail */}
      <aside className="w-14 bg-slate-950 border-r border-slate-800 flex flex-col items-center justify-between py-3 shrink-0">
        <div className="flex flex-col items-center gap-2 w-full">
          {teamRail.map((item) => {
            const Icon = item.icon;
            const isActive = activeTeamTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTeamTab(item.id as any)}
                className={`relative group flex flex-col items-center justify-center w-10 h-10 rounded-xl transition-all ${
                  isActive
                    ? 'bg-purple-600/20 text-purple-400 border border-purple-500/40 shadow-[0_0_12px_rgba(168,85,247,0.3)]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                }`}
                title={item.label}
              >
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-purple-500 rounded-r-full" />
                )}
                <Icon className="w-4 h-4" />
                <span className="text-[9px] mt-0.5 font-medium">{item.label}</span>
              </button>
            );
          })}
        </div>

        <div className="flex flex-col items-center gap-2">
          {onStartVideoCall && (
            <button
              onClick={onStartVideoCall}
              className="w-9 h-9 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-400 hover:bg-purple-600 hover:text-white transition-all"
              title="Start Live Video Huddle"
            >
              <Video className="w-4 h-4" />
            </button>
          )}
        </div>
      </aside>

      {/* Primary Team Side Drawer */}
      <aside className="w-64 sm:w-72 bg-slate-950/95 border-r border-slate-800 flex flex-col justify-between overflow-hidden">
        {/* Top Header */}
        <div className="p-3.5 space-y-3 border-b border-slate-800/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-purple-400" />
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                TEAM ALL-HANDS
              </span>
            </div>
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 text-[10px] font-mono flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              12 Online
            </span>
          </div>

          {/* Quick Meeting Action */}
          <button
            onClick={onJoinMeeting}
            className="w-full py-2 px-3 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(168,85,247,0.4)] transition-all cursor-pointer"
          >
            <Video className="w-4 h-4" />
            <span>Join Main Stage</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {/* Breakout Audio/Video Channels */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5 px-1">
              War Rooms & Channels
            </div>
            <div className="space-y-1">
              {channels.map((ch) => {
                const isSelected = activeChannel === ch.id;
                return (
                  <button
                    key={ch.id}
                    onClick={() => setActiveChannel(ch.id)}
                    className={`w-full flex items-center justify-between p-2 rounded-xl text-left text-xs transition-colors ${
                      isSelected
                        ? 'bg-purple-600/15 border border-purple-500/40 text-purple-300'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                    }`}
                  >
                    <span className="truncate">{ch.name}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-900 text-slate-500">
                      {ch.count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 12-Agent Roster Preview */}
          <div>
            <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5 px-1">
              <span>Agent Roster ({TEAM_AGENTS.length})</span>
              <span className="text-emerald-400">All Active</span>
            </div>
            <div className="space-y-1.5">
              {TEAM_AGENTS.map((agent) => (
                <div
                  key={agent.id}
                  onClick={() => onTalkToAgent && onTalkToAgent(agent)}
                  className="flex items-center justify-between p-2 rounded-xl bg-slate-900/60 hover:bg-slate-900 border border-slate-800/80 text-xs cursor-pointer group transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="relative shrink-0">
                      <img
                        src={agent.avatarUrl}
                        alt={agent.name}
                        className="w-6 h-6 rounded-full object-cover ring-1 ring-slate-700"
                        referrerPolicy="no-referrer"
                      />
                      <span className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-emerald-400 ring-1 ring-slate-950" />
                    </div>
                    <div className="truncate">
                      <div className="font-semibold text-slate-200 group-hover:text-white truncate">
                        {agent.name}
                      </div>
                      <div className="text-[10px] text-slate-500 truncate">{agent.role}</div>
                    </div>
                  </div>

                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400 font-mono shrink-0">
                    {agent.progress ?? 90}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom Sprint Progress Card */}
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/60">
          <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-200">Sprint 14 Velocity</span>
              <span className="text-cyan-400 font-mono text-[11px]">88%</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-purple-500 to-cyan-400 rounded-full w-[88%]" />
            </div>
            <div className="text-[10px] text-slate-500 flex justify-between font-mono pt-0.5">
              <span>32 / 36 Tasks</span>
              <span>2 Days left</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
};
