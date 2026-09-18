import React, { useState } from 'react';
import {
  X,
  Wrench,
  Globe,
  Terminal,
  Cpu,
  Sparkles,
  Bot,
  ShieldCheck,
  Check,
  Zap,
  Layers,
  Keyboard,
  Sliders,
  RotateCcw,
  Palette,
  Eye,
  CheckCircle2
} from 'lucide-react';
import { KeybindingItem, TerminalPaletteId, TerminalPalette } from '../types';
import { KeybindingConfig } from './KeybindingConfig';
import { TERMINAL_PALETTES, DEFAULT_TERMINAL_PALETTE_ID } from '../data/terminalThemes';

interface ToolsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  keybindings?: KeybindingItem[];
  onUpdateKeybinding?: (id: string, newKey: string) => void;
  onResetKeybinding?: (id: string) => void;
  onResetAllKeybindings?: () => void;
  selectedModel?: string;
  onSelectModel?: (modelId: string) => void;
  terminalPaletteId?: TerminalPaletteId;
  onSelectTerminalPalette?: (id: TerminalPaletteId) => void;
  initialTab?: 'tools' | 'keybindings' | 'terminal';
}

export const ToolsDrawer: React.FC<ToolsDrawerProps> = ({
  isOpen,
  onClose,
  keybindings = [],
  onUpdateKeybinding = () => {},
  onResetKeybinding = () => {},
  onResetAllKeybindings = () => {},
  selectedModel = 'gemini-2.5-flash',
  onSelectModel,
  terminalPaletteId = DEFAULT_TERMINAL_PALETTE_ID,
  onSelectTerminalPalette = (_id: TerminalPaletteId) => {},
  initialTab = 'keybindings',
}) => {
  const [activeTab, setActiveTab] = useState<'tools' | 'keybindings' | 'terminal'>(initialTab);
  const [browserAuto, setBrowserAuto] = useState(true);
  const [terminalExec, setTerminalExec] = useState(true);
  const [codeRefactor, setCodeRefactor] = useState(true);
  const [localModel, setLocalModel] = useState(selectedModel);

  // Custom Color Customization state for Terminal
  const [customBg, setCustomBg] = useState<string>('');
  const [customFg, setCustomFg] = useState<string>('');
  const [customPrompt, setCustomPrompt] = useState<string>('');
  const [showColorPicker, setShowColorPicker] = useState(false);

  if (!isOpen) return null;

  const modifiedKeybindingsCount = keybindings.filter(
    (k) => k.currentKey !== k.defaultKey
  ).length;

  const activePalette: TerminalPalette =
    TERMINAL_PALETTES[terminalPaletteId] || TERMINAL_PALETTES[DEFAULT_TERMINAL_PALETTE_ID];

  const handleModelClick = (modelId: string) => {
    setLocalModel(modelId);
    if (onSelectModel) {
      onSelectModel(modelId);
    }
  };

  const handlePaletteSelect = (id: TerminalPaletteId) => {
    onSelectTerminalPalette(id);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex justify-end select-none animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl bg-slate-900 border-l border-slate-800 h-full p-5 flex flex-col justify-between overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex-1 flex flex-col overflow-hidden space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
                <Sliders className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Settings & IDE Configuration</h3>
                <p className="text-[11px] text-slate-400">
                  Keybindings, terminal themes & autonomous agent permissions
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Navigation Tabs (Shortcuts, Terminal Theme, Agent Tools) */}
          <div className="flex items-center bg-slate-950/80 p-1 rounded-lg border border-slate-800 shrink-0 gap-1">
            <button
              type="button"
              onClick={() => setActiveTab('keybindings')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-semibold transition-all ${
                activeTab === 'keybindings'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <Keyboard className="w-3.5 h-3.5" />
              <span>Keybindings</span>
              {modifiedKeybindingsCount > 0 && (
                <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-cyan-400 text-slate-950 font-bold ml-0.5">
                  {modifiedKeybindingsCount}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('terminal')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-semibold transition-all ${
                activeTab === 'terminal'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <Palette className="w-3.5 h-3.5" />
              <span>Terminal Themes</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('tools')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-semibold transition-all ${
                activeTab === 'tools'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <Wrench className="w-3.5 h-3.5" />
              <span>Agent & Model</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto min-h-0 custom-scrollbar pr-1">
            {activeTab === 'keybindings' ? (
              <KeybindingConfig
                keybindings={keybindings}
                onUpdateKeybinding={onUpdateKeybinding}
                onResetKeybinding={onResetKeybinding}
                onResetAllKeybindings={onResetAllKeybindings}
              />
            ) : activeTab === 'terminal' ? (
              <div className="space-y-5">
                {/* Active Terminal Theme Preview Card */}
                <div className="p-3 rounded-xl border border-slate-800 bg-slate-950/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-4 h-4 text-cyan-400" />
                      <span className="text-xs font-bold text-white">
                        Current Palette: {activePalette.name}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {activePalette.id}
                    </span>
                  </div>

                  {/* High-fidelity ANSI Terminal Live Preview Window */}
                  <div
                    style={{
                      backgroundColor: customBg || activePalette.bg,
                      color: customFg || activePalette.fg,
                      borderColor: activePalette.border,
                    }}
                    className="p-3 rounded-lg border font-mono text-[11px] leading-relaxed shadow-inner"
                  >
                    <div className="flex items-center gap-1.5 mb-2 pb-1 border-b border-white/10 text-[10px] opacity-70">
                      <span className="w-2 h-2 rounded-full bg-rose-500/80" />
                      <span className="w-2 h-2 rounded-full bg-amber-500/80" />
                      <span className="w-2 h-2 rounded-full bg-emerald-500/80" />
                      <span className="ml-2 truncate">task-manager • {activePalette.name}</span>
                    </div>

                    <div className="space-y-1">
                      <div>
                        <span
                          style={{ color: customPrompt || activePalette.prompt }}
                          className="font-bold mr-1"
                        >
                          ➜
                        </span>
                        <span style={{ color: activePalette.command }} className="font-semibold mr-1">
                          task-manager
                        </span>
                        <span className="opacity-60 text-[10px] mr-2">git:(main)</span>
                        <span style={{ color: activePalette.command }}>npm run dev</span>
                      </div>
                      <div style={{ color: activePalette.step }}>
                        ▶ aetherius-vite ready in 184ms
                      </div>
                      <div style={{ color: activePalette.success }}>
                        ✔ Local: http://localhost:5173/
                      </div>
                      <div style={{ color: activePalette.warn }}>
                        ⚡ 14 modules compiled
                      </div>
                    </div>
                  </div>

                  {/* Swatches strip */}
                  <div className="flex items-center gap-1.5 pt-1">
                    <span className="text-[10px] text-slate-400 font-sans mr-1">Palette ANSI:</span>
                    {[
                      { label: 'BG', color: activePalette.bg },
                      { label: 'FG', color: activePalette.fg },
                      { label: 'Prompt', color: activePalette.prompt },
                      { label: 'Cmd', color: activePalette.command },
                      { label: 'Step', color: activePalette.step },
                      { label: 'Success', color: activePalette.success },
                      { label: 'Warn', color: activePalette.warn },
                      { label: 'Error', color: activePalette.error },
                    ].map((sw, idx) => (
                      <div
                        key={idx}
                        className="w-5 h-5 rounded-md border border-white/20 shadow-sm flex items-center justify-center text-[8px] font-bold cursor-default"
                        style={{ backgroundColor: sw.color, color: idx === 0 ? '#fff' : '#000' }}
                        title={`${sw.label}: ${sw.color}`}
                      />
                    ))}
                  </div>
                </div>

                {/* Predefined ANSI Palettes Grid */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <Palette className="w-3.5 h-3.5 text-blue-400" />
                      <span>Predefined ANSI Palettes</span>
                    </label>
                    <span className="text-[10px] text-slate-400">
                      {Object.keys(TERMINAL_PALETTES).length} themes available
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {Object.values(TERMINAL_PALETTES).map((pal) => {
                      const isSelected = terminalPaletteId === pal.id;
                      return (
                        <div
                          key={pal.id}
                          onClick={() => handlePaletteSelect(pal.id)}
                          className={`p-3 rounded-xl border cursor-pointer transition-all ${
                            isSelected
                              ? 'bg-blue-600/20 border-blue-500 shadow-md ring-1 ring-blue-500'
                              : 'bg-slate-950/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-xs font-bold text-white">{pal.name}</span>
                            {isSelected && (
                              <span className="flex items-center gap-1 text-[10px] font-bold text-cyan-400 bg-cyan-400/15 px-1.5 py-0.5 rounded-full">
                                <Check className="w-3 h-3" /> Active
                              </span>
                            )}
                          </div>

                          <p className="text-[10px] text-slate-400 mb-2 leading-tight">
                            {pal.description}
                          </p>

                          {/* Mini Palette Swatch bar */}
                          <div
                            className="p-1.5 rounded-lg border border-white/10 flex items-center justify-between"
                            style={{ backgroundColor: pal.bg }}
                          >
                            <span
                              className="font-mono text-[9px] font-bold truncate max-w-[100px]"
                              style={{ color: pal.prompt }}
                            >
                              ➜ dev-server
                            </span>
                            <div className="flex items-center gap-1 shrink-0">
                              <span
                                className="w-2.5 h-2.5 rounded-full"
                                style={{ backgroundColor: pal.command }}
                              />
                              <span
                                className="w-2.5 h-2.5 rounded-full"
                                style={{ backgroundColor: pal.step }}
                              />
                              <span
                                className="w-2.5 h-2.5 rounded-full"
                                style={{ backgroundColor: pal.success }}
                              />
                              <span
                                className="w-2.5 h-2.5 rounded-full"
                                style={{ backgroundColor: pal.warn }}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Custom Color Overrides Accordion */}
                <div className="pt-3 border-t border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-bold text-slate-200">
                        Custom Color Overrides
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Fine-tune terminal background, foreground, and prompt accents
                      </div>
                    </div>
                    {(customBg || customFg || customPrompt) && (
                      <button
                        onClick={() => {
                          setCustomBg('');
                          setCustomFg('');
                          setCustomPrompt('');
                        }}
                        className="text-[10px] text-cyan-400 hover:underline flex items-center gap-1"
                      >
                        <RotateCcw className="w-3 h-3" /> Reset Custom
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                      <label className="text-[10px] text-slate-400 block font-semibold">
                        Background
                      </label>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="color"
                          value={customBg || activePalette.bg}
                          onChange={(e) => setCustomBg(e.target.value)}
                          className="w-6 h-6 rounded cursor-pointer border-0 bg-transparent p-0"
                        />
                        <span className="text-[10px] font-mono text-slate-300 truncate">
                          {customBg || activePalette.bg}
                        </span>
                      </div>
                    </div>

                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                      <label className="text-[10px] text-slate-400 block font-semibold">
                        Text / FG
                      </label>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="color"
                          value={customFg || activePalette.fg}
                          onChange={(e) => setCustomFg(e.target.value)}
                          className="w-6 h-6 rounded cursor-pointer border-0 bg-transparent p-0"
                        />
                        <span className="text-[10px] font-mono text-slate-300 truncate">
                          {customFg || activePalette.fg}
                        </span>
                      </div>
                    </div>

                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                      <label className="text-[10px] text-slate-400 block font-semibold">
                        Prompt Arrow
                      </label>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="color"
                          value={customPrompt || activePalette.prompt}
                          onChange={(e) => setCustomPrompt(e.target.value)}
                          className="w-6 h-6 rounded cursor-pointer border-0 bg-transparent p-0"
                        />
                        <span className="text-[10px] font-mono text-slate-300 truncate">
                          {customPrompt || activePalette.prompt}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                {/* AI Model Selector */}
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-cyan-400" />
                    <span>Primary Reasoning Engine</span>
                  </label>
                  <div className="space-y-2">
                    {[
                      {
                        id: 'gemini-2.5-flash',
                        name: 'Gemini 2.5 Flash',
                        desc: 'Fast, multimodal reasoning & live UI generation',
                      },
                      {
                        id: 'gemini-2.5-pro',
                        name: 'Gemini 2.5 Pro',
                        desc: 'Deep codebase comprehension & complex architectures',
                      },
                      {
                        id: 'aetherius-omni',
                        name: 'Aetherius Omni Swarm',
                        desc: '12-agent cooperative planning & peer review',
                      },
                    ].map((m) => (
                      <div
                        key={m.id}
                        onClick={() => handleModelClick(m.id)}
                        className={`p-2.5 rounded-xl border cursor-pointer transition-all ${
                          localModel === m.id
                            ? 'bg-blue-600/15 border-blue-500/60 text-white'
                            : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold">{m.name}</span>
                          {localModel === m.id && <Check className="w-3.5 h-3.5 text-cyan-400" />}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1">{m.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Tool Toggles */}
                <div className="space-y-2.5 pt-2 border-t border-slate-800">
                  <label className="text-xs font-bold text-slate-300">Tool Execution Permissions</label>

                  <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <Globe className="w-4 h-4 text-cyan-400" />
                      <div>
                        <div className="text-xs font-semibold text-slate-200">Headless Browser Sandbox</div>
                        <div className="text-[10px] text-slate-400">Allows autonomous navigation & research</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={browserAuto}
                      onChange={() => setBrowserAuto(!browserAuto)}
                      className="rounded bg-slate-800 border-slate-700 text-blue-600 focus:ring-0"
                    />
                  </div>

                  <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <Terminal className="w-4 h-4 text-emerald-400" />
                      <div>
                        <div className="text-xs font-semibold text-slate-200">Isolated Terminal Execution</div>
                        <div className="text-[10px] text-slate-400">Allows npm installs, builds, test execution</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={terminalExec}
                      onChange={() => setTerminalExec(!terminalExec)}
                      className="rounded bg-slate-800 border-slate-700 text-blue-600 focus:ring-0"
                    />
                  </div>

                  <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <Zap className="w-4 h-4 text-amber-400" />
                      <div>
                        <div className="text-xs font-semibold text-slate-200">Continuous Code Refactoring</div>
                        <div className="text-[10px] text-slate-400">Synthesizes updates straight into filesystem</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={codeRefactor}
                      onChange={() => setCodeRefactor(!codeRefactor)}
                      className="rounded bg-slate-800 border-slate-700 text-blue-600 focus:ring-0"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-slate-800 shrink-0">
          <button
            onClick={onClose}
            className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-600/30 transition-all"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
