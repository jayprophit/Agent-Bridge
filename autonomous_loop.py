"""Autonomous development/adaptation loop (v1).

Implements the programme law as executable code instead of prose:

    UNDERSTAND -> PLAN -> BUILD -> MEASURE -> TEST -> VERIFY
        -> CRITIQUE -> ADAPT -> RECORD -> CONTINUE (repeat)

Loop semantics (non-negotiable):
- CONTINUE never means blindly carrying on: every bounded unit is measured,
  verified, and can change direction (adapt/replan/switch tasks).
- FAIL -> DIAGNOSE -> CHANGE APPROACH -> RETEST, with a per-task attempt cap.
  Repeating the identical failing action indefinitely is forbidden.
- A blocked task is recorded (blocker + evidence) and the loop selects the
  next highest-priority UNBLOCKED task.
- The loop stops only for: no unblocked work, iteration budget exhausted, or
  a genuine OWNER GATE (payment, legal, public release, visibility change,
  destructive deletion, credentials, dangerous control, major architecture
  conflict). Ordinary failures never stop the loop.

The loop drives an AdaptiveTaskGraph with injected executor/verifier
callables, so it is fully testable headless and resumable from checkpoints.
Runtime state lives under repo-local storage (localdirs), never the Desktop.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from localdirs import local_subdir
from task_dag import AdaptiveTaskGraph, TaskRecord, TaskStatus

OWNER_GATES = frozenset({
    "PAYMENT", "LEGAL_ACCEPTANCE", "LICENCE_PURCHASE", "PUBLIC_RELEASE",
    "VISIBILITY_CHANGE", "DESTRUCTIVE_DELETION", "CREDENTIAL_ACTION",
    "DANGEROUS_CONTROL", "MAJOR_ARCH_CONFLICT",
})

@dataclass
class ExecResult:
    ok: bool = False
    output: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    approach: str = "default"   # executor labels what it tried (for adapt tracking)


@dataclass
class VerifyResult:
    achieved: bool = False
    failures: list[str] = field(default_factory=list)
    measures: dict[str, Any] = field(default_factory=dict)


@dataclass
class IterationRecord:
    iteration: int = 0
    task_id: str = ""
    stage: str = ""             # last stage reached
    attempt: int = 0
    approach: str = ""
    verified: bool = False
    adapted: bool = False
    blocked: str = ""           # blocker reason if the task was blocked
    gate: str = ""              # owner gate if the loop stopped here
    duration_s: float = 0.0
    detail: str = ""


@dataclass
class LoopReport:
    iterations: int = 0
    verified: list[str] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    gate: str = ""
    gate_task: str = ""
    stopped: str = ""           # NO_UNBLOCKED_WORK | BUDGET_EXHAUSTED | OWNER_GATE
    records: list[IterationRecord] = field(default_factory=list)


@dataclass
class LoopConfig:
    max_iterations: int = 50
    max_attempts_per_task: int = 3
    checkpoint_path: str = ""   # default: repo-local runtime dir


def _deps_met(task: TaskRecord, by_id: dict[str, TaskRecord]) -> bool:
    refs = list(task.dependencies or [])
    if task.parent_task:
        refs.append(task.parent_task)
    for r in refs:
        dep = by_id.get(r)
        if dep is None or dep.status != TaskStatus.VERIFIED_COMPLETE:
            return False
    return True


class AutonomousLoop:
    """PLAN -> BUILD -> MEASURE/TEST -> VERIFY -> CRITIQUE -> ADAPT -> RECORD -> CONTINUE."""

    def __init__(self, graph: AdaptiveTaskGraph,
                 executor: Callable[[TaskRecord, int], ExecResult],
                 verifier: Callable[[TaskRecord, ExecResult], VerifyResult],
                 config: LoopConfig | None = None):
        self.graph = graph
        self.executor = executor
        self.verifier = verifier
        self.config = config or LoopConfig()
        self.attempts: dict[str, int] = {}
        self.report = LoopReport()
        self._iteration = 0
        ckpt = self.config.checkpoint_path or str(
            Path(local_subdir("runtime", create=True)) / "autonomous_loop_checkpoint.json")
        self.checkpoint_path = ckpt
        self._restore()

    # -- checkpoint ------------------------------------------------------
    def _snapshot(self) -> dict[str, Any]:
        return {"tasks": {t.task_id: t.status.value for t in self.graph.tasks.values()}
                if hasattr(self.graph, "tasks") else {},
                "attempts": self.attempts,
                "iterations": self._iteration,
                "verified": self.report.verified,
                "blocked": self.report.blocked,
                "failed": self.report.failed}

    def _checkpoint(self) -> None:
        try:
            Path(self.checkpoint_path).write_text(json.dumps(self._snapshot(), indent=1),
                                                   encoding="utf-8")
        except OSError:
            pass  # checkpoint best-effort; loop state stays in memory

    def _restore(self) -> None:
        try:
            snap = json.loads(Path(self.checkpoint_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        tasks = getattr(self.graph, "tasks", {})
        for tid, st in (snap.get("tasks") or {}).items():
            if tid in tasks:
                try:
                    tasks[tid].status = TaskStatus(st)
                except ValueError:
                    pass
        self.attempts = dict(snap.get("attempts") or {})
        self._iteration = int(snap.get("iterations") or 0)
        self.report.verified = list(snap.get("verified") or [])
        self.report.blocked = dict(snap.get("blocked") or {})
        self.report.failed = list(snap.get("failed") or [])

    # -- selection --------------------------------------------------------
    def _select(self) -> TaskRecord | None:
        """Highest-priority unblocked task whose dependencies are verified.

        Owner-gated tasks are skipped while runnable work exists (a gate must
        not starve the loop); the highest-priority waiting gated task is
        returned only when nothing else is runnable, so step() records the
        gate stop instead of executing it.
        """
        by_id = getattr(self.graph, "tasks", {})
        runnable = [t for t in by_id.values()
                    if t.status in (TaskStatus.PLANNED, TaskStatus.QUEUED, TaskStatus.RETRYING)
                    and t.task_id not in self.report.blocked
                    and _deps_met(t, by_id)]
        open_tasks = [t for t in runnable
                      if (getattr(t, "owner_gate", "") or "") not in OWNER_GATES]
        if open_tasks:
            open_tasks.sort(key=lambda t: (getattr(t, "priority", 5), t.task_id))
            return open_tasks[0]
        gated = [t for t in runnable
                 if (getattr(t, "owner_gate", "") or "") in OWNER_GATES]
        if gated:
            gated.sort(key=lambda t: (getattr(t, "priority", 5), t.task_id))
            return gated[0]
        return None

    # -- one bounded unit ---------------------------------------------------
    def step(self) -> IterationRecord | None:
        """UNDERSTAND (select) -> BUILD (execute) -> MEASURE/TEST (verify)
        -> CRITIQUE/ADAPT -> RECORD. Returns None when no unblocked work."""
        task = self._select()
        if task is None:
            return None
        # Owner gate check BEFORE execution: never cross without the owner.
        gate = getattr(task, "owner_gate", "") or ""
        if gate in OWNER_GATES:
            rec = IterationRecord(iteration=self._iteration, task_id=task.task_id,
                                  stage="GATE", gate=gate,
                                  detail="owner gate: execution refused without owner")
            self.report.gate, self.report.gate_task = gate, task.task_id
            self.report.records.append(rec)
            self._checkpoint()
            return rec
        self._iteration += 1
        t0 = time.monotonic()
        attempt = self.attempts.get(task.task_id, 0) + 1
        self.attempts[task.task_id] = attempt
        task.status = TaskStatus.RUNNING
        adapted = attempt > 1
        try:
            exec_res = self.executor(task, attempt)          # BUILD (bounded unit)
            verify_res = self.verifier(task, exec_res)       # MEASURE / TEST / VERIFY
        except Exception as e:                               # CRITIQUE: harness fault
            exec_res = ExecResult(ok=False, error=f"harness: {e}")
            verify_res = VerifyResult(achieved=False, failures=[f"harness: {e}"])
        if verify_res.achieved:                              # VERIFIED -> RECORD
            task.status = TaskStatus.VERIFIED_COMPLETE
            if task.task_id not in self.report.verified:
                self.report.verified.append(task.task_id)
            rec = IterationRecord(iteration=self._iteration, task_id=task.task_id,
                                  stage="VERIFIED", attempt=attempt,
                                  approach=exec_res.approach, verified=True,
                                  adapted=adapted,
                                  duration_s=round(time.monotonic() - t0, 3))
        elif attempt >= self.config.max_attempts_per_task:
            # DIAGNOSE -> BLOCK (approach exhausted) -> switch task next step.
            task.status = TaskStatus.BLOCKED
            reason = "; ".join(verify_res.failures or [exec_res.error or "unverified"])[:300]
            self.report.blocked[task.task_id] = reason
            if task.task_id not in self.report.failed:
                self.report.failed.append(task.task_id)
            rec = IterationRecord(iteration=self._iteration, task_id=task.task_id,
                                  stage="BLOCKED", attempt=attempt,
                                  approach=exec_res.approach, adapted=True,
                                  blocked=reason,
                                  duration_s=round(time.monotonic() - t0, 3),
                                  detail="attempt budget exhausted; approach varied each try")
        else:                                                # ADAPT -> RETEST next step
            task.status = TaskStatus.RETRYING
            rec = IterationRecord(iteration=self._iteration, task_id=task.task_id,
                                  stage="ADAPT", attempt=attempt,
                                  approach=exec_res.approach, adapted=True,
                                  duration_s=round(time.monotonic() - t0, 3),
                                  detail="; ".join(verify_res.failures or
                                                   [exec_res.error or "unverified"])[:300])
        self.report.records.append(rec)
        self._checkpoint()
        return rec

    # -- full loop ------------------------------------------------------------
    def run(self) -> LoopReport:
        """CONTINUE until no unblocked work, budget exhausted, or owner gate."""
        while self._iteration < self.config.max_iterations:
            if self.report.gate:
                self.report.stopped = "OWNER_GATE"
                break
            rec = self.step()
            if rec is None:
                self.report.stopped = "NO_UNBLOCKED_WORK"
                break
            if rec.gate:
                self.report.stopped = "OWNER_GATE"
                break
        else:
            self.report.stopped = "BUDGET_EXHAUSTED"
        self.report.iterations = self._iteration
        self._checkpoint()
        return self.report
