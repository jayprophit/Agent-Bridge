"""Capability Cache (v0.9.0 Phase 1).

Controlled cache for machine scans: scan timestamp, tool versions,
invalidation, manual rescan. No daemon watcher in Phase 1.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class CacheEntry:
    key: str = ""
    timestamp: float = field(default_factory=time.time)
    tool_versions: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)


class CapabilityCache:
    """Simple TTL cache with explicit invalidation and manual rescan."""

    def __init__(self, ttl_seconds: float = 3600.0):
        self._ttl = ttl_seconds
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        e = self._entries.get(key)
        if e is None:
            return None
        if (time.time() - e.timestamp) > self._ttl:
            return None
        return e

    def put(self, key: str, payload: dict[str, Any],
            tool_versions: dict[str, str] | None = None) -> CacheEntry:
        e = CacheEntry(key=key, payload=payload,
                       tool_versions=tool_versions or {})
        self._entries[key] = e
        return e

    def invalidate(self, key: str | None = None) -> int:
        """Invalidate one key or everything. Returns count removed."""
        if key is None:
            n = len(self._entries)
            self._entries.clear()
            return n
        return 1 if self._entries.pop(key, None) is not None else 0

    def rescan(self, key: str, fn: Callable[[], tuple[dict[str, Any], dict[str, str]]]) -> CacheEntry:
        """Manual rescan: fn() returns (payload, tool_versions)."""
        payload, versions = fn()
        return self.put(key, payload, versions)

    def status(self) -> dict[str, Any]:
        now = time.time()
        return {
            "ttl_seconds": self._ttl,
            "entries": {
                k: {"age_s": round(now - v.timestamp, 1),
                    "expired": (now - v.timestamp) > self._ttl,
                    "tools": len(v.tool_versions)}
                for k, v in self._entries.items()
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {"ttl_seconds": self._ttl,
                "entries": {k: asdict(v) for k, v in self._entries.items()}}
