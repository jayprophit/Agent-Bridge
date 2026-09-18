import { KeybindingItem } from '../types';

export const isMacPlatform = (): boolean => {
  if (typeof window === 'undefined') return false;
  return navigator.platform.toUpperCase().indexOf('MAC') >= 0;
};

/**
 * Parses a key string like "Ctrl+Shift+P" into its components.
 */
export const parseKeybindingString = (keyStr: string) => {
  if (!keyStr) {
    return {
      hasCtrl: false,
      hasShift: false,
      hasAlt: false,
      hasMeta: false,
      mainKey: '',
    };
  }
  const parts = keyStr.split('+').map((p) => p.trim());
  const hasCtrl = parts.some((p) => (p || '').toLowerCase() === 'ctrl' || (p || '').toLowerCase() === 'cmd');
  const hasShift = parts.some((p) => (p || '').toLowerCase() === 'shift');
  const hasAlt = parts.some((p) => (p || '').toLowerCase() === 'alt' || (p || '').toLowerCase() === 'option');
  const hasMeta = parts.some((p) => (p || '').toLowerCase() === 'meta' || (p || '').toLowerCase() === 'command');

  // The primary key is the part that is not a modifier
  const modifierWords = ['ctrl', 'cmd', 'shift', 'alt', 'option', 'meta', 'command'];
  const mainKey = parts.find((p) => !modifierWords.includes((p || '').toLowerCase())) || '';

  return {
    hasCtrl,
    hasShift,
    hasAlt,
    hasMeta,
    mainKey,
  };
};

/**
 * Formats a keybinding string into an array of readable key tokens.
 * Adapts to Mac symbols if on Mac (⌘, ⇧, ⌥), or clean standard labels (Ctrl, Shift, Alt).
 */
export const formatKeyTokens = (keyStr: string, useMacSymbols = false): string[] => {
  if (!keyStr) return [];
  const parts = keyStr.split('+').map((p) => p.trim());
  
  if (!useMacSymbols) {
    return parts;
  }

  return parts.map((part) => {
    const lower = part.toLowerCase();
    if (lower === 'ctrl' || lower === 'cmd') return '⌘';
    if (lower === 'shift') return '⇧';
    if (lower === 'alt' || lower === 'option') return '⌥';
    if (lower === 'enter') return '↵';
    if (lower === 'backspace') return '⌫';
    return part.toUpperCase();
  });
};

/**
 * Checks if a native KeyboardEvent matches a configured keybinding string.
 */
export const doesEventMatchKeybinding = (
  e: KeyboardEvent,
  keyStr: string
): boolean => {
  if (!keyStr) return false;

  const { hasCtrl, hasShift, hasAlt, mainKey } = parseKeybindingString(keyStr);
  if (!mainKey) return false;

  const isMac = isMacPlatform();
  // Either Ctrl or Command can satisfy hasCtrl
  const eventHasCtrlOrCmd = isMac ? e.metaKey || e.ctrlKey : e.ctrlKey;

  // Verify modifiers
  if (hasCtrl !== eventHasCtrlOrCmd) return false;
  if (hasShift !== e.shiftKey) return false;
  if (hasAlt !== e.altKey) return false;

  // Match main key
  const eventKey = e.key;
  if (!eventKey) return false;

  // Check direct case-insensitive match
  if (eventKey.toLowerCase() === mainKey.toLowerCase()) {
    return true;
  }

  // Handle specific code checks (e.g. backquote, digits)
  if (mainKey === '`' && (eventKey === '`' || e.code === 'Backquote')) {
    return true;
  }

  if (mainKey === 'Esc' || mainKey === 'Escape') {
    return eventKey === 'Escape';
  }

  return false;
};

/**
 * Constructs a normalized key combination string from a recorded KeyboardEvent.
 * Returns null if the user only pressed a modifier key (so they can continue holding it).
 */
export const recordKeyCombination = (e: KeyboardEvent): string | null => {
  const ignoredKeys = ['Control', 'Shift', 'Alt', 'Meta'];
  if (ignoredKeys.includes(e.key)) {
    return null;
  }

  const parts: string[] = [];

  const isMac = isMacPlatform();
  const hasCtrl = isMac ? e.metaKey || e.ctrlKey : e.ctrlKey;

  if (hasCtrl) {
    parts.push('Ctrl');
  }
  if (e.altKey) {
    parts.push('Alt');
  }
  if (e.shiftKey) {
    parts.push('Shift');
  }

  // Format the main key nicely
  let mainKey = e.key;
  if (mainKey === ' ') mainKey = 'Space';
  else if (mainKey === '`' || e.code === 'Backquote') mainKey = '`';
  else if (mainKey.length === 1) mainKey = mainKey.toUpperCase();
  else if (mainKey === 'Escape') mainKey = 'Esc';

  parts.push(mainKey);

  return parts.join('+');
};

/**
 * Finds if another action in keybindings is already assigned to the given key.
 */
export const findKeybindingConflict = (
  keybindings: KeybindingItem[],
  actionId: string,
  targetKey: string
): KeybindingItem | undefined => {
  if (!targetKey) return undefined;
  const normalizedTarget = targetKey.trim().toLowerCase();
  return keybindings.find(
    (kb) => kb.id !== actionId && (kb.currentKey || '').trim().toLowerCase() === normalizedTarget
  );
};
