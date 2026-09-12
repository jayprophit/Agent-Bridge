"""ArtifactRegistry (v0.7). Stable references for generated/downloaded
artifacts with hash/size verification. References obey runtime
permissions (checked by callers at creation)."""
from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any


class ArtifactRegistry:
    def __init__(self):
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._n = 0

    def register(self, kind: str, path_or_ref: str, creator_tool: str = "",
                 provenance: str = "", verify: bool = True) -> dict[str, Any]:
        with self._lock:
            self._n += 1
            aid = f"art-{self._n:05d}"
            entry: dict[str, Any] = {"artifact_id": aid, "type": kind,
                                     "path": str(path_or_ref),
                                     "creator_tool": creator_tool,
                                     "timestamp": time.time(),
                                     "provenance": provenance[:500]}
            if verify and kind in ("file", "screenshot", "download", "log",
                                   "document", "image", "audio", "video",
                                   "archive", "dataset", "report", "code"):
                try:
                    p = Path(str(path_or_ref))
                    if p.exists() and p.is_file():
                        h = hashlib.sha256()
                        with open(p, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""):
                                h.update(chunk)
                        entry.update({"hash": h.hexdigest()[:16],
                                      "size": p.stat().st_size,
                                      "verification": "exists+hashed"})
                    else:
                        entry.update({"verification": "MISSING"})
                except OSError as e:
                    entry.update({"verification": f"error: {e}"})
            else:
                entry.update({"verification": "reference-only"})
            self._items[aid] = entry
            return dict(entry)

    def get(self, artifact_id: str) -> dict[str, Any]:
        try:
            return dict(self._items[artifact_id])
        except KeyError:
            raise KeyError(f"unknown artifact: {artifact_id!r}")

    def list(self, kind: str = "") -> list[dict[str, Any]]:
        return [dict(v) for v in self._items.values()
                if not kind or v["type"] == kind]
