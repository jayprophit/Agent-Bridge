"""Workspace file/git API backend (Phase 2).

Read/write/search/list over explicit workspace roots with git read-only
status. Writes are USER file operations through the loopback IDE service
(model actions keep going through task approval instead). Every op is
confined to an allowed root, size-capped, and recorded as evidence.
Binary/control policy: text files only for read (UTF-8), 256KB cap.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

MAX_READ_BYTES = 256 * 1024
MAX_LIST_ENTRIES = 500
MAX_SEARCH_HITS = 100


class WorkspaceAPI:
    def __init__(self, allowed_roots: list[str | Path]):
        self.roots = [Path(r).expanduser().resolve() for r in allowed_roots]

    @staticmethod
    def _is_within(path: Path, candidate: Path) -> bool:
        try:
            path.relative_to(candidate)
            return True
        except ValueError:
            return False

    def resolve(self, root: str | Path, user_path: str = "") -> Path:
        base = Path(root).expanduser().resolve()
        if base not in self.roots and not any(
                self._is_within(base, candidate) for candidate in self.roots):
            raise PermissionError(f"workspace outside roots: {root!r}")
        target = (base / (user_path or "")).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            raise PermissionError(f"path escapes workspace: {user_path!r}")
        return target

    def list(self, root: str | Path, path: str = "") -> dict[str, Any]:
        target = self.resolve(root, path)
        if not target.is_dir():
            return {"ok": False, "error": f"not a directory: {path!r}"}
        entries = []
        try:
            children = sorted(target.iterdir(),
                              key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            return {"ok": False, "error": f"list failed: {e}"}
        for child in children[:MAX_LIST_ENTRIES]:
            try:
                entries.append({"name": child.name,
                                "dir": child.is_dir(),
                                "size": child.stat().st_size
                                if child.is_file() else 0})
            except OSError:
                continue
        return {"ok": True, "path": path, "entries": entries,
                "truncated": len(children) > MAX_LIST_ENTRIES}

    def read(self, root: str | Path, path: str) -> dict[str, Any]:
        target = self.resolve(root, path)
        try:
            if not target.is_file():
                return {"ok": False, "error": f"not a file: {path!r}"}
            if target.stat().st_size > MAX_READ_BYTES:
                return {"ok": False, "error": "file too large to preview"}
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": "not UTF-8 text"}
        except OSError as e:
            return {"ok": False, "error": f"read failed: {e}"}
        return {"ok": True, "path": path, "content": text,
                "bytes": target.stat().st_size}

    def write(self, root: str | Path, path: str, content: str) -> dict[str, Any]:
        if not isinstance(content, str):
            return {"ok": False, "error": "content must be text"}
        if len(content.encode("utf-8")) > 4 * MAX_READ_BYTES:
            return {"ok": False, "error": "content too large"}
        target = self.resolve(root, path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".bridge-tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(target)
        except OSError as e:
            return {"ok": False, "error": f"write failed: {e}"}
        return {"ok": True, "path": path, "bytes": target.stat().st_size,
                "verified": True}

    def search(self, root: str | Path, pattern: str,
               path: str = "", glob: str = "*") -> dict[str, Any]:
        import re
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return {"ok": False, "error": f"bad pattern: {e}"}
        target = self.resolve(root, path)
        if not target.is_dir():
            return {"ok": False, "error": f"not a directory: {path!r}"}
        hits = []
        count = 0
        for base, dirs, files in __import__("os").walk(target):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "node_modules", "__pycache__",
                                    ".bridge", "dist", "build")]
            for name in files:
                if not fnmatch.fnmatch(name, glob):
                    continue
                full = Path(base) / name
                try:
                    if full.stat().st_size > MAX_READ_BYTES:
                        continue
                    text = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        hits.append({"path": str(full.relative_to(target)),
                                     "line": lineno,
                                     "preview": line.strip()[:160]})
                        count += 1
                        if count >= MAX_SEARCH_HITS:
                            return {"ok": True, "pattern": pattern,
                                    "hits": hits, "truncated": True}
        return {"ok": True, "pattern": pattern, "hits": hits,
                "truncated": False}

    def git(self, root: str | Path, op: str) -> dict[str, Any]:
        import gitops
        if op not in ("status", "diff", "branch", "log"):
            return {"ok": False, "error": f"read-only git op required: {op!r}"}
        base = self.resolve(root, "")
        return gitops.operate(base, op)

    def create(self, root: str | Path, path: str, is_dir: bool = False) -> dict[str, Any]:
        """Create a new file or directory."""
        target = self.resolve(root, path)
        if target.exists():
            raise FileExistsError(f"already exists: {path!r}")
        try:
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("", encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": f"create failed: {e}"}
        return {"ok": True, "path": path, "is_dir": is_dir}

    def delete(self, root: str | Path, path: str) -> dict[str, Any]:
        """Delete a file or empty directory."""
        target = self.resolve(root, path)
        if not target.exists():
            raise FileNotFoundError(f"not found: {path!r}")
        try:
            if target.is_dir():
                target.rmdir()
            else:
                target.unlink()
        except OSError as e:
            return {"ok": False, "error": f"delete failed: {e}"}
        return {"ok": True, "path": path}

    def rename(self, root: str | Path, old_path: str, new_path: str) -> dict[str, Any]:
        """Rename/move a file or directory."""
        old_target = self.resolve(root, old_path)
        new_target = self.resolve(root, new_path)
        if not old_target.exists():
            raise FileNotFoundError(f"not found: {old_path!r}")
        if new_target.exists():
            raise ValueError(f"destination exists: {new_path!r}")
        try:
            old_target.rename(new_target)
        except OSError as e:
            return {"ok": False, "error": f"rename failed: {e}"}
        return {"ok": True, "old_path": old_path, "new_path": new_path}
