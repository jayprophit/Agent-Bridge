"""Local session memory + deterministic compaction (v0.3, JSON only)."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


class SessionMemory:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else None
        self.data: dict[str, Any] = {
            "task": "", "model": "", "decisions": [],
            "completed": [], "failed": [], "results": [],
            "files_touched": [], "tests_run": [],
            "review_findings": [], "constraints": [],
        }
        if self.path and self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (OSError, ValueError):
                pass

    def set_task(self, task: str, model: str) -> None:
        self.data["task"] = task
        self.data["model"] = model
        self.save()

    def record(self, kind: str, entry: Any) -> None:
        if kind in self.data and isinstance(self.data[kind], list):
            self.data[kind].append(entry)
        else:
            self.data.setdefault("extra", []).append({kind: entry})
        if isinstance(entry, dict):
            for f in (entry.get("files_touched") or []):
                if f not in self.data["files_touched"]:
                    self.data["files_touched"].append(f)
        self.save()

    def save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2)[:300_000],
                                 encoding="utf-8")
        except OSError:
            pass

    def summary(self) -> dict[str, Any]:
        return {"completed": len(self.data.get("completed", [])),
                "failed": len(self.data.get("failed", [])),
                "files_touched": list(self.data.get("files_touched", []))[:50],
                "tests_run": len(self.data.get("tests_run", [])),
                "reviews": len(self.data.get("review_findings", []))}

    # -- compaction: keep critical state, drop noise -------------------------
    def compact(self) -> dict[str, Any]:
        """Deterministic compaction. Raw logs stay on disk; the summary never
        replaces execution truth (it only trims duplicated/verbose text)."""
        before = len(json.dumps(self.data))
        # dedupe repeated failures by (kind, error, action) — step and
        # timestamps differ every time and must not defeat the dedupe.
        failed = self.data.get("failed", [])
        deduped: list[Any] = []
        last_key, run = None, 0
        for f in failed:
            if isinstance(f, dict):
                key = json.dumps({k: str(f.get(k, ""))[:200]
                                  for k in ("kind", "error", "action")},
                                 sort_keys=True)
            else:
                key = str(f)[:300]
            if key == last_key:
                run += 1
                continue
            if run > 1:
                deduped.append({"repeated_previous_failure": f"x{run}"})
            deduped.append(f)
            last_key, run = key, 1
        if run > 1:
            deduped.append({"repeated_previous_failure": f"x{run}"})
        self.data["failed"] = deduped[:40]
        # trim verbose completed entries (keep action + result status only)
        slim_completed = []
        for c in self.data.get("completed", [])[-60:]:
            if isinstance(c, dict):
                slim_completed.append({
                    "step": c.get("step"), "action": c.get("action"),
                    "files_touched": (c.get("files_touched") or [])[:10]})
            else:
                slim_completed.append(str(c)[:300])
        self.data["completed"] = slim_completed
        for k in ("results", "extra"):
            if isinstance(self.data.get(k), list):
                self.data[k] = self.data[k][-20:]
        for k in ("decisions", "review_findings", "constraints"):
            trimmed = []
            for e in self.data.get(k, [])[-30:]:
                trimmed.append(e if not isinstance(e, str) else e[:800])
            self.data[k] = trimmed
        self.save()
        after = len(json.dumps(self.data))
        return {"before_chars": before, "after_chars": after,
                "kept": self.summary()}
