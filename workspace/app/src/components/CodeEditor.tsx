import React, { useState, useEffect, useRef } from 'react';

interface CodeEditorProps {
  filePath: string;
  content: string;
  onChange?: (content: string) => void;
  onSave?: (content: string) => void;
  language?: string;
}

export const CodeEditor: React.FC<CodeEditorProps> = ({
  filePath,
  content,
  onChange,
  onSave,
  language = 'typescript'
}) => {
  const [code, setCode] = useState(content);
  const [isModified, setIsModified] = useState(false);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setCode(content);
    setIsModified(false);
  }, [content]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newCode = e.target.value;
    setCode(newCode);
    setIsModified(newCode !== content);
    onChange?.(newCode);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Save: Ctrl+S / Cmd+S
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      onSave?.(code);
      setIsModified(false);
    }

    // Tab indentation
    if (e.key === 'Tab') {
      e.preventDefault();
      const textarea = textareaRef.current;
      if (textarea) {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const newCode = code.substring(0, start) + '  ' + code.substring(end);
        setCode(newCode);
        setIsModified(true);
        onChange?.(newCode);

        // Restore cursor position
        setTimeout(() => {
          textarea.selectionStart = textarea.selectionEnd = start + 2;
        }, 0);
      }
    }
  };

  const handleKeyUp = (e: React.KeyboardEvent) => {
    // Update cursor position
    const textarea = textareaRef.current;
    if (textarea) {
      const text = textarea.value.substring(0, textarea.selectionStart);
      const lines = text.split('\n');
      setCursorPosition({
        line: lines.length,
        column: lines[lines.length - 1].length + 1
      });
    }
  };

  const getLanguageFromPath = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'ts':
      case 'tsx':
        return 'typescript';
      case 'js':
      case 'jsx':
        return 'javascript';
      case 'py':
        return 'python';
      case 'json':
        return 'json';
      case 'md':
        return 'markdown';
      case 'css':
        return 'css';
      case 'html':
        return 'html';
      default:
        return 'text';
    }
  };

  const detectedLanguage = getLanguageFromPath(filePath);

  return (
    <div className="h-full flex flex-col bg-gray-900 text-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono">{filePath.split('/').pop()}</span>
          {isModified && (
            <span className="text-yellow-400 text-xs">●</span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span>{detectedLanguage}</span>
          <span>Ln {cursorPosition.line}, Col {cursorPosition.column}</span>
          <button
            className="text-blue-400 hover:text-blue-300"
            onClick={() => onSave?.(code)}
            disabled={!isModified}
          >
            Save (Ctrl+S)
          </button>
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-auto">
        <div className="flex">
          {/* Line numbers */}
          <div className="text-gray-500 text-right pr-4 pl-2 py-2 select-none font-mono text-sm">
            {code.split('\n').map((_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>

          {/* Code area */}
          <textarea
            ref={textareaRef}
            value={code}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onKeyUp={handleKeyUp}
            className="flex-1 bg-transparent text-white font-mono text-sm p-2 resize-none outline-none"
            style={{ minHeight: 'calc(100vh - 200px)' }}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
          />
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-1 bg-gray-800 border-t border-gray-700 text-xs text-gray-400">
        <div className="flex items-center gap-4">
          <span>{detectedLanguage}</span>
          <span>UTF-8</span>
          <span>LF</span>
        </div>
        <div className="flex items-center gap-4">
          <span>Spaces: 2</span>
          <span>{isModified ? 'Modified' : 'Saved'}</span>
        </div>
      </div>
    </div>
  );
};

export default CodeEditor;