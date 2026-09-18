import React, { useState, useEffect } from 'react';
import {
  Mic,
  MicOff,
  PhoneOff,
  Volume2,
  Video,
  VideoOff,
  Share2,
  MoreHorizontal,
  Sparkles,
  ShieldCheck
} from 'lucide-react';

interface VoiceVideoCallModalProps {
  type: 'voice' | 'video';
  onClose: () => void;
}

export const VoiceVideoCallModal: React.FC<VoiceVideoCallModalProps> = ({
  type,
  onClose,
}) => {
  const [seconds, setSeconds] = useState(24);
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoOff, setIsVideoOff] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(true);

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (totalSecs: number) => {
    const m = Math.floor(totalSecs / 60)
      .toString()
      .padStart(2, '0');
    const s = (totalSecs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/95 backdrop-blur-xl flex flex-col items-center justify-between p-6 sm:p-10 select-none animate-in fade-in duration-200">
      {/* Top Bar */}
      <div className="w-full max-w-4xl flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white shadow-md">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">
              {type === 'voice' ? 'Voice Call with Aetherius' : 'Video Call (Real-time)'}
            </h3>
            <p className="text-[11px] text-slate-400">
              {type === 'voice' ? 'Natural voice conversation' : 'Face to face. Anywhere in the world.'}
            </p>
          </div>
        </div>

        {/* Timer */}
        <div className="px-3 py-1 rounded-full bg-slate-900 border border-slate-800 font-mono text-sm text-cyan-400 font-bold">
          {formatTime(seconds)}
        </div>
      </div>

      {/* Center Avatar View */}
      <div className="relative flex flex-col items-center justify-center my-auto">
        <div className="relative w-64 h-64 sm:w-80 sm:h-80 rounded-full flex items-center justify-center">
          {/* Animated Glow Rings */}
          <div className="absolute -inset-4 rounded-full border border-cyan-500/30 animate-orbit" />
          <div className="absolute -inset-8 rounded-full border border-indigo-500/20 animate-orbit-reverse" />
          <div className="absolute -inset-2 rounded-full bg-gradient-to-tr from-cyan-500/20 via-blue-500/20 to-indigo-500/20 blur-xl animate-pulse-glow" />

          {/* Avatar Face */}
          <div className="relative w-56 h-56 sm:w-72 sm:h-72 rounded-full overflow-hidden border-4 border-cyan-400/60 shadow-[0_0_50px_rgba(6,182,212,0.5)] bg-slate-950">
            <img
              src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600&auto=format&fit=crop&q=80"
              alt="Aetherius"
              className="w-full h-full object-cover filter contrast-115 brightness-105 saturate-120"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-cyan-950/80 via-transparent to-transparent" />
          </div>

          {/* Picture-in-Picture User Camera if video */}
          {type === 'video' && !isVideoOff && (
            <div className="absolute -bottom-4 -right-4 w-28 h-28 rounded-2xl overflow-hidden border-2 border-slate-700 shadow-2xl bg-slate-900">
              <img
                src="https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200&auto=format&fit=crop&q=80"
                alt="You"
                className="w-full h-full object-cover"
              />
              <div className="absolute bottom-1 left-2 text-[10px] font-bold text-white bg-slate-950/70 px-1.5 rounded">
                You
              </div>
            </div>
          )}
        </div>

        {/* Dynamic Speech Waves */}
        <div className="mt-8 flex flex-col items-center gap-2">
          <div className="flex items-center gap-1.5 h-8">
            <span className="w-1.5 h-4 bg-cyan-400 rounded-full animate-pulse" />
            <span className="w-1.5 h-7 bg-cyan-400 rounded-full animate-pulse delay-75" />
            <span className="w-1.5 h-10 bg-blue-400 rounded-full animate-pulse delay-150" />
            <span className="w-1.5 h-6 bg-indigo-400 rounded-full animate-pulse delay-200" />
            <span className="w-1.5 h-9 bg-cyan-400 rounded-full animate-pulse delay-100" />
            <span className="w-1.5 h-3 bg-cyan-400 rounded-full animate-pulse" />
          </div>
          <span className="text-sm font-semibold text-cyan-300">
            {isSpeaking ? 'Listening to your thoughts...' : 'Aetherius is responding...'}
          </span>
        </div>
      </div>

      {/* Call Controls Bar */}
      <div className="w-full max-w-md flex items-center justify-center gap-4 py-4">
        <button
          onClick={() => setIsMuted(!isMuted)}
          className={`p-4 rounded-full border transition-all ${
            isMuted
              ? 'bg-rose-600/20 text-rose-400 border-rose-500/40'
              : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border-slate-700'
          }`}
          title={isMuted ? 'Unmute' : 'Mute'}
        >
          {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6 text-cyan-400" />}
        </button>

        {type === 'video' && (
          <button
            onClick={() => setIsVideoOff(!isVideoOff)}
            className={`p-4 rounded-full border transition-all ${
              isVideoOff
                ? 'bg-rose-600/20 text-rose-400 border-rose-500/40'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border-slate-700'
            }`}
            title={isVideoOff ? 'Turn Video On' : 'Turn Video Off'}
          >
            {isVideoOff ? <VideoOff className="w-6 h-6" /> : <Video className="w-6 h-6 text-indigo-400" />}
          </button>
        )}

        {/* End Call Button */}
        <button
          onClick={onClose}
          className="p-5 rounded-full bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/40 transition-all hover:scale-105"
          title="End Call"
        >
          <PhoneOff className="w-7 h-7" />
        </button>

        <button
          className="p-4 rounded-full bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 transition-all"
          title="Speaker / Audio Output"
        >
          <Volume2 className="w-6 h-6 text-slate-300" />
        </button>
      </div>
    </div>
  );
};
