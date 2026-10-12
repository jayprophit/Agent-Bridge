"""Permanent Active Supervision (§1-§38 of the supervision directive).

Hermes is the ACTIVE SUPERVISOR of the entire workforce — not a dispatcher.
For every active worker:

    ASSIGN -> VERIFY TASK RECEIVED -> MONITOR -> DETECT COMPLETION/BLOCKER
    -> READ HANDOFF -> VERIFY CLAIMS -> GAP ANALYSIS
    -> ACCEPT / CORRECT / EXTEND / REASSIGN -> ISSUE NEXT TASK -> CONTINUE

Extends, never duplicates (§49): worker selection/reservation already lives in
compute/hive_scheduler.py (WORKER_SCORE router, write-set ownership,
WAITING_FOR_QUOTA); this module adds the SUPERVISION LOOP around it — worker
records with heartbeat/stall detection (§4), mandatory structured handoffs
(§5), the handoff review queue with verdicts (§6), automatic next-work
assignment (§25), and the review-queue model that guarantees no handoff is
ever left unread (§30).

Honesty: a worker self-report is a CLAIM until verified (§1); review verdicts
carry the evidence that justified them (§6); no worker is silently dropped.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

# --- worker lifecycle states (§2 — the FULL vocabulary) -----------------------
AVAILABLE = "AVAILABLE"
ASSIGNED = "ASSIGNED"
ANALYSING = "ANALYSING"
PLANNING = "PLANNING"
IMPLEMENTING = "IMPLEMENTING"
TESTING = "TESTING"
FIXING = "FIXING"
REVIEWING = "REVIEWING"
DOCUMENTING = "DOCUMENTING"
COMMITTING = "COMMITTING"
PUSHING = "PUSHING"
WAITING = "WAITING"
WAITING_FOR_QUOTA = "WAITING_FOR_QUOTA"
BLOCKED = "BLOCKED"
INTERRUPTED = "INTERRUPTED"
HUNG = "HUNG"
AWAITING_QA = "AWAITING_QA"
COMPLETE = "COMPLETE"
OFFLINE = "OFFLINE"

WORKER_STATES = frozenset({
    AVAILABLE, ASSIGNED, ANALYSING, PLANNING, IMPLEMENTING, TESTING, FIXING,
    REVIEWING, DOCUMENTING, COMMITTING, PUSHING, WAITING, WAITING_FOR_QUOTA,
    BLOCKED, INTERRUPTED, HUNG, AWAITING_QA, COMPLETE, OFFLINE})

# states from which a worker may accept new work (§25)
ACTIVE_WORK_STATES = frozenset({
    ASSIGNED, ANALYSING, PLANNING, IMPLEMENTING, TESTING, FIXING, REVIEWING,
    DOCUMENTING, COMMITTING, PUSHING})

# states meaning "not currently doing useful work" (§8)
IDLE_STATES = frozenset({AVAILABLE, WAITING})

# states requiring supervisor intervention (§3, §32)
INTERVENTION_STATES = frozenset({
    BLOCKED, INTERRUPTED, HUNG, WAITING_FOR_QUOTA, AWAITING_QA, COMPLETE})

# --- review verdicts (§6) ------------------------------------------------------
ACCEPT = "ACCEPT"
CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
CONTINUE_SAME_WORKER = "CONTINUE_SAME_WORKER"
EXTEND_SCOPE = "EXTEND_SCOPE_WITHIN_PROJECT"
REASSIGN = "REASSIGN"
CROSS_AGENT_REVIEW = "CROSS_AGENT_REVIEW"
BLOCKED_VERDICT = "BLOCKED"

REVIEW_VERDICTS = frozenset({
    ACCEPT, CORRECTION_REQUIRED, CONTINUE_SAME_WORKER, EXTEND_SCOPE,
    REASSIGN, CROSS_AGENT_REVIEW, BLOCKED_VERDICT})

# gap severities (§19)
CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
DEFERRED = "DEFERRED"
SUPERSEDED = "SUPERSEDED"

GAP_SEVERITIES = frozenset({CRITICAL, HIGH, MEDIUM, LOW, DEFERRED, SUPERSEDED})

DEFAULT_STALL_THRESHOLD_S = 600.0   # no heartbeat for 10 min -> investigate (§4)


def _now() -> float:
    return time.time()


@dataclass
class WorkerRecord:
    """One supervised worker (§2 — the full record)."""
    worker_id: str
    worker_type: str                  # HERMES_INTERNAL / EXTERNAL_AI_AGENT / ...
    application: str
    role: str
    status: str = AVAILABLE
    project: str = ""
    task_id: str = ""
    task_description: str = ""
    repo: str = ""
    worktree: str = ""
    branch: str = ""
    write_set: str = ""
    model: str = ""
    provider: str = ""
    tier: str = ""
    phase: str = ""
    started_at: float = 0.0
    last_heartbeat: float = field(default_factory=_now)
    last_activity: float = field(default_factory=_now)
    files_changed: list[str] = field(default_factory=list)
    tests: dict[str, Any] = field(default_factory=dict)
    latest_commit: str = ""
    latest_push: str = ""
    blockers: list[str] = field(default_factory=list)
    handoff_state: str = ""
    review_state: str = ""
    next_action: str = ""
    # §4/§16: live quota state (pool, reset_at, resets_in_s) so the
    # dashboard shows WAITING_FOR_QUOTA with its real reset time.
    quota_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Handoff:
    """Structured worker handoff (§5 — mandatory, never lost)."""
    task_id: str
    worker_id: str
    project: str
    objective: str = ""
    completed_work: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    repo: str = ""
    branch: str = ""
    baseline_sha: str = ""
    current_sha: str = ""
    tests_run: list[str] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    implementation_decisions: list[str] = field(default_factory=list)
    research_used: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    known_gaps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    received_at: float = field(default_factory=_now)
    reviewed: bool = False
    review_verdict: str = ""
    review_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Handoff":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Gap:
    """A gap-analysis finding (§19)."""
    gap_id: str
    severity: str
    category: str          # feature / test / security / docs / integration ...
    description: str
    evidence: list[str] = field(default_factory=list)
    project: str = ""
    created_at: float = field(default_factory=_now)
    disposition: str = ""  # ADD_TO_BACKLOG / REFERENCE / SUPERSEDED / ...

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Supervisor:
    """The permanent active supervision loop (§1-§38).

    The loop itself is driven externally (one supervise() call per cycle);
    this class is the STATE MACHINE that makes each cycle correct:
    no unread handoffs (§30), no idle worker while ready work exists (§8),
    no silently-dropped worker (§32), verdicts backed by evidence (§6).
    """

    def __init__(self, stall_threshold_s: float = DEFAULT_STALL_THRESHOLD_S,
                 event_sink: Optional[Callable[[dict[str, Any]], None]] = None
                 ) -> None:
        self._lock = threading.RLock()
        self._workers: dict[str, WorkerRecord] = {}
        self._handoffs: list[Handoff] = []
        self._gaps: list[Gap] = []
        self._stall_threshold_s = stall_threshold_s
        self._event_sink = event_sink or (lambda e: None)
        self._cycle = 0
        self._last_progress_at = _now()

    # -- events ------------------------------------------------------------------
    def _emit(self, event: str, **payload: Any) -> None:
        try:
            self._event_sink({"event": event, "timestamp": _now(), **payload})
        except Exception:
            pass   # an event sink must never break supervision

    # -- worker registry (§2) -----------------------------------------------------
    def register_worker(self, worker_id: str, worker_type: str,
                        application: str, role: str, **kwargs: Any
                        ) -> WorkerRecord:
        with self._lock:
            rec = self._workers.get(worker_id)
            if rec is None:
                rec = WorkerRecord(worker_id=worker_id,
                                   worker_type=worker_type,
                                   application=application, role=role)
                self._workers[worker_id] = rec
            for k, v in kwargs.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
            return rec

    def worker(self, worker_id: str) -> Optional[WorkerRecord]:
        return self._workers.get(worker_id)

    def heartbeat(self, worker_id: str, status: Optional[str] = None,
                  **fields: Any) -> None:
        """§4: fresh activity resets stall detection; status/fields update."""
        with self._lock:
            rec = self._workers.get(worker_id)
            if rec is None:
                raise KeyError(f"unknown worker {worker_id!r} — register first")
            now = _now()
            rec.last_heartbeat = now
            rec.last_activity = now
            if status is not None:
                if status not in WORKER_STATES:
                    raise ValueError(f"unknown worker state {status!r}")
                rec.status = status
            for k, v in fields.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
            self._last_progress_at = now

    # -- stall detection (§4) -----------------------------------------------------
    def stalled_workers(self, now: Optional[float] = None) -> list[WorkerRecord]:
        """Workers whose heartbeat went stale while in an active state —
        candidates for HUNG/INTERRUPTED investigation, NOT instant failure."""
        now = now or _now()
        out = []
        for rec in self._workers.values():
            if rec.status in ACTIVE_WORK_STATES and \
                    (now - rec.last_heartbeat) > self._stall_threshold_s:
                out.append(rec)
        return out

    def intervene_on_stalls(self) -> list[dict[str, Any]]:
        """§4: investigate-then-act. Marks a stalled active worker INTERRUPTED
        (checkpoint point) — never assumes failure, never kills blindly."""
        actions = []
        for rec in self.stalled_workers():
            age = _now() - rec.last_heartbeat
            rec.status = INTERRUPTED
            rec.review_state = "stall_detected"
            action = {
                "worker_id": rec.worker_id,
                "action": "checkpoint_and_investigate",
                "stale_for_s": round(age, 1),
                "previous_task": rec.task_id,
            }
            actions.append(action)
            self._emit("worker.stalled", **action)
        return actions

    # -- assignment (§8, §25) -----------------------------------------------------
    def assign(self, worker_id: str, task_id: str, description: str,
               project: str = "", **task_fields: Any) -> dict[str, Any]:
        """Issue work to an AVAILABLE/WAITING worker (§8: no idle worker while
        ready work exists — but §8 also forbids inventing fake work)."""
        with self._lock:
            rec = self._workers.get(worker_id)
            if rec is None:
                raise KeyError(f"unknown worker {worker_id!r}")
            if rec.status not in IDLE_STATES:
                return {"assigned": False,
                        "reason": f"worker {rec.status}, not idle",
                        "worker_id": worker_id}
            rec.status = ASSIGNED
            rec.task_id = task_id
            rec.task_description = description
            rec.project = project
            rec.started_at = _now()
            rec.handoff_state = ""
            rec.review_state = ""
            for k, v in task_fields.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
            out = {"assigned": True, "worker_id": worker_id, "task_id": task_id}
            self._emit("worker.assigned", **out)
            return out

    def idle_workers(self) -> list[WorkerRecord]:
        return [r for r in self._workers.values() if r.status in IDLE_STATES]

    def find_ready_work_for(self, worker: WorkerRecord,
                            ready_tasks: list[dict[str, Any]]) -> Optional[dict]:
        """§8/§25: pick the best ready task for THIS worker (capability +
        write-set conflict check delegated to the caller's scheduler)."""
        for task in ready_tasks:
            if task.get("assigned_to"):
                continue
            caps = set(task.get("capabilities", []))
            if caps and worker.role not in caps and \
                    worker.application not in caps:
                continue
            return task
        return None

    def auto_assign(self, ready_tasks: list[dict[str, Any]]) -> list[dict]:
        """§25: after accepted work (or every cycle), give idle workers their
        next task. Returns what was assigned. No fake work is invented (§8)."""
        assigned = []
        for rec in self.idle_workers():
            task = self.find_ready_work_for(rec, ready_tasks)
            if task is None:
                continue
            task["assigned_to"] = rec.worker_id
            result = self.assign(rec.worker_id, task["task_id"],
                                 task.get("description", ""),
                                 project=task.get("project", ""))
            if result.get("assigned"):
                assigned.append(result)
        return assigned

    # -- handoff ingestion (§5, §30) -----------------------------------------------
    def submit_handoff(self, handoff: Handoff) -> dict[str, Any]:
        """A worker completing a bounded unit MUST hand off (§5). The handoff
        enters the review queue immediately — it is never left unread (§30)."""
        with self._lock:
            rec = self._workers.get(handoff.worker_id)
            if rec is not None:
                rec.status = AWAITING_QA
                rec.handoff_state = "submitted"
                rec.latest_commit = handoff.current_sha or rec.latest_commit
                rec.files_changed = handoff.files_changed
            self._handoffs.append(handoff)
            out = {"handoff_received": True, "task_id": handoff.task_id,
                   "worker_id": handoff.worker_id,
                   "queue_position": len(self._handoffs)}
            self._emit("worker.completed", **out)
            self._emit("supervisor.review_queued", **out)
            return out

    def unreviewed_handoffs(self) -> list[Handoff]:
        return [h for h in self._handoffs if not h.reviewed]

    def review_handoff(self, task_id: str,
                       verifier: Callable[[Handoff], tuple[str, list[str]]]
                       ) -> dict[str, Any]:
        """§6: READ -> INSPECT -> VERIFY -> GAP ANALYSIS -> verdict.

        `verifier` is injected (Hermes supplies the real evidence checks —
        git/diff/tests/requirements); it returns (verdict, evidence list).
        The supervisor never marks ACCEPT without evidence (§6, §1)."""
        with self._lock:
            handoff = next((h for h in self._handoffs
                            if h.task_id == task_id and not h.reviewed), None)
            if handoff is None:
                return {"reviewed": False,
                        "reason": f"no unreviewed handoff for {task_id!r}"}
            verdict, evidence = verifier(handoff)
            if verdict not in REVIEW_VERDICTS:
                raise ValueError(f"unknown verdict {verdict!r}")
            if verdict == ACCEPT and not evidence:
                # §2 of the completion directive: completion is EVIDENCE-backed;
                # an ACCEPT with zero evidence is a false completion.
                return {"reviewed": False,
                        "reason": "ACCEPT requires evidence (§2) — verifier "
                                  "returned none"}
            handoff.reviewed = True
            handoff.review_verdict = verdict
            handoff.review_evidence = evidence
            rec = self._workers.get(handoff.worker_id)
            if rec is not None:
                rec.handoff_state = "reviewed"
                rec.review_state = verdict.lower()
                if verdict == ACCEPT:
                    rec.status = AVAILABLE
                    rec.next_action = handoff.recommended_next_action
                elif verdict in (CORRECTION_REQUIRED, CONTINUE_SAME_WORKER):
                    rec.status = FIXING
                elif verdict == REASSIGN:
                    rec.status = AVAILABLE
                    rec.task_id = ""
            out = {"reviewed": True, "task_id": task_id,
                   "verdict": verdict, "evidence_count": len(evidence)}
            self._emit("supervisor.handoff_reviewed", **out)
            return out

    # -- gap analysis (§17-§19) ------------------------------------------------------
    def record_gap(self, gap: Gap) -> dict[str, Any]:
        """§7/§19: a handoff or review that reveals missing work CREATES a task
        — 'task complete' never terminates a workstream (§7)."""
        if gap.severity not in GAP_SEVERITIES:
            raise ValueError(f"unknown gap severity {gap.severity!r}")
        with self._lock:
            self._gaps.append(gap)
            out = {"gap_recorded": True, "gap_id": gap.gap_id,
                   "severity": gap.severity, "category": gap.category}
            self._emit("supervisor.gap_found", **out)
            return out

    def open_gaps(self, min_severity: Optional[str] = None) -> list[Gap]:
        order = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, DEFERRED: 4,
                 SUPERSEDED: 5}
        gaps = [g for g in self._gaps if not g.disposition]
        if min_severity:
            floor = order[min_severity]
            gaps = [g for g in gaps if order[g.severity] <= floor]
        return sorted(gaps, key=lambda g: (order[g.severity], g.created_at))

    # -- the supervision cycle (§33) --------------------------------------------------
    def supervise(self, ready_tasks: Optional[list[dict[str, Any]]] = None,
                  auto_review: bool = True) -> dict[str, Any]:
        """ONE full supervisor cycle (§33). Pure state machine: no I/O — the
        caller supplies live evidence (adapters) and receives actions to take.

        Returns everything that happened so Hermes can act on it."""
        with self._lock:
            self._cycle += 1
            cycle_actions: dict[str, Any] = {
                "cycle": self._cycle,
                "interventions": self.intervene_on_stalls(),
                "assigned": self.auto_assign(ready_tasks or []),
                "handoffs_pending": len(self.unreviewed_handoffs()),
                "idle_workers": [r.worker_id for r in self.idle_workers()],
                "open_gaps": [g.gap_id for g in self.open_gaps()],
                "needs_intervention": [
                    r.worker_id for r in self._workers.values()
                    if r.status in INTERVENTION_STATES],
            }
            if any(cycle_actions[k] for k in
                   ("interventions", "assigned")) or \
                    cycle_actions["handoffs_pending"]:
                self._last_progress_at = _now()
            self._emit("supervisor.cycle", **{k: v for k, v in
                                              cycle_actions.items()
                                              if k != "cycle"})
            return cycle_actions

    # -- persistence (§32, §35 of the completion directive) ---------------------------
    def save(self, path: "str | Path") -> None:
        data = {
            "stall_threshold_s": self._stall_threshold_s,
            "workers": {k: v.to_dict() for k, v in self._workers.items()},
            "handoffs": [h.to_dict() for h in self._handoffs],
            "gaps": [g.to_dict() for g in self._gaps],
            "cycle": self._cycle,
            "continuation_required": bool(self.unreviewed_handoffs()
                                          or self.open_gaps()),
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: "str | Path") -> "Supervisor":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        sup = cls(stall_threshold_s=data.get("stall_threshold_s",
                                             DEFAULT_STALL_THRESHOLD_S))
        for wid, wd in data.get("workers", {}).items():
            known = {f for f in WorkerRecord.__dataclass_fields__}
            sup._workers[wid] = WorkerRecord(
                **{k: v for k, v in wd.items() if k in known})
        for hd in data.get("handoffs", []):
            sup._handoffs.append(Handoff.from_dict(hd))
        for gd in data.get("gaps", []):
            known = {f for f in Gap.__dataclass_fields__}
            sup._gaps.append(Gap(**{k: v for k, v in gd.items()
                                    if k in known}))
        sup._cycle = data.get("cycle", 0)
        return sup

    # -- dashboard view (§35) ----------------------------------------------------------
    def overview(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for r in self._workers.values():
            by_status[r.status] = by_status.get(r.status, 0) + 1
        return {
            "cycle": self._cycle,
            "workers_total": len(self._workers),
            "workers_by_status": by_status,
            "handoffs_pending": len(self.unreviewed_handoffs()),
            "handoffs_total": len(self._handoffs),
            "gaps_open": len(self.open_gaps()),
            "gaps_by_severity": {
                sev: sum(1 for g in self.open_gaps() if g.severity == sev)
                for sev in (CRITICAL, HIGH, MEDIUM, LOW, DEFERRED)},
            "continuation_required": bool(self.unreviewed_handoffs()
                                          or self.open_gaps()),
            "last_progress_at": self._last_progress_at,
        }
