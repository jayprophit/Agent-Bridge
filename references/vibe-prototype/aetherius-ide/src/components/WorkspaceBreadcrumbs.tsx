import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Folder,
  FolderOpen,
  FileCode2,
  ChevronRight,
  ChevronDown,
  ArrowUp,
  Copy,
  Check,
  ChevronLeft,
  Layers,
  FileText
} from 'lucide-react';
import { FileItem, RightSurfaceTab } from '../types';

interface WorkspaceBreadcrumbsProps {
  activeFilePath: string;
  projectName: string;
  files: FileItem[];
  onSelectFile: (path: string) => void;
  activeRightTab?: RightSurfaceTab;
}

export const WorkspaceBreadcrumbs: React.FC<WorkspaceBreadcrumbsProps> = ({
  activeFilePath,
  projectName,
  files,
  onSelectFile,
  activeRightTab = 'code',
}) => {
  const [activeDropdownPath, setActiveDropdownPath] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setActiveDropdownPath(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Compute breadcrumb segments from activeFilePath
  const segments = useMemo(() => {
    const cleanProjectName = (projectName || 'project').toLowerCase().replace(/\s+/g, '-');
    const parts = (activeFilePath || '').split('/').filter(Boolean);
    const segs: { name: string; fullPath: string; isFolder: boolean }[] = [
      { name: cleanProjectName, fullPath: '/', isFolder: true },
    ];

    let current = '';
    for (let i = 0; i < parts.length; i++) {
      current += '/' + parts[i];
      const isFile = i === parts.length - 1;
      segs.push({
        name: parts[i],
        fullPath: current,
        isFolder: !isFile,
      });
    }
    return segs;
  }, [activeFilePath, projectName]);

  // Helper to find folder contents
  const getFolderContents = (folderPath: string): FileItem[] => {
    if (!folderPath || folderPath === '/' || folderPath === '') {
      return files;
    }
    const findInTree = (list: FileItem[]): FileItem | null => {
      for (const item of list) {
        if (item.type === 'folder') {
          if (item.path === folderPath) return item;
          if (item.children) {
            const found = findInTree(item.children);
            if (found) return found;
          }
        }
      }
      return null;
    };
    const folder = findInTree(files);
    return folder?.children || [];
  };

  // Helper to navigate back up to parent directory
  const handleNavigateUp = () => {
    const parts = activeFilePath.split('/').filter(Boolean);
    if (parts.length <= 1) return;
    parts.pop(); // remove current file
    const parentPath = '/' + parts.join('/');
    const siblingItems = getFolderContents(parentPath);
    const firstFile = siblingItems.find((item) => item.type === 'file');
    if (firstFile) {
      onSelectFile(firstFile.path);
    }
  };

  // Helper to copy relative path
  const handleCopyPath = () => {
    const relativePath = activeFilePath.startsWith('/') ? activeFilePath.slice(1) : activeFilePath;
    navigator.clipboard.writeText(relativePath);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const currentFileName = activeFilePath.split('/').pop() || '';
  const fileExt = currentFileName.split('.').pop()?.toUpperCase() || 'FILE';

  return (
    <div
      ref={containerRef}
      className="h-7.5 bg-slate-950 border-b border-slate-800/90 px-3 flex items-center justify-between text-[11px] font-mono text-slate-400 select-none z-20 shrink-0"
    >
      {/* Left: Breadcrumb Trail */}
      <div className="flex items-center gap-0.5 overflow-x-auto py-0.5 min-w-0">
        {/* Quick Navigate to Parent Directory button */}
        {segments.length > 2 && (
          <button
            type="button"
            onClick={handleNavigateUp}
            title="Navigate back to parent folder (ArrowUp)"
            className="p-1 rounded hover:bg-slate-800/80 text-slate-400 hover:text-cyan-400 mr-1 transition-colors flex items-center shrink-0"
          >
            <ArrowUp className="w-3 h-3" />
          </button>
        )}

        {segments.map((seg, idx) => {
          const isLast = idx === segments.length - 1;
          const isDropdownOpen = activeDropdownPath === seg.fullPath;
          const folderItems = seg.isFolder ? getFolderContents(seg.fullPath) : [];

          return (
            <div key={seg.fullPath} className="relative flex items-center shrink-0">
              {idx > 0 && (
                <ChevronRight className="w-3 h-3 text-slate-600 mx-0.5 shrink-0" />
              )}

              <button
                type="button"
                onClick={() => {
                  if (seg.isFolder) {
                    setActiveDropdownPath(isDropdownOpen ? null : seg.fullPath);
                  }
                }}
                className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors text-[11px] ${
                  isLast
                    ? 'text-cyan-300 font-semibold bg-slate-900/90 border border-slate-800'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 cursor-pointer'
                }`}
                title={seg.isFolder ? `Click to browse ${seg.name}` : seg.fullPath}
              >
                {seg.isFolder ? (
                  isDropdownOpen ? (
                    <FolderOpen className="w-3 h-3 text-blue-400 shrink-0" />
                  ) : (
                    <Folder className="w-3 h-3 text-blue-400 shrink-0" />
                  )
                ) : (
                  <FileCode2 className="w-3 h-3 text-cyan-400 shrink-0" />
                )}
                <span className="truncate max-w-[140px] sm:max-w-none">{seg.name}</span>
                {seg.isFolder && (
                  <ChevronDown className="w-2.5 h-2.5 text-slate-500 ml-0.5 shrink-0" />
                )}
              </button>

              {/* Folder Sibling Dropdown Menu */}
              {isDropdownOpen && seg.isFolder && (
                <div className="absolute left-0 top-full mt-1 w-60 max-h-60 overflow-y-auto rounded-xl bg-slate-900 border border-slate-700 shadow-2xl z-50 p-1.5 space-y-0.5 text-xs">
                  <div className="px-2 py-1 text-[10px] font-mono text-slate-400 border-b border-slate-800 flex items-center justify-between">
                    <span className="truncate font-semibold">{seg.name}</span>
                    <span>{folderItems.length} items</span>
                  </div>

                  {folderItems.length === 0 ? (
                    <div className="p-2 text-center text-xs text-slate-500">Empty directory</div>
                  ) : (
                    folderItems.map((item) => {
                      const isItemActive = item.path === activeFilePath;
                      return (
                        <button
                          key={item.path}
                          type="button"
                          onClick={() => {
                            if (item.type === 'file') {
                              onSelectFile(item.path);
                              setActiveDropdownPath(null);
                            } else {
                              setActiveDropdownPath(item.path);
                            }
                          }}
                          className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-left text-xs font-mono transition-colors ${
                            isItemActive
                              ? 'bg-blue-600/25 text-cyan-300 border border-blue-500/30'
                              : 'hover:bg-slate-800 text-slate-300'
                          }`}
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            {item.type === 'folder' ? (
                              <Folder className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                            ) : (
                              <FileCode2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                            )}
                            <span className="truncate">{item.name}</span>
                          </div>
                          {item.type === 'folder' && (
                            <ChevronRight className="w-3 h-3 text-slate-500 shrink-0" />
                          )}
                          {isItemActive && (
                            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" />
                          )}
                        </button>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Right: Quick actions & File metadata */}
      <div className="flex items-center gap-2 shrink-0 ml-2">
        <button
          type="button"
          onClick={handleCopyPath}
          title="Copy file path"
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors text-[10px]"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3 text-slate-400" />
              <span className="hidden sm:inline">Path</span>
            </>
          )}
        </button>

        <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] text-slate-400 hidden md:inline">
          {fileExt}
        </span>
      </div>
    </div>
  );
};
