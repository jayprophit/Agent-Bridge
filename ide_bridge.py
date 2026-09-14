"""IDE runtime bridge (Phase 2): live runtime state for IDE surfaces.

Aggregates task state, queue, models, workers, approvals, progress,
results, evidence refs, resource use, health and errors into one
snapshot the IDE polls. Backed by explicit record_* calls plus an
optional JSON snapshot file (persistence + recovery). No mocks: every
field defaults to unknown/empty until real data is recorded.

Also feeds GET /v1/runtime on the Agent Bridge service.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TaskEntry:
    task_id: str = ""
    session_id: str = ""
    objective: str = ""
    status: str = "UNKNOWN"
    progress_pct: float = 0.0
    worker: str = ""
    model: str = ""
    updated_at: float = 0.0


@dataclass
class RuntimeSnapshot:
    timestamp: float = field(default_factory=time.time)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    queue_depth: int = 0
    queued_ids: list[str] = field(default_factory=list)
    active_model: str = ""
    models: list[dict[str, Any]] = field(default_factory=list)
    workers: list[dict[str, Any]] = field(default_factory=list)
    approvals_pending: list[dict[str, Any]] = field(default_factory=list)
    progress_pct: float = 0.0
    results: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)
    health: str = "UNKNOWN"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeStateTracker:
    """In-memory tracker with optional JSON snapshot persistence."""

    def __init__(self, snapshot_path: str | Path | None = None):
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None
        self.tasks: dict[str, TaskEntry] = {}
        self.queued_ids: list[str] = []
        self.models: list[dict[str, Any]] = []
        self.active_model: str = ""
        self.workers: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        self.evidence_refs: list[str] = []
        self.resources: dict[str, Any] = {}
        self.health: str = "UNKNOWN"
        self.errors: list[str] = []

    # -- record ---------------------------------------------------------
    def record_task(self, entry: TaskEntry) -> None:
        entry.updated_at = time.time()
        self.tasks[entry.task_id] = entry

    def record_queue(self, queued_ids: list[str]) -> None:
        self.queued_ids = list(queued_ids)

    def record_models(self, models: list[dict[str, Any]],
                      active: str = "") -> None:
        self.models = list(models)
        if active:
            self.active_model = active

    def record_workers(self, workers: list[dict[str, Any]]) -> None:
        self.workers = list(workers)

    def record_approval(self, approval: dict[str, Any]) -> None:
        self.approvals.append(dict(approval))

    def record_result(self, result: dict[str, Any]) -> None:
        self.results.append(dict(result))

    def record_evidence(self, ref: str) -> None:
        if ref not in self.evidence_refs:
            self.evidence_refs.append(ref)

    def record_resources(self, resources: dict[str, Any]) -> None:
        self.resources = dict(resources)

    def set_health(self, health: str) -> None:
        self.health = health

    def record_error(self, error: str) -> None:
        self.errors.append(str(error)[:300])

    # -- snapshot --------------------------------------------------------
    def snapshot(self) -> RuntimeSnapshot:
        tasks = [asdict(t) for t in self.tasks.values()]
        done = sum(1 for t in self.tasks.values()
                   if t.status in ("VERIFIED_COMPLETE", "COMPLETED"))
        progress = round(100.0 * done / len(tasks), 1) if tasks else 0.0
        return RuntimeSnapshot(
            tasks=tasks, queue_depth=len(self.queued_ids),
            queued_ids=list(self.queued_ids), active_model=self.active_model,
            models=list(self.models), workers=list(self.workers),
            approvals_pending=list(self.approvals), progress_pct=progress,
            results=list(self.results), evidence_refs=list(self.evidence_refs),
            resources=dict(self.resources), health=self.health,
            errors=list(self.errors))

    def save(self) -> str:
        if self.snapshot_path is None:
            return ""
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(
            json.dumps(self.snapshot().to_dict(), indent=1), encoding="utf-8")
        return str(self.snapshot_path)

    def load(self) -> bool:
        if self.snapshot_path is None or not self.snapshot_path.exists():
            return False
        try:
            data = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        self.queued_ids = list(data.get("queued_ids", []))
        self.models = list(data.get("models", []))
        self.active_model = str(data.get("active_model", ""))
        self.workers = list(data.get("workers", []))
        self.approvals = list(data.get("approvals_pending", []))
        self.results = list(data.get("results", []))
        self.evidence_refs = list(data.get("evidence_refs", []))
        self.resources = dict(data.get("resources", {}))
        self.health = str(data.get("health", "UNKNOWN"))
        self.errors = list(data.get("errors", []))
        self.tasks = {}
        for td in data.get("tasks", []):
            try:
                self.tasks[td["task_id"]] = TaskEntry(**td)
            except (KeyError, TypeError):
                continue
        return True


def build_runtime_snapshot(runtime: Any,
                           tracker: RuntimeStateTracker | None = None
                           ) -> dict[str, Any]:
    """Aggregate live runtime sessions (+ optional tracker) for /v1/runtime."""
    snap = (tracker.snapshot().to_dict() if tracker is not None
            else RuntimeSnapshot().to_dict())
    try:
        sessions = runtime.list_sessions()
    except Exception:
        sessions = []
    tasks: list[dict[str, Any]] = list(snap.get("tasks", []))
    approvals: list[dict[str, Any]] = list(snap.get("approvals_pending", []))
    seen = {t.get("task_id") for t in tasks}
    for s in sessions if isinstance(sessions, list) else []:
        sid = s.get("session_id", "") if isinstance(s, dict) else ""
        try:
            detail = runtime.get_session(sid)
            items = detail.tasks.items() if hasattr(detail, "tasks") else []
        except Exception:
            continue
        for tid, res in items:
            if tid in seen:
                continue
            seen.add(tid)
            status = getattr(res, "status",
                             res.get("status") if isinstance(res, dict) else "")
            tasks.append({"task_id": tid, "session_id": sid,
                          "objective": "", "status": str(status),
                          "progress_pct": 0.0, "worker": "", "model": "",
                          "updated_at": time.time()})
    snap["tasks"] = tasks
    snap["approvals_pending"] = approvals
    snap["timestamp"] = time.time()
    try:
        health = runtime.health()
        snap["health"] = health.get("status", snap.get("health", "UNKNOWN")) \
            if isinstance(health, dict) else str(health)
    except Exception:
        pass
    return snap
