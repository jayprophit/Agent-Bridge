"""Lightweight local cache (v0.3, same contract as v0.2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class BridgeCache:
    def __init__(self, workspace: Path | str | None = None,
                 enabled: bool = True, max_entries: int = 256):
        self.workspace = Path(workspace).resolve() if workspace else None
        self.enabled = enabled
        self.max_entries = max_entries
        self._reads: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    def bind(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()

    def get_read(self, rel: str) -> dict | None:
        if not self.enabled or self.workspace is None:
            self.misses += 1
            return None
        e = self._reads.get(rel)
        if not e:
            self.misses += 1
            return None
        try:
            st = (self.workspace / rel).resolve().stat()
        except OSError:
            self.invalidate(rel)
            self.misses += 1
            return None
        if e.get("mtime") == st.st_mtime and e.get("size") == st.st_size:
            self.hits += 1
            return dict(e["result"])
        self.invalidate(rel)
        self.misses += 1
        return None

    def put_read(self, rel: str, target: Path, result: dict) -> None:
        if not self.enabled:
            return
        try:
            st = target.stat()
        except OSError:
            return
        if len(self._reads) >= self.max_entries:
            self._reads.pop(next(iter(self._reads)))
        self._reads[rel] = {"mtime": st.st_mtime, "size": st.st_size,
                            "result": dict(result)}

    def invalidate(self, rel: str) -> None:
        self._reads.pop(rel, None)

    def clear(self) -> None:
        self._reads.clear()

    def stats(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "entries": len(self._reads),
                "hits": self.hits, "misses": self.misses}
