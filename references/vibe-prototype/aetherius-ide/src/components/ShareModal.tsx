import React, { useState } from 'react';
import {
  Share2,
  Copy,
  Check,
  Globe,
  Lock,
  UserPlus,
  Users,
  X,
  QrCode,
  Shield,
  Eye,
  Edit3,
  Bot,
  ExternalLink
} from 'lucide-react';

interface ShareModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectName: string;
  projectId: string;
}

export const ShareModal: React.FC<ShareModalProps> = ({
  isOpen,
  onClose,
  projectName,
  projectId,
}) => {
  const [copied, setCopied] = useState(false);
  const [accessLevel, setAccessLevel] = useState<'view' | 'edit' | 'copilot'>('edit');
  const [inviteEmail, setInviteEmail] = useState('');
  const [invitedList, setInvitedList] = useState<string[]>([]);
  const [showQr, setShowQr] = useState(false);

  if (!isOpen) return null;

  // Use current origin or default shared preview app url
  const baseUrl =
    typeof window !== 'undefined' && window.location.origin && window.location.origin !== 'null'
      ? window.location.origin
      : 'https://ais-pre-hyykcmyr7f7ci2pu6ktgde-372118764882.europe-west1.run.app';
  
  const shareableUrl = `${baseUrl}?project=${encodeURIComponent(projectId)}&access=${accessLevel}`;

  const handleCopy = () => {
    navigator.clipboard.writeText(shareableUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInvitedList((prev) => [...prev, inviteEmail.trim()]);
    setInviteEmail('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in select-none">
      <div
        className="w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-white shadow-md">
              <Share2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                Share Workspace
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-blue-500/10 text-cyan-400 border border-blue-500/30">
                  Live Sync
                </span>
              </h3>
              <p className="text-[11px] text-slate-400">{projectName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 text-xs">
          {/* Shareable Link Box */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-300 mb-1.5 uppercase tracking-wider font-mono">
              Shareable Link
            </label>
            <div className="flex items-center gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-800 focus-within:border-cyan-500/60 transition-colors">
              <div className="p-1.5 text-slate-500">
                <Globe className="w-3.5 h-3.5 text-cyan-400" />
              </div>
              <input
                type="text"
                readOnly
                value={shareableUrl}
                className="flex-1 bg-transparent text-slate-200 font-mono text-[11px] outline-none truncate"
              />
              <button
                onClick={handleCopy}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all ${
                  copied
                    ? 'bg-emerald-600 text-white'
                    : 'bg-blue-600 hover:bg-blue-500 text-white'
                }`}
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Link</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Access Permissions Selector */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-300 mb-1.5 uppercase tracking-wider font-mono">
              Collaboration Permission
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setAccessLevel('view')}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  accessLevel === 'view'
                    ? 'bg-blue-600/20 border-cyan-500/50 text-white shadow-sm'
                    : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold text-xs mb-0.5">
                  <Eye className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Can View</span>
                </div>
                <p className="text-[10px] text-slate-400 line-clamp-1">Read-only preview</p>
              </button>

              <button
                type="button"
                onClick={() => setAccessLevel('edit')}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  accessLevel === 'edit'
                    ? 'bg-blue-600/20 border-cyan-500/50 text-white shadow-sm'
                    : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold text-xs mb-0.5">
                  <Edit3 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Can Edit</span>
                </div>
                <p className="text-[10px] text-slate-400 line-clamp-1">Live code changes</p>
              </button>

              <button
                type="button"
                onClick={() => setAccessLevel('copilot')}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  accessLevel === 'copilot'
                    ? 'bg-blue-600/20 border-cyan-500/50 text-white shadow-sm'
                    : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold text-xs mb-0.5">
                  <Bot className="w-3.5 h-3.5 text-indigo-400" />
                  <span>AI Co-pilot</span>
                </div>
                <p className="text-[10px] text-slate-400 line-clamp-1">Joint AI agent prompts</p>
              </button>
            </div>
          </div>

          {/* Invite Collaborators via Email */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-300 mb-1.5 uppercase tracking-wider font-mono">
              Invite Team Members
            </label>
            <form onSubmit={handleInvite} className="flex gap-2">
              <input
                type="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="flex-1 px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 text-xs focus:outline-none focus:border-cyan-500/60"
              />
              <button
                type="submit"
                disabled={!inviteEmail.trim()}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors"
              >
                <UserPlus className="w-3.5 h-3.5 text-cyan-400" />
                <span>Invite</span>
              </button>
            </form>
          </div>

          {/* Active Collaborators list */}
          <div className="bg-slate-950/50 rounded-xl p-3 border border-slate-800/80 space-y-2">
            <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">
              Workspace Members (4 Active)
            </span>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-[9px] font-bold text-white">
                    JD
                  </div>
                  <span className="text-slate-200">You (jprophit@gmail.com)</span>
                </div>
                <span className="text-[10px] text-slate-400 font-mono">Owner</span>
              </div>

              <div className="flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center text-[9px] font-bold text-white">
                    AT
                  </div>
                  <span className="text-slate-300">Atlas (AI Lead Agent)</span>
                </div>
                <span className="text-[10px] text-cyan-400 font-mono">Co-pilot</span>
              </div>

              <div className="flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-pink-600 flex items-center justify-center text-[9px] font-bold text-white">
                    LU
                  </div>
                  <span className="text-slate-300">Luna (Design Lead)</span>
                </div>
                <span className="text-[10px] text-emerald-400 font-mono">Editor</span>
              </div>

              {invitedList.map((email) => (
                <div key={email} className="flex items-center justify-between text-[11px] text-emerald-300">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full bg-slate-800 flex items-center justify-center text-[9px] font-bold text-emerald-400">
                      @
                    </div>
                    <span>{email}</span>
                  </div>
                  <span className="text-[10px] text-amber-400 font-mono">Invitation Pending</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-800/80 bg-slate-950 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>End-to-end encrypted live session</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
