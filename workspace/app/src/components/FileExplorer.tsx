import React, { useState, useEffect } from 'react';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
  expanded?: boolean;
}

interface FileExplorerProps {
  rootPath: string;
  onFileSelect?: (path: string) => void;
  onFileCreate?: (path: string) => void;
  onFileDelete?: (path: string) => void;
  onFileRename?: (oldPath: string, newPath: string) => void;
}

export const FileExplorer: React.FC<FileExplorerProps> = ({
  rootPath,
  onFileSelect,
  onFileCreate,
  onFileDelete,
  onFileRename
}) => {
  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: string } | null>(null);
  const [newFileName, setNewFileName] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    // Mock file system - in real implementation, this would call Agent Bridge API
    const mockFiles: FileNode[] = [
      {
        name: 'src',
        path: `${rootPath}/src`,
        type: 'directory',
        expanded: true,
        children: [
          {
            name: 'components',
            path: `${rootPath}/src/components`,
            type: 'directory',
            children: [
              { name: 'FileExplorer.tsx', path: `${rootPath}/src/components/FileExplorer.tsx`, type: 'file' },
              { name: 'CodeEditor.tsx', path: `${rootPath}/src/components/CodeEditor.tsx`, type: 'file' },
            ]
          },
          {
            name: 'App.tsx',
            path: `${rootPath}/src/App.tsx`,
            type: 'file'
          },
          {
            name: 'main.tsx',
            path: `${rootPath}/src/main.tsx`,
            type: 'file'
          }
        ]
      },
      {
        name: 'package.json',
        path: `${rootPath}/package.json`,
        type: 'file'
      },
      {
        name: 'README.md',
        path: `${rootPath}/README.md`,
        type: 'file'
      }
    ];
    setFiles(mockFiles);
  }, [rootPath]);

  const toggleDirectory = (path: string) => {
    const updateFiles = (nodes: FileNode[]): FileNode[] => {
      return nodes.map(node => {
        if (node.path === path) {
          return { ...node, expanded: !node.expanded };
        }
        if (node.children) {
          return { ...node, children: updateFiles(node.children) };
        }
        return node;
      });
    };
    setFiles(updateFiles(files));
  };

  const handleContextMenu = (e: React.MouseEvent, path: string) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, path });
  };

  const handleCreateFile = () => {
    if (newFileName && contextMenu) {
      const newPath = `${contextMenu.path}/${newFileName}`;
      onFileCreate?.(newPath);
      setNewFileName('');
      setIsCreating(false);
      setContextMenu(null);
    }
  };

  const renderFileNode = (node: FileNode, depth: number = 0) => {
    const isDirectory = node.type === 'directory';
    const isSelected = selectedFile === node.path;

    return (
      <div key={node.path}>
        <div
          className={`flex items-center py-1 px-2 hover:bg-gray-700 cursor-pointer ${isSelected ? 'bg-gray-600' : ''}`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => {
            if (isDirectory) {
              toggleDirectory(node.path);
            } else {
              setSelectedFile(node.path);
              onFileSelect?.(node.path);
            }
          }}
          onContextMenu={(e) => handleContextMenu(e, node.path)}
        >
          <span className="mr-2 text-gray-400">
            {isDirectory ? (node.expanded ? '▼' : '▶') : '📄'}
          </span>
          <span className="text-sm">{node.name}</span>
        </div>
        {isDirectory && node.expanded && node.children && (
          <div>
            {node.children.map(child => renderFileNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full bg-gray-800 text-white overflow-auto">
      <div className="p-2 border-b border-gray-700 flex justify-between items-center">
        <span className="font-semibold">Files</span>
        <button
          className="text-xs bg-blue-600 hover:bg-blue-700 px-2 py-1 rounded"
          onClick={() => {
            setContextMenu({ x: 0, y: 0, path: rootPath });
            setIsCreating(true);
          }}
        >
          + New
        </button>
      </div>
      <div className="overflow-auto">
        {files.map(file => renderFileNode(file))}
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <div
          className="fixed bg-gray-700 border border-gray-600 rounded shadow-lg z-50"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {isCreating ? (
            <div className="p-2">
              <input
                type="text"
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                placeholder="filename.ext"
                className="w-full bg-gray-600 text-white px-2 py-1 rounded text-sm mb-2"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateFile();
                  if (e.key === 'Escape') setIsCreating(false);
                }}
              />
              <div className="flex gap-2">
                <button
                  className="flex-1 bg-blue-600 hover:bg-blue-700 px-2 py-1 rounded text-sm"
                  onClick={handleCreateFile}
                >
                  Create
                </button>
                <button
                  className="flex-1 bg-gray-600 hover:bg-gray-500 px-2 py-1 rounded text-sm"
                  onClick={() => setIsCreating(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="py-1">
              <button
                className="w-full text-left px-4 py-2 hover:bg-gray-600 text-sm"
                onClick={() => {
                  setIsCreating(true);
                  setContextMenu({ ...contextMenu, path: contextMenu.path });
                }}
              >
                New File
              </button>
              <button
                className="w-full text-left px-4 py-2 hover:bg-gray-600 text-sm"
                onClick={() => {
                  setIsCreating(true);
                  setContextMenu({ ...contextMenu, path: contextMenu.path });
                }}
              >
                New Folder
              </button>
              <hr className="border-gray-600 my-1" />
              <button
                className="w-full text-left px-4 py-2 hover:bg-gray-600 text-sm"
                onClick={() => {
                  onFileRename?.(contextMenu.path, prompt('New name:', contextMenu.path.split('/').pop() || '') || contextMenu.path);
                  setContextMenu(null);
                }}
              >
                Rename
              </button>
              <button
                className="w-full text-left px-4 py-2 hover:bg-gray-600 text-sm text-red-400"
                onClick={() => {
                  if (confirm('Delete this file?')) {
                    onFileDelete?.(contextMenu.path);
                  }
                  setContextMenu(null);
                }}
              >
                Delete
              </button>
            </div>
          )}
        </div>
      )}

      {/* Click outside to close context menu */}
      {contextMenu && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setContextMenu(null)}
        />
      )}
    </div>
  );
};

export default FileExplorer;