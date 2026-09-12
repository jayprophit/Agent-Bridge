"""Tool call metrics (v0.7). Local only. No telemetry."""
from __future__ import annotations

import threading
from typing import Any


class ToolMetrics:
    def __init__(self):
        self._m: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def note(self, tool_id: str, ok: bool, duration_s: float,
             validation_failure: bool = False, fallback: bool = False,
             timeout: bool = False, cancelled: bool = False,
             backend_failure: bool = False) -> None:
        with self._lock:
            m = self._m.setdefault(tool_id, {"calls": 0, "success": 0,
                                             "failure": 0, "total_s": 0.0,
                                             "timeouts": 0, "cancellations": 0,
                                             "validation_failures": 0,
                                             "backend_failures": 0,
                                             "fallbacks": 0})
            m["calls"] += 1
            m["success" if ok else "failure"] += 1
            m["total_s"] += max(0.0, duration_s)
            m["timeouts"] += int(timeout)
            m["cancellations"] += int(cancelled)
            m["validation_failures"] += int(validation_failure)
            m["backend_failures"] += int(backend_failure)
            m["fallbacks"] += int(fallback)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            out = {}
            for tool_id, m in self._m.items():
                d = dict(m)
                d["average_duration_s"] = round(
                    d["total_s"] / d["calls"], 3) if d["calls"] else 0.0
                out[tool_id] = d
            return out
