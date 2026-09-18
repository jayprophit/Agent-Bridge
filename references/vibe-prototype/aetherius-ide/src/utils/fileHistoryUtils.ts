import { FileRevision } from '../types';

const STORAGE_PREFIX = 'aetherius_file_history_';
const MAX_REVISIONS_PER_FILE = 40;

/**
 * Calculates simple diff metrics (added / removed lines) between previous text and current text
 */
export const calculateDiffStats = (
  oldText: string,
  newText: string
): { addedLinesCount: number; removedLinesCount: number } => {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');

  const oldSet = new Set(oldLines);
  const newSet = new Set(newLines);

  let addedLinesCount = 0;
  let removedLinesCount = 0;

  for (const line of newLines) {
    if (!oldSet.has(line)) addedLinesCount++;
  }
  for (const line of oldLines) {
    if (!newSet.has(line)) removedLinesCount++;
  }

  return { addedLinesCount, removedLinesCount };
};

/**
 * Retrieves saved history revisions for a specific file path
 */
export const getFileHistory = (filePath: string): FileRevision[] => {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${filePath}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed;
    }
  } catch (err) {
    console.warn(`Failed to read file history for ${filePath}:`, err);
  }
  return [];
};

/**
 * Saves a new revision snapshot for a file
 */
export const saveFileRevision = (
  filePath: string,
  content: string,
  summary = 'Saved snapshot'
): FileRevision => {
  const currentHistory = getFileHistory(filePath);
  const latest = currentHistory[0];

  // If identical to latest snapshot, don't store redundant duplicate
  if (latest && latest.content === content) {
    return latest;
  }

  const prevContent = latest ? latest.content : '';
  const { addedLinesCount, removedLinesCount } = calculateDiffStats(prevContent, content);

  const now = new Date();
  const dateFormatted = now.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }) + ` · ${now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;

  const newRevision: FileRevision = {
    id: `rev-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    timestamp: Date.now(),
    dateFormatted,
    summary,
    content,
    addedLinesCount,
    removedLinesCount,
  };

  const updated = [newRevision, ...currentHistory].slice(0, MAX_REVISIONS_PER_FILE);

  try {
    localStorage.setItem(`${STORAGE_PREFIX}${filePath}`, JSON.stringify(updated));
  } catch (err) {
    console.warn(`Failed to write file history for ${filePath}:`, err);
  }

  return newRevision;
};

/**
 * Clear file history
 */
export const clearFileHistory = (filePath: string) => {
  try {
    localStorage.removeItem(`${STORAGE_PREFIX}${filePath}`);
  } catch (e) {
    console.warn('Failed to clear file history', e);
  }
};
