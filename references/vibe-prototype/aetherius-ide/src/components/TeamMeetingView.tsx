import React, { useState } from 'react';
import {
  Mic,
  MicOff,
  Video,
  VideoOff,
  Hand,
  MessageSquare,
  Users,
  Settings,
  PhoneOff,
  Volume2,
  Sparkles,
  Radio,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldCheck,
  Zap
} from 'lucide-react';
import { TEAM_AGENTS } from '../data/mockData';
import { TeamAgent } from '../types';

interface TeamMeetingViewProps {
  onLeaveMeeting: () => void;
  onTalkToAgent?: (agent: TeamAgent) => void;
}

export const TeamMeetingView: React.FC<TeamMeetingViewProps> = ({
  onLeaveMeeting,
  onTalkToAgent,
}) => {
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoOn, setIsVideoOn] = useState(true);
  const [hasHandRaised, setHasHandRaised] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<TeamAgent>(TEAM_AGENTS[0]);
  const [silentMode, setSilentMode] = useState(false);

  const [queue, setQueue] = useState([
    { name: 'You', status: 'Next to speak' },
    { name: 'Atlas', status: 'Project Lead' },
    { name: 'Zuri', status: 'Marketing' },
    { name: 'Kai', status: 'Operations' },
    { name: 'Aria', status: 'Research' },
  ]);

  const [interAgentChats, setInterAgentChats] = useState([
    { from: 'Aria', to: 'Dev', text: 'Found a new dataset that might be useful for caching.', time: '10:14 AM' },
    { from: 'Dev', to: 'Aria', text: "Great! I'll integrate it into the state hook now.", time: '10:15 AM' },
    { from: 'Luna', to: 'Nova', text: 'Here are the updated high-contrast visuals for QA check.', time: '10:16 AM' },
    { from: 'Nova', to: 'Luna', text: 'They pass WCAG AA with flying colors! 0 contrast issues.', time: '10:17 AM' },
  ]);

  return (
    <div className="flex-1 flex flex-col h-full bg-[#070b14] text-slate-100 select-none overflow-hidden">
      {/* Top Banner */}
      <div className="h-12 border-b border-slate-800/80 px-4 sm:px-6 flex items-center justify-between bg-slate-950/90 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
            <span className="text-xs font-bold text-white tracking-wide uppercase">
              Team Meeting — All Hands
            </span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-600/20 text-rose-400 border border-rose-500/30">
              LIVE
            </span>
          </div>
          <span className="text-slate-500 hidden sm:inline">|</span>
          <span className="text-xs text-slate-400 hidden sm:inline">
            12/12 Autonomous Agents Active
          </span>
        </div>

        <div className="text-xs text-slate-400 italic hidden md:block">
          “Great things happen when everyone has a voice.”
        </div>
      </div>

      {/* Main Conference Content: Grid on Left/Center, Sidebars on Right */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Agent Video Matrix */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {TEAM_AGENTS.map((agent) => {
              const isSelected = selectedAgent.id === agent.id;
              return (
                <div
                  key={agent.id}
                  onClick={() => setSelectedAgent(agent)}
                  className={`relative aspect-video rounded-2xl overflow-hidden bg-slate-900 border-2 cursor-pointer transition-all group ${
                    agent.speaking
                      ? 'border-cyan-400 ring-4 ring-cyan-500/20 shadow-[0_0_20px_rgba(6,182,212,0.3)]'
                      : isSelected
                      ? 'border-blue-500'
                      : 'border-slate-800/80 hover:border-slate-700'
                  }`}
                >
                  <img
                    src={agent.avatarUrl}
                    alt={agent.name}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950/90 via-transparent to-transparent pointer-events-none" />

                  {/* Top Badge: Role */}
                  <div className="absolute top-2 left-2 flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-slate-950/80 border border-slate-800 text-[10px] text-slate-300 backdrop-blur-sm">
                    <span>{agent.role}</span>
                  </div>

                  {/* Speaking Waveform */}
                  {agent.speaking && (
                    <div className="absolute top-2 right-2 flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-cyan-500/20 border border-cyan-400/40 text-cyan-400 text-[10px] backdrop-blur-sm">
                      <Volume2 className="w-3 h-3 animate-pulse" />
                      <span className="font-mono">Live</span>
                    </div>
                  )}

                  {/* Bottom Identity */}
                  <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="text-xs font-bold text-white drop-shadow-sm">
                        {agent.name}
                      </span>
                    </div>

                    <Mic className="w-3 h-3 text-slate-400" />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Active Speaker Banner */}
          {selectedAgent && (
            <div className="p-4 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-blue-950/40 border border-slate-800 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <img
                  src={selectedAgent.avatarUrl}
                  alt={selectedAgent.name}
                  className="w-12 h-12 rounded-xl object-cover border border-cyan-400/40"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-bold text-white">{selectedAgent.name}</h4>
                    <span className="text-xs text-cyan-400 font-mono">
                      {selectedAgent.specialty}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 mt-0.5 leading-relaxed">
                    {selectedAgent.speechText || selectedAgent.currentTask}
                  </p>
                </div>
              </div>

              {onTalkToAgent && (
                <button
                  onClick={() => onTalkToAgent(selectedAgent)}
                  className="px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shrink-0 shadow-sm"
                >
                  Direct Chat →
                </button>
              )}
            </div>
          )}
        </div>

        {/* Right Sidebar: Queue & Inter-Agent Chat */}
        <div className="w-full lg:w-80 border-t lg:border-t-0 lg:border-l border-slate-800 bg-slate-950/80 flex flex-col justify-between shrink-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Conversation Queue */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-bold text-slate-200">
                <span>Conversation Queue</span>
                <span className="text-[10px] font-mono text-cyan-400">Auto-mod ON</span>
              </div>
              <div className="space-y-1.5">
                {queue.map((item, idx) => (
                  <div
                    key={item.name}
                    className={`flex items-center justify-between p-2 rounded-lg text-xs ${
                      idx === 0
                        ? 'bg-blue-600/20 border border-blue-500/40 text-white'
                        : 'bg-slate-900/60 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-4 h-4 rounded-full bg-slate-800 text-[10px] font-bold flex items-center justify-center text-slate-400 font-mono">
                        {idx + 1}
                      </span>
                      <span className="font-semibold">{item.name}</span>
                    </div>
                    <span className="text-[10px] text-slate-400">{item.status}</span>
                  </div>
                ))}
              </div>

              <button
                onClick={() => setHasHandRaised(!hasHandRaised)}
                className={`w-full py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                  hasHandRaised
                    ? 'bg-amber-600/20 text-amber-400 border-amber-500/40'
                    : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
                }`}
              >
                {hasHandRaised ? '✋ Hand Raised in Queue' : 'Request to Speak'}
              </button>
            </div>

            {/* Inter-Agent Live Feed */}
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between text-xs font-bold text-slate-200">
                <span className="flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
                  Inter-Agent Messages
                </span>
                <span className="text-[10px] text-slate-400 font-mono">LIVE</span>
              </div>

              <div className="space-y-2">
                {interAgentChats.map((c, i) => (
                  <div key={i} className="p-2 rounded-lg bg-slate-900/80 border border-slate-800 text-[11px] space-y-1">
                    <div className="flex items-center justify-between font-mono text-[10px]">
                      <span className="text-cyan-400 font-bold">
                        {c.from} → {c.to}
                      </span>
                      <span className="text-slate-500">{c.time}</span>
                    </div>
                    <p className="text-slate-300 leading-snug">{c.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Meeting Controls Toggles */}
          <div className="p-3 border-t border-slate-800 bg-slate-950 space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-300">
              <span>Push to Talk (Space)</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>
            <div className="flex items-center justify-between text-slate-300">
              <span>Silent Mode (Text Only)</span>
              <input
                type="checkbox"
                checked={silentMode}
                onChange={() => setSilentMode(!silentMode)}
                className="rounded bg-slate-800 border-slate-700 text-blue-600 focus:ring-0"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Meeting Control Bar */}
      <div className="h-16 bg-slate-950 border-t border-slate-800/80 px-6 flex items-center justify-between shrink-0 select-none">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsMuted(!isMuted)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all ${
              isMuted
                ? 'bg-rose-600/20 text-rose-400 border border-rose-500/40'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800'
            }`}
          >
            {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4 text-cyan-400" />}
            <span>{isMuted ? 'Unmute' : 'Mute'}</span>
          </button>

          <button
            onClick={() => setIsVideoOn(!isVideoOn)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all ${
              !isVideoOn
                ? 'bg-rose-600/20 text-rose-400 border border-rose-500/40'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800'
            }`}
          >
            {!isVideoOn ? <VideoOff className="w-4 h-4" /> : <Video className="w-4 h-4 text-indigo-400" />}
            <span>{isVideoOn ? 'Stop Video' : 'Start Video'}</span>
          </button>

          <button
            onClick={() => setHasHandRaised(!hasHandRaised)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all ${
              hasHandRaised
                ? 'bg-amber-600/20 text-amber-400 border border-amber-500/40'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800'
            }`}
          >
            <Hand className="w-4 h-4" />
            <span>Raise Hand</span>
          </button>
        </div>

        {/* Leave Meeting Button */}
        <button
          onClick={onLeaveMeeting}
          className="flex items-center gap-2 px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow-lg shadow-rose-600/20 transition-all"
        >
          <PhoneOff className="w-4 h-4" />
          <span>Leave</span>
        </button>
      </div>
    </div>
  );
};
