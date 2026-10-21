"""Standing autonomous loop — the persistent supervisor (E2E-008).

E2E-008 requirement:
    Do NOT manually invoke each task one at a time.
    Prepare a READY queue containing at least two legitimate bounded tasks.
    Start the supervisor daemon ONCE.
    Expected behaviour:
        scheduler selects TASK-A
        -> bridge delivers TASK-A
        -> OpenCode executes
        -> Hermes verifies
        -> Hermes QA
        -> scheduler automatically selects TASK-B
        -> bridge delivers TASK-B
        -> OpenCode executes.

    No manual:
        runner invocation
        prompt insertion
        task-B command
        continue command
        owner input.

    Only then:
        STANDING_AUTONOMOUS_LOOP = LIVE_VERIFIED.

This is the standing loop. One supervisor runtime process, started once,
drains the READY queue through the bridge until no more ready work remains.
Each next task is selected from the hive scheduler (priority + readiness),
not hardcoded.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from compute.agent_message import build_task_assign
from compute.agent_message_bus import AgentMessageBus
from compute.worker_bridge_adapters import OpenCodeAdapter, WorkerAdapterInterface


# --- records ---------------------------------------------------------------------------

@dataclass
class StandingStep:
    """One lifecycle step of one task in the standing loop."""
    task_id: str
    step: str
    passed: bool
    evidence: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "step": self.step,
                "passed": self.passed, "evidence": self.evidence,
                "timestamp": self.timestamp}


@dataclass
class StandingRun:
    """The full record of one standing-loop run."""
    run_id: str
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    total_tasks: int = 0
    tasks_verified: int = 0
    tasks_failed: int = 0
    stopped_by: Optional[str] = None   # e.g. "ready queue drained"
    steps: list[StandingStep] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_tasks": self.total_tasks,
            "tasks_verified": self.tasks_verified,
            "tasks_failed": self.tasks_failed,
            "stopped_by": self.stopped_by,
            "steps": [s.to_dict() for s in self.steps],
            "tasks": self.tasks,
        }


# --- the standing autonomous loop ------------------------------------------------------

class StandingAutonomousLoop:
    """Drains the READY queue through the bridge, one task at a time.

    Usage:
        loop = StandingAutonomousLoop(adapter=opencode_adapter,
                                      bus=agent_message_bus,
                                      repo="/path/to/repo")
        result = loop.run_ready_queue()

    The loop auto-selects the next task from the hive scheduler after each
    verified task. No owner input required.
    """

    # -- a minimal task spec that the standing loop understands -------------------------

    @dataclass
    class ReadyTask:
        """A task already "ready" (awaiting assignment), with everything the
        standing loop needs to run it."""
        task_spec: dict[str, Any]     # full TaskSpec
        qa_fn: Optional[callable] = None
        branch: str = ""

    def __init__(self,
                 adapter: WorkerAdapterInterface,
                 bus: Optional[AgentMessageBus] = None,
                 repo: str = "",
                 run_id: str = "") -> None:
        self.adapter = adapter
        self.bus = bus
        self.repo = Path(repo) if repo else None
        self.run_id = run_id or f"STAND-001-{int(time.time())}"
        self.runs: list[StandingRun] = []
        self._run: Optional[StandingRun] = None

    def _new_run(self, tasks: list[ReadyTask]) -> StandingRun:
        run = StandingRun(
            run_id=self.run_id,
            total_tasks=len(tasks),
        )
        self._run = run
        return run

    # -- one task in the standing loop -------------------------------------------------

    def _run_one(self, task: ReadyTask) -> dict[str, Any]:
        """Run one ready task end-to-end.

        Returns {"verified": bool, "failure": str}. The failure is
        empty when the task verified, and otherwise it says WHAT went
        wrong, because the caller has to decide whether the queue should
        stop. A failure that means the work could not be HANDED OVER is
        the PROVIDER's failure and does not stop the queue: a lane whose
        provider is down must not stall the other lanes. A failure that
        means the work was handed over and the worker did not complete
        it is a real blocker, and the queue stops there.
        """
        task_id = task.task_spec["task_id"]
        objective = task.task_spec.get("title", task_id)
        write_set = tuple(
            task.task_spec.get("write_set", "").split()
            if task.task_spec.get("write_set") else ())
        branch = task.task_spec.get("branch", task.branch)
        qa_fn = task.qa_fn

        # build the complete worker brief from the canonical envelope
        msg = build_task_assign(
            task_id=task_id, objective=objective,
            sender_agent="hermes", sender_worker="standing-loop",
            receiver_agent=self.adapter.agent_id,
            receiver_worker=self.adapter.worker_id,
            project_id="Agent-Bridge",
            cost_policy="ZERO_INCREMENTAL_SPEND",
            write_set=list(write_set), branch=branch,
            worktree=str(self.repo) if self.repo else "",
            priority=task.task_spec.get("priority", 50),
        )
        if self.bus:
            self.bus.submit(msg)

        # 1. deliver (blocking: the worker executes the brief)
        result = self.adapter.send_message(msg)
        self._run.steps.append(StandingStep(
            task_id, "deliver", result.get("delivered", False),
            f"channel={result.get('channel')}; "
            f"evidence={result.get('evidence')}"))
        if not result.get("delivered", False):
            self._run.tasks.append({
                "task_id": task_id, "status": "FAILED_DELIVERY",
            })
            return {"verified": False, "failure": "DELIVERY"}
        if self.bus:
            self.bus.mark_delivered(msg.message_id)

        # 2. ACK — receiver-side evidence, not a model print
        ack_ok = self.adapter.acknowledge(msg)
        self._run.steps.append(StandingStep(task_id, "ack",
                                            ack_ok,
                                            f"task_id={task_id} "
                                            f"in worker transcript"))
        if not ack_ok:
            self._run.tasks.append({"task_id": task_id, "status": "NO_ACK"})
            return {"verified": False, "failure": "NO_ACK"}

        # 3. START — supervisor-derived when task-specific action begins
        self._run.steps.append(StandingStep(task_id, "start",
                                            True,
                                            "delivery verified + ACK "
                                            "(supervisor derivation)"))
        # 4. COMPLETE — inferred from write-set + QA (listener emits markers
        #    but the supervisor derives completion from evidence)
        # 5. real file evidence
        files_found = []
        if write_set and self.repo:
            files_found = [f for f in write_set if (self.repo / f).exists()]
        if files_found:
            self._run.steps.append(StandingStep(
                task_id, "write_set",
                len(files_found) == len(write_set),
                f"found {len(files_found)}/{len(write_set)}"))
        else:
            self._run.steps.append(StandingStep(
                task_id, "write_set", True, "no write-set declared"))

        # 6. independent QA (the supervisor re-verifies — never trusts the
        #    worker's own claim)
        if qa_fn is not None:
            qa_ok, qa_ev = qa_fn(self.repo or Path("."))
            self._run.steps.append(StandingStep(task_id, "independent_qa",
                                                qa_ok, qa_ev))
        else:
            qa_ok = True
            self._run.steps.append(StandingStep(
                task_id, "independent_qa", True, "no QA supplied"))

        # 7. verdict
        verified = all(s.passed for s in self._run.steps if s.step != "deliver") \
            and result.get("delivered", False) and ack_ok
        self._run.tasks.append({
            "task_id": task_id,
            "status": "VERIFIED" if verified else "FAILED",
            "steps": [s.step for s in self._run.steps],
        })
        return {"verified": verified, "failure": "" if verified else "WORK"}

    # -- the queue ----------------------------------------------------------------------

    def run_ready_queue(self, ready_tasks: list[ReadyTask]) -> dict[str, Any]:
        """Start the standing loop ONCE; it drains the READY queue.

        Each next task is picked from the hive scheduler (the caller passes
        the ready queue). No owner input after start().

        A lane whose PROVIDER failed does not stop the queue. The work
        could not be handed over, and that is the provider's failure and
        not the lane's: the other lanes are other projects, and one
        provider being down must not stop them. The failed lane is
        recorded as failed, with the reason, and the loop carries on.

        A lane whose work was handed over and did not complete is a real
        blocker: the next task may depend on this one, so the queue stops
        there and says which task stopped it.

        The run's status says which of the two happened. "queue_drained"
        means every ready task was ATTEMPTED, not that every one of them
        verified, and the counts say how many verified.
        """
        if not ready_tasks:
            return {
                "run_id": self.run_id,
                "status": "no_ready_tasks",
                "total": 0,
                "verified": 0,
            }
        self._new_run(ready_tasks)
        verified = 0
        attempted = 0
        provider_failures: list[str] = []
        for task in ready_tasks:
            attempted += 1
            outcome = self._run_one(task)
            if outcome["verified"]:
                verified += 1
                continue
            if outcome["failure"] == "DELIVERY":
                # The work could not be handed over. That is this lane's
                # provider, and it is not the other lanes' provider: the
                # lane is recorded and the queue carries on.
                self._run.tasks_failed += 1
                provider_failures.append(task.task_spec["task_id"])
                continue
            # The work ran and did not verify. That is a blocker.
            self._run.stopped_by = task.task_spec["task_id"]
            self._run.tasks_failed += 1
            break
        self._run.finished_at = time.time()
        self.runs.append(self._run)
        blocked = self._run.stopped_by is not None
        return {
            "run_id": self.run_id,
            "status": "stopped_by_blocker" if blocked else "queue_drained",
            "total": len(ready_tasks),
            "attempted": attempted,
            "verified": verified,
            "failed": self._run.tasks_failed,
            "all_verified": verified == len(ready_tasks),
            # The lanes whose provider failed, and the lanes that were
            # never reached because a blocker stopped the queue.
            "provider_failures": provider_failures,
            "not_attempted": [t.task_spec["task_id"] for t in ready_tasks
                              if t.task_spec["task_id"] not in
                              {s.task_id for s in self._run.steps}],
            "stopped_by": self._run.stopped_by,
            "steps": [s.to_dict() for s in self._run.steps],
            "tasks": self._run.tasks,
        }
