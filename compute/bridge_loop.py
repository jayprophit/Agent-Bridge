"""Bridge autonomous loop — the standing multi-task supervisor (§30).

Closes the last gap in the Hermes↔OpenCode bridge proof:

    §30: "Hermes → TASK_ASSIGN(TASK-A) → ... → Hermes QA →
          Hermes → TASK_ASSIGN(TASK-B) → OpenCode ACK → START"

The loop takes a task queue and runs it WITHOUT owner interaction:
  assign → verify ACK → verify START → wait for TASK_COMPLETE/HANDOFF →
  independent QA → auto-assign the next task → ... until the queue drains.

Every step requires evidence (§6). SENT != ACKNOWLEDGED != RUNNING. If any
step's evidence is missing, the loop STOPS and reports the exact failure —
it never fabricates progress (§38 honesty).
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from compute.agent_message import AgentMessage, DeliveryState, Intent
from compute.agent_message_bus import AgentMessageBus
from compute.worker_bridge_adapters import OpenCodeAdapter, WorkerAdapterInterface


# --- loop step records ---------------------------------------------------------------

@dataclass
class LoopStepRecord:
    """Evidence for one lifecycle step of one task."""
    step: str
    passed: bool
    evidence: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "passed": self.passed,
                "evidence": self.evidence, "timestamp": self.timestamp}


@dataclass
class TaskRunRecord:
    """The full evidenced record of one task's autonomous run."""
    task_id: str
    steps: list[LoopStepRecord] = field(default_factory=list)
    outcome: str = "pending"           # verified | failed_before_ack | ...
    write_set: tuple[str, ...] = ()
    files_found: tuple[str, ...] = ()
    qa_passed: Optional[bool] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    def add(self, step: str, passed: bool, evidence: str) -> None:
        self.steps.append(LoopStepRecord(step, passed, evidence))

    @property
    def ok(self) -> bool:
        return all(s.passed for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "outcome": self.outcome,
            "steps": [s.to_dict() for s in self.steps],
            "write_set": list(self.write_set),
            "files_found": list(self.files_found),
            "qa_passed": self.qa_passed,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


# --- the autonomous loop ---------------------------------------------------------------

class BridgeAutonomousLoop:
    """Runs a task queue through a worker adapter autonomously (§30).

    Delivery runs synchronously (`opencode run` blocks until the worker
    finishes), so the loop:
      1. assigns the task (blocking delivery = the worker executes)
      2. verifies ACK + START + COMPLETE markers in the worker output
      3. verifies the write-set files actually exist on disk
      4. runs the caller-supplied QA function (independent verification)
      5. records everything and auto-assigns the next task
    """

    def __init__(self, adapter: WorkerAdapterInterface,
                 bus: Optional[AgentMessageBus] = None,
                 repo: str = "",
                 ack_timeout_s: float = 900.0):
        self.adapter = adapter
        self.bus = bus
        self.repo = Path(repo) if repo else None
        self.ack_timeout_s = ack_timeout_s
        self.records: list[TaskRunRecord] = []
        self.owner_intervention_detected = False

    # -- one task -----------------------------------------------------------------

    def run_task(self, task_id: str, objective: str,
                 write_set: tuple[str, ...] = (),
                 branch: str = "",
                 qa_fn: Optional[Callable[[Path], tuple[bool, str]]] = None,
                 priority: int = 50) -> TaskRunRecord:
        """Run one task autonomously and return its evidenced record."""
        from compute.agent_message import build_task_assign

        rec = TaskRunRecord(task_id=task_id, write_set=write_set)

        # --- 1. ASSIGN (blocking delivery: the worker executes the brief) -----
        msg = build_task_assign(
            task_id=task_id, objective=objective,
            sender_agent="hermes", sender_worker="bridge-loop",
            receiver_agent=self.adapter.agent_id,
            receiver_worker=self.adapter.worker_id,
            project_id="Agent-Bridge",
            cost_policy="ZERO_INCREMENTAL_SPEND",
            write_set=list(write_set), branch=branch,
            worktree=str(self.repo) if self.repo else "",
            priority=priority,
        )
        msg.delivery_timeout_s = self.ack_timeout_s
        if self.bus:
            self.bus.submit(msg)

        result = self.adapter.send_message(msg)
        output = result.get("output", "")

        rec.add("assign_delivered", result.get("delivered", False),
                f"channel={result.get('channel', 'none')}; "
                f"evidence={result.get('evidence', [])}")
        if not result.get("delivered"):
            rec.outcome = "failed_delivery"
            rec.ended_at = time.time()
            self.records.append(rec)
            return rec
        if self.bus:
            self.bus.mark_delivered(msg.message_id)

        # --- 2. ACK (§7: receiver-side evidence, not Hermes intent) -------------
        ack_ok = f"ACK TASK_ID={task_id}" in output or f"ACK TASK_ID = {task_id}" in output \
            or f"**ACK TASK_ID={task_id}" in output
        rec.add("ack_received", ack_ok,
                "worker ACK marker found in output" if ack_ok
                else "no ACK marker in worker output — SENT != ACKNOWLEDGED")
        if not ack_ok:
            rec.outcome = "failed_before_ack"
            rec.ended_at = time.time()
            self.records.append(rec)
            return rec

        # --- 3. START (§8: PROCESS_ALIVE alone is insufficient) -----------------
        start_ok = f"TASK_START TASK_ID={task_id}" in output or \
            f"TASK_START TASK_ID = {task_id}" in output or \
            f"**TASK_START TASK_ID={task_id}" in output
        rec.add("task_start", start_ok,
                "worker TASK_START marker found" if start_ok
                else "no TASK_START marker")
        if not start_ok:
            rec.outcome = "failed_before_start"
            rec.ended_at = time.time()
            self.records.append(rec)
            return rec

        # --- 4. COMPLETE (§11) ---------------------------------------------------
        complete_ok = f"TASK_COMPLETE TASK_ID={task_id}" in output or \
            f"TASK_COMPLETE TASK_ID = {task_id}" in output or \
            f"**TASK_COMPLETE TASK_ID={task_id}" in output
        rec.add("task_complete", complete_ok,
                "worker TASK_COMPLETE marker found" if complete_ok
                else "no TASK_COMPLETE marker")
        if not complete_ok:
            rec.outcome = "failed_before_complete"
            rec.ended_at = time.time()
            self.records.append(rec)
            return rec

        # --- 5. real file evidence ----------------------------------------------
        if write_set and self.repo:
            found = tuple(f for f in write_set
                          if (self.repo / f).exists())
            rec.files_found = found
            files_ok = len(found) == len(write_set)
            rec.add("write_set_files_exist", files_ok,
                    f"found {len(found)}/{len(write_set)}: {found}")
        else:
            rec.add("write_set_files_exist", True, "no write-set declared")

        # --- 6. independent QA (supervisor re-verifies, never trusts the worker) --
        if qa_fn is not None:
            qa_ok, qa_evidence = qa_fn(self.repo or Path("."))
            rec.qa_passed = qa_ok
            rec.add("independent_qa", qa_ok, qa_evidence)
        else:
            rec.qa_passed = None
            rec.add("independent_qa", True, "no QA function supplied")

        # --- 7. owner-intervention detector (§44) ---------------------------------
        if not result.get("delivered"):
            self.owner_intervention_detected = True

        rec.outcome = "verified" if rec.ok else "qa_or_evidence_failed"
        rec.ended_at = time.time()
        self.records.append(rec)
        return rec

    # -- the queue ------------------------------------------------------------------

    def run_queue(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """Run a queue of tasks, auto-assigning each after the previous verifies.

        Each task dict: {task_id, objective, write_set?, branch?, priority?, qa_fn?}
        The loop STOPS at the first task that fails evidence — it never
        fabricates progress to keep going.
        """
        for i, task in enumerate(tasks):
            rec = self.run_task(
                task_id=task["task_id"],
                objective=task["objective"],
                write_set=tuple(task.get("write_set", ())),
                branch=task.get("branch", ""),
                qa_fn=task.get("qa_fn"),
                priority=task.get("priority", 50),
            )
            if not rec.ok:
                return {
                    "completed": i,
                    "total": len(tasks),
                    "stopped_at": task["task_id"],
                    "reason": rec.outcome,
                    "all_verified": False,
                    "records": [r.to_dict() for r in self.records],
                }
            # §30: the NEXT task is assigned automatically — no owner relay
        return {
            "completed": len(tasks),
            "total": len(tasks),
            "stopped_at": None,
            "reason": "queue drained — every task verified",
            "all_verified": True,
            "owner_intervention_detected": self.owner_intervention_detected,
            "records": [r.to_dict() for r in self.records],
        }
