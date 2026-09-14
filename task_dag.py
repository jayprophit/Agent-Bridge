"""Durable task graph + orchestration (v0.9.0 continuous build).

Execution backbone: tasks survive interruption; restart resumes from the
last verified checkpoint, never from scratch.

Concepts: DurableTaskGraph, WorkQueue, WorkerRegistry, WorkerLifecycle,
CheckpointManager, RecoveryManager, RetryPolicy, TaskBudget,
EvidenceLedger, structured worker handoff (request + return contracts).

Evidence-first: FACT/OBSERVATION/SOURCE/PROPOSAL/ARTIFACT/TEST_RESULT/
FAILED_ATTEMPT/WARNING/DECISION/VERIFIED_RESULT. Confidence is NOT
verification. Additive only; no import side effects; no I/O except
explicit checkpoint persistence to a caller-chosen path.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class TaskStatus(str, Enum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    VERIFIED_COMPLETE = "VERIFIED_COMPLETE"
    CANCELLED = "CANCELLED"


class EvidenceKind(str, Enum):
    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    SOURCE = "SOURCE"
    PROPOSAL = "PROPOSAL"
    ARTIFACT = "ARTIFACT"
    TEST_RESULT = "TEST_RESULT"
    FAILED_ATTEMPT = "FAILED_ATTEMPT"
    WARNING = "WARNING"
    DECISION = "DECISION"
    VERIFIED_RESULT = "VERIFIED_RESULT"


@dataclass
class TaskBudget:
    time_s: float = 0.0       # 0 = unbounded
    tool_calls: int = 0       # 0 = unbounded
    retries: int = 2
    cost_units: float = 0.0


@dataclass
class TaskRecord:
    task_id: str = field(default_factory=lambda: "t-" + uuid.uuid4().hex[:8])
    parent_task: str = ""
    objective: str = ""
    requirements: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    assigned_worker: str = ""
    execution_environment: str = ""
    status: TaskStatus = TaskStatus.PLANNED
    checkpoint: str = ""
    attempt: int = 0
    budget: TaskBudget = field(default_factory=TaskBudget)
    started_at: float = 0.0
    updated_at: float = 0.0
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)  # evidence ids
    failures: list[str] = field(default_factory=list)
    next_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Evidence:
    evidence_id: str = field(default_factory=lambda: "e-" + uuid.uuid4().hex[:8])
    kind: EvidenceKind = EvidenceKind.OBSERVATION
    producer: str = ""
    task_id: str = ""
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    confidence: float = 0.0  # informational only; never implies verification

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


class EvidenceLedger:
    """Typed shared blackboard. Confidence never equals verification."""

    def __init__(self):
        self._items: dict[str, Evidence] = {}

    def add(self, item: Evidence) -> str:
        self._items[item.evidence_id] = item
        return item.evidence_id

    def get(self, evidence_id: str) -> Evidence | None:
        return self._items.get(evidence_id)

    def verified_results(self, task_id: str = "") -> list[Evidence]:
        return [e for e in self._items.values()
                if e.verified and e.kind == EvidenceKind.VERIFIED_RESULT
                and (not task_id or e.task_id == task_id)]

    def mark_verified(self, evidence_id: str) -> bool:
        item = self._items.get(evidence_id)
        if item is None:
            return False
        item.verified = True
        return True


@dataclass
class RetryPolicy:
    max_retries: int = 2
    backoff_s: float = 5.0
    retry_on: tuple[str, ...] = ("TRANSIENT", "TIMEOUT")

    def should_retry(self, attempt: int, failure_kind: str) -> bool:
        return attempt <= self.max_retries and failure_kind in self.retry_on

    def delay_for(self, attempt: int) -> float:
        return self.backoff_s * (2 ** max(0, attempt - 1))


class DurableTaskGraph:
    """Dependency-ordered tasks with checkpoint resume."""

    def __init__(self):
        self.tasks: dict[str, TaskRecord] = {}

    def add(self, task: TaskRecord) -> str:
        self.tasks[task.task_id] = task
        return task.task_id

    def get(self, task_id: str) -> TaskRecord | None:
        return self.tasks.get(task_id)

    def ready(self) -> list[TaskRecord]:
        """Tasks whose dependencies are VERIFIED_COMPLETE and which are queued."""
        out = []
        for t in self.tasks.values():
            if t.status not in (TaskStatus.QUEUED, TaskStatus.PLANNED):
                continue
            deps_ok = all(
                (d in self.tasks and
                 self.tasks[d].status == TaskStatus.VERIFIED_COMPLETE)
                for d in t.dependencies)
            if deps_ok:
                out.append(t)
        return sorted(out, key=lambda t: t.task_id)

    def ordered(self) -> list[TaskRecord]:
        order: list[TaskRecord] = []
        visited: dict[str, int] = {}

        def visit(tid: str) -> None:
            mark = visited.get(tid, 0)
            if mark == 2:
                return
            if mark == 1:
                raise ValueError(f"task cycle at {tid!r}")
            visited[tid] = 1
            task = self.tasks.get(tid)
            if task is not None:
                for dep in sorted(task.dependencies):
                    if dep in self.tasks:
                        visit(dep)
                order.append(task)
            visited[tid] = 2

        for tid in sorted(self.tasks):
            visit(tid)
        return order

    def resume_state(self) -> dict[str, Any]:
        """What a restart continues from: last verified checkpoints."""
        return {t.task_id: {"status": t.status.value, "checkpoint": t.checkpoint,
                            "attempt": t.attempt, "next_action": t.next_action}
                for t in self.tasks.values()
                if t.status not in (TaskStatus.PLANNED,)}


class CheckpointManager:
    """Persist/restore graph snapshots to an explicit path (caller-owned)."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None

    def save(self, graph: DurableTaskGraph,
             ledger: EvidenceLedger | None = None) -> dict[str, Any]:
        snapshot = {"tasks": [t.to_dict() for t in graph.tasks.values()],
                    "evidence": [e.to_dict() for e in
                                 (ledger._items.values() if ledger else [])]}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(snapshot, indent=1),
                                 encoding="utf-8")
        return {"ok": True, "tasks": len(snapshot["tasks"]),
                "path": str(self.path) if self.path else ""}

    def load(self) -> tuple[DurableTaskGraph, EvidenceLedger]:
        graph, ledger = DurableTaskGraph(), EvidenceLedger()
        if self.path is None or not self.path.exists():
            return graph, ledger
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for td in data.get("tasks", []):
            td["status"] = TaskStatus(td.get("status", "PLANNED"))
            td["budget"] = TaskBudget(**td.get("budget", {}))
            graph.tasks[td["task_id"]] = TaskRecord(**td)
        for ed in data.get("evidence", []):
            ed["kind"] = EvidenceKind(ed.get("kind", "OBSERVATION"))
            ledger._items[ed["evidence_id"]] = Evidence(**ed)
        return graph, ledger


