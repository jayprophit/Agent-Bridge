import React, { useState } from 'react';
import { Sparkles, Mic, Video, ChevronUp, ChevronDown, Volume2, ShieldCheck } from 'lucide-react';
import { ThemeType } from '../types';

interface AvatarHologramProps {
  theme: ThemeType;
  onStartVoiceCall?: () => void;
  onStartVideoCall?: () => void;
  isSpeaking?: boolean;
}

export const AvatarHologram: React.FC<AvatarHologramProps> = ({
  theme,
  onStartVoiceCall,
  onStartVideoCall,
  isSpeaking = false,
}) => {
  const [collapsed, setCollapsed] = useState(true);

  // Hologram cyber art styled SVG & CSS
  return (
    <div className="relative border-b border-slate-800/80 bg-gradient-to-b from-slate-900/40 to-transparent transition-all duration-300">
      {/* Collapsible toggle */}
      <div className="flex items-center justify-between px-3 py-1.5 text-xs">
        <div className="flex items-center gap-2 font-semibold tracking-wider text-cyan-400 uppercase text-[11px]">
          <Sparkles className="w-3 h-3 text-cyan-400 animate-pulse" />
          <span>Neural Presence</span>
          <span className="inline-flex items-center gap-1 ml-1 px-1.5 py-0.5 rounded-full text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
            Online
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={onStartVoiceCall}
            title="Voice Call with Aetherius"
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 border border-slate-700/60 transition-colors"
          >
            <Mic className="w-3.5 h-3.5 text-cyan-400" />
            <span>Voice</span>
          </button>
          <button
            onClick={onStartVideoCall}
            title="Video Call with Aetherius"
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 border border-slate-700/60 transition-colors"
          >
            <Video className="w-3.5 h-3.5 text-indigo-400" />
            <span>Video</span>
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? "Expand Avatar" : "Collapse Avatar"}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
          >
            {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="relative px-6 pb-6 pt-2 flex flex-col md:flex-row items-center justify-between gap-6 overflow-hidden">
          {/* Subtle background glow effect */}
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-cyan-500/10 via-indigo-600/5 to-transparent blur-2xl" />

          {/* Left Title */}
          <div className="z-10 max-w-xs text-center md:text-left">
            <div className="text-2xl lg:text-3xl font-extrabold tracking-tight text-white leading-tight">
              <div>Think</div>
              <div>Build</div>
              <div>Iterate</div>
              <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-indigo-400 bg-clip-text text-transparent drop-shadow-[0_0_15px_rgba(56,189,248,0.5)]">
                Together.
              </span>
            </div>
          </div>

          {/* Central Holographic Avatar Portrait */}
          <div className="relative z-10 flex flex-col items-center">
            <div className="relative w-36 h-36 sm:w-44 sm:h-44 rounded-full flex items-center justify-center">
              {/* Outer Energy Orbit Rings */}
              <div className="absolute inset-0 rounded-full border border-cyan-500/20 border-dashed animate-orbit" />
              <div className="absolute inset-2 rounded-full border border-indigo-500/30 animate-orbit-reverse" />
              <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-cyan-500/20 via-blue-500/10 to-indigo-500/20 blur-lg animate-pulse-glow" />

              {/* Avatar Face Container */}
              <div className="relative w-32 h-32 sm:w-36 sm:h-36 rounded-full overflow-hidden border-2 border-cyan-400/40 shadow-[0_0_35px_rgba(6,182,212,0.4)] bg-slate-950">
                <img
                  src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500&auto=format&fit=crop&q=80"
                  alt="Aetherius AI"
                  className="w-full h-full object-cover filter contrast-110 brightness-105 saturate-120"
                />
                
                {/* Cybernetic Blue Ethereal Overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-cyan-950/80 via-blue-900/30 to-transparent mix-blend-color-dodge pointer-events-none" />
                <div className="absolute inset-0 bg-gradient-to-b from-cyan-400/10 via-transparent to-blue-600/30 pointer-events-none" />
                
                {/* Scanline effect */}
                <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%)] bg-[length:100%_4px] pointer-events-none opacity-40" />

                {/* Floating cyber particles */}
                <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-slate-950/80 border border-cyan-400/40 text-[10px] text-cyan-300 backdrop-blur-sm shadow-sm">
                  <ShieldCheck className="w-3 h-3 text-cyan-400" />
                  <span>Aetherius v4</span>
                </div>
              </div>

              {/* Speaking waveform overlay if active */}
              {isSpeaking && (
                <div className="absolute -bottom-3 flex items-center gap-1 px-3 py-1 rounded-full bg-slate-900/90 border border-cyan-400 text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.6)]">
                  <Volume2 className="w-3.5 h-3.5 animate-bounce" />
                  <span className="text-[10px] font-mono font-bold tracking-wider">SPEAKING</span>
                  <div className="flex items-center gap-0.5 ml-1">
                    <span className="w-1 h-3 bg-cyan-400 rounded-full animate-pulse" />
                    <span className="w-1 h-4 bg-cyan-400 rounded-full animate-pulse delay-75" />
                    <span className="w-1 h-2 bg-cyan-400 rounded-full animate-pulse delay-150" />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Quote */}
          <div className="z-10 max-w-xs text-center md:text-right">
            <div className="text-xs lg:text-sm text-slate-300/90 font-medium leading-relaxed italic relative">
              <span className="text-cyan-400 font-serif text-xl mr-1">“</span>
              I'm Aetherius, your coding partner. I can help you plan, build, debug, and deploy — all in one place.
              <span className="text-cyan-400 font-serif text-xl ml-1">”</span>
            </div>
            <div className="mt-2 text-[11px] text-slate-400 font-mono flex items-center justify-center md:justify-end gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
              <span>Full Stack Agent • Context 2M</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
