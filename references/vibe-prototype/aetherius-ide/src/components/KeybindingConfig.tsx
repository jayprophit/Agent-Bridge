import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  RotateCcw,
  Keyboard,
  AlertTriangle,
  Check,
  X,
  Edit2,
  Sparkles,
  Command,
  HelpCircle,
  Save,
  CheckCircle2,
} from 'lucide-react';
import { KeybindingItem, KeybindingCategory } from '../types';
import {
  formatKeyTokens,
  recordKeyCombination,
  findKeybindingConflict,
  isMacPlatform,
  doesEventMatchKeybinding,
} from '../utils/keybindingUtils';

interface KeybindingConfigProps {
  keybindings: KeybindingItem[];
  onUpdateKeybinding: (id: string, newKey: string) => void;
  onResetKeybinding: (id: string) => void;
  onResetAllKeybindings: () => void;
}

export const KeybindingConfig: React.FC<KeybindingConfigProps> = ({
  keybindings,
  onUpdateKeybinding,
  onResetKeybinding,
  onResetAllKeybindings,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [recordingKey, setRecordingKey] = useState<string>('');
  const [conflictItem, setConflictItem] = useState<KeybindingItem | null>(null);
  const [useMacSymbols, setUseMacSymbols] = useState<boolean>(isMacPlatform());
  const [testPressedKey, setTestPressedKey] = useState<string | null>(null);
  const [matchedAction, setMatchedAction] = useState<KeybindingItem | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const recordingRef = useRef<HTMLDivElement>(null);

  const categories: string[] = ['All', 'Navigation', 'Editor', 'View', 'Agent & Tools'];

  // Count modified
  const modifiedCount = keybindings.filter((k) => k.currentKey !== k.defaultKey).length;

  // Listen for keypress when in recording mode
  useEffect(() => {
    if (!editingId) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      // If Escape pressed alone, cancel
      if (e.key === 'Escape') {
        setEditingId(null);
        setRecordingKey('');
        setConflictItem(null);
        return;
      }

      const recorded = recordKeyCombination(e);
      if (recorded) {
        setRecordingKey(recorded);
        const conflict = findKeybindingConflict(keybindings, editingId, recorded);
        setConflictItem(conflict || null);
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [editingId, keybindings]);

  // Apply new keybinding
  const handleSaveBinding = (id: string, newKey: string) => {
    if (!newKey.trim()) return;
    onUpdateKeybinding(id, newKey.trim());
    setToastMessage(`Updated shortcut to ${newKey}`);
    setTimeout(() => setToastMessage(null), 2000);
    setEditingId(null);
    setRecordingKey('');
    setConflictItem(null);
  };

  // Quick shortcut tester
  const handleTestKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const recorded = recordKeyCombination(e.nativeEvent);
    if (recorded) {
      setTestPressedKey(recorded);
      const matched = keybindings.find((kb) =>
        doesEventMatchKeybinding(e.nativeEvent, kb.currentKey)
      );
      setMatchedAction(matched || null);
    }
  };

  const filteredKeybindings = keybindings.filter((item) => {
    const matchesCategory =
      selectedCategory === 'All' || item.category === selectedCategory;
    const query = (searchQuery || '').toLowerCase();
    const matchesSearch =
      (item.name || '').toLowerCase().includes(query) ||
      (item.description || '').toLowerCase().includes(query) ||
      (item.currentKey || '').toLowerCase().includes(query) ||
      (item.category || '').toLowerCase().includes(query);
    return matchesCategory && matchesSearch;
  });

  const getCategoryColor = (cat: KeybindingCategory) => {
    switch (cat) {
      case 'Navigation':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'Editor':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'View':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
      case 'Agent & Tools':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="flex flex-col h-full space-y-3 select-none">
      {/* Search & Actions Bar */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search shortcut name, action, or key..."
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-8.5 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-sans"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Category Pills & Controls */}
        <div className="flex items-center justify-between gap-1 text-[11px] overflow-x-auto pb-0.5">
          <div className="flex items-center gap-1 shrink-0">
            {categories.map((cat) => {
              const isSelected = selectedCategory === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-2 py-0.5 rounded-md font-medium transition-all ${
                    isSelected
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 border border-slate-800/80'
                  }`}
                >
                  {cat}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            <button
              onClick={() => setUseMacSymbols(!useMacSymbols)}
              title={useMacSymbols ? 'Switch to standard labels (Ctrl)' : 'Switch to Mac symbols (⌘)'}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-colors ${
                useMacSymbols
                  ? 'bg-blue-500/20 text-cyan-300 border-blue-500/40'
                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
            >
              {useMacSymbols ? '⌘ Mac' : 'Ctrl Win/Linux'}
            </button>

            {modifiedCount > 0 && (
              <button
                onClick={onResetAllKeybindings}
                title="Reset all modified shortcuts to defaults"
                className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-900 hover:bg-red-500/20 text-slate-400 hover:text-red-300 border border-slate-800 hover:border-red-500/30 text-[10px] transition-colors"
              >
                <RotateCcw className="w-2.5 h-2.5" />
                <span>Reset ({modifiedCount})</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Active toast notification */}
      {toastMessage && (
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 text-[11px] animate-in fade-in">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Keybindings List */}
      <div className="flex-1 overflow-y-auto space-y-1.5 pr-0.5 max-h-[360px] custom-scrollbar">
        {filteredKeybindings.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs">
            No keyboard shortcuts matching "{searchQuery}"
          </div>
        ) : (
          filteredKeybindings.map((item) => {
            const isEditing = editingId === item.id;
            const isModified = item.currentKey !== item.defaultKey;
            const tokens = formatKeyTokens(item.currentKey, useMacSymbols);

            return (
              <div
                key={item.id}
                className={`p-2.5 rounded-lg border transition-all ${
                  isEditing
                    ? 'bg-blue-950/30 border-cyan-500/60 ring-1 ring-cyan-500/40'
                    : isModified
                    ? 'bg-slate-950/90 border-slate-700/80 hover:border-slate-600'
                    : 'bg-slate-950/50 border-slate-800/80 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-semibold text-slate-100 truncate">
                        {item.name}
                      </span>
                      <span
                        className={`text-[9px] px-1.5 py-0.2 rounded-full border font-mono ${getCategoryColor(
                          item.category
                        )}`}
                      >
                        {item.category}
                      </span>
                      {isModified && (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono">
                          Custom
                        </span>
                      )}
                    </div>
                    <p className="text-[10.5px] text-slate-400 mt-0.5 line-clamp-1 leading-snug">
                      {item.description}
                    </p>
                  </div>

                  {/* Shortcut Display or Recording Box */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {isEditing ? (
                      <div className="flex items-center gap-1" ref={recordingRef}>
                        <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-cyan-950/80 border border-cyan-400/60 text-cyan-300 font-mono text-[11px] animate-pulse">
                          <Keyboard className="w-3 h-3 text-cyan-400" />
                          <span>{recordingKey || 'Press shortcut...'}</span>
                        </div>
                        {recordingKey && (
                          <button
                            type="button"
                            onClick={() => handleSaveBinding(item.id, recordingKey)}
                            title="Confirm Shortcut"
                            className="p-1 rounded bg-blue-600 hover:bg-blue-500 text-white"
                          >
                            <Check className="w-3 h-3" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(null);
                            setRecordingKey('');
                            setConflictItem(null);
                          }}
                          title="Cancel"
                          className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        {/* Display styled key chips */}
                        <div
                          onClick={() => {
                            setEditingId(item.id);
                            setRecordingKey('');
                            setConflictItem(null);
                          }}
                          className="flex items-center gap-1 px-2 py-1 rounded-md bg-slate-900 border border-slate-700/80 hover:border-cyan-500/50 cursor-pointer transition-colors shadow-inner group"
                          title="Click to rebind shortcut"
                        >
                          {tokens.map((token, idx) => (
                            <React.Fragment key={idx}>
                              <kbd className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-700 text-[10px] font-mono text-cyan-300 font-semibold shadow-sm group-hover:text-cyan-200">
                                {token}
                              </kbd>
                              {idx < tokens.length - 1 && (
                                <span className="text-[10px] text-slate-500">+</span>
                              )}
                            </React.Fragment>
                          ))}
                          <Edit2 className="w-2.5 h-2.5 text-slate-500 group-hover:text-cyan-400 ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>

                        {/* Reset button if modified */}
                        {isModified && (
                          <button
                            type="button"
                            onClick={() => onResetKeybinding(item.id)}
                            title={`Reset to default: ${item.defaultKey}`}
                            className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800/80 transition-colors"
                          >
                            <RotateCcw className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Conflict Alert in Edit Mode */}
                {isEditing && conflictItem && (
                  <div className="mt-2 pt-2 border-t border-amber-500/20 flex items-center justify-between text-[11px] text-amber-300 bg-amber-950/30 p-1.5 rounded">
                    <div className="flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      <span>
                        Conflicts with <strong>{conflictItem.name}</strong> ({conflictItem.currentKey})
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleSaveBinding(item.id, recordingKey)}
                      className="px-1.5 py-0.5 rounded bg-amber-500/30 hover:bg-amber-500/50 text-amber-200 font-medium text-[10px]"
                    >
                      Override
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Interactive Shortcut Tester & Help Bar */}
      <div className="pt-2.5 border-t border-slate-800/90 space-y-2">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <div className="flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-cyan-400" />
            <span className="font-semibold text-slate-300">Shortcut Verification Sandbox</span>
          </div>
          <span className="text-[10px] text-slate-500">Live listener</span>
        </div>

        <div className="relative">
          <input
            type="text"
            readOnly
            onKeyDown={handleTestKeyDown}
            placeholder="Focus here & press any shortcut to test action..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 font-mono text-center cursor-pointer"
          />
          {testPressedKey && (
            <div className="mt-1.5 p-2 rounded-md bg-slate-950/90 border border-slate-800 flex items-center justify-between text-xs animate-in fade-in">
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400 text-[11px]">Detected:</span>
                <kbd className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-cyan-300 font-mono text-[10px]">
                  {testPressedKey}
                </kbd>
              </div>
              <div className="flex items-center gap-1">
                {matchedAction ? (
                  <span className="text-emerald-400 font-medium text-[11px] flex items-center gap-1">
                    <Check className="w-3 h-3 text-emerald-400" />
                    Triggers: {matchedAction.name}
                  </span>
                ) : (
                  <span className="text-slate-500 text-[11px]">Unassigned key</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