class RecoveryManager:
    """Resume-from-checkpoint after interruption; never restart blindly."""

    @staticmethod
    def plan_recovery(graph: DurableTaskGraph) -> list[dict[str, Any]]:
        plan = []
        for t in graph.ordered():
            if t.status in (TaskStatus.VERIFIED_COMPLETE, TaskStatus.CANCELLED):
                continue
            if t.status in (TaskStatus.RUNNING, TaskStatus.RETRYING,
                            TaskStatus.VERIFYING, TaskStatus.WAITING):
                action = f"resume from checkpoint {t.checkpoint!r}" \
                    if t.checkpoint else "re-queue (no checkpoint)"
                plan.append({"task_id": t.task_id, "was": t.status.value,
                             "action": action})
            elif t.status in (TaskStatus.FAILED, TaskStatus.BLOCKED,
                              TaskStatus.PLANNED, TaskStatus.QUEUED):
                plan.append({"task_id": t.task_id, "was": t.status.value,
                             "action": "evaluate then queue"})
        return plan


@dataclass
class WorkerInfo:
    worker_id: str = ""
    kind: str = ""          # native | third-party | remote | specialist
    capabilities: list[str] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    state: str = "IDLE"     # IDLE | BUSY | DRAINING | OFFLINE
    current_task: str = ""


class WorkerRegistry:
    def __init__(self):
        self.workers: dict[str, WorkerInfo] = {}

    def register(self, worker: WorkerInfo) -> None:
        self.workers[worker.worker_id] = worker

    def available(self, capability: str = "") -> list[WorkerInfo]:
        return sorted(
            (w for w in self.workers.values()
             if w.state == "IDLE" and (not capability or capability in w.capabilities)),
            key=lambda w: w.worker_id)


class WorkQueue:
    """FIFO with priority + lease semantics (claim disjoint work)."""

    def __init__(self):
        self._queued: list[str] = []
        self._leased: dict[str, float] = {}

    def push(self, task_id: str) -> None:
        if task_id not in self._queued:
            self._queued.append(task_id)

    def claim(self, lease_s: float = 300.0) -> str | None:
        now = time.time()
        expired = [tid for tid, until in self._leased.items() if until < now]
        for tid in expired:
            del self._leased[tid]
            if tid not in self._queued:
                self._queued.insert(0, tid)
        if not self._queued:
            return None
        tid = self._queued.pop(0)
        self._leased[tid] = now + lease_s
        return tid

    def release(self, task_id: str, requeue: bool = True) -> None:
        self._leased.pop(task_id, None)
        if requeue and task_id not in self._queued:
            self._queued.append(task_id)

    def depth(self) -> int:
        return len(self._queued)


class QueueDecisionEngine:
    """Immediate vs queued: decides from task traits, never queues trivia."""

    def decide(self, task: TaskRecord) -> str:
        if task.status in (TaskStatus.BLOCKED,):
            return "QUEUE_AFTER_DEPENDENCY"
        if task.dependencies:
            return "QUEUE_AFTER_DEPENDENCY"
        budget = task.budget
        if budget.time_s and budget.time_s > 300:
            return "QUEUE_BACKGROUND"
        if "long-running" in task.requirements or "batch" in task.requirements:
            return "QUEUE_BACKGROUND"
        return "EXECUTE_NOW"


def make_handoff(task: TaskRecord) -> dict[str, Any]:
    """Structured worker request contract."""
    return {"task_id": task.task_id, "parent_task": task.parent_task,
            "objective": task.objective, "requirements": task.requirements,
            "constraints": {}, "inputs": task.inputs,
            "context_refs": list(task.evidence), "workspace": "",
            "dependencies": task.dependencies,
            "expected_outputs": [], "verification": task.checkpoint,
            "budget": asdict(task.budget)}


def make_handoff_result(task_id: str, status: str, **kw: Any) -> dict[str, Any]:
    out = {"task_id": task_id, "status": status, "outputs": {},
           "changed_files": [], "tests": {}, "evidence": [],
           "warnings": [], "assumptions": [], "failures": [],
           "handoff": ""}
    out.update(kw)
    return out
