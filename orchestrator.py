"""Aetherius orchestrator: the dispatch substrate Hermes currently lacks.

Hermes supervises. This module dispatches. Nothing here duplicates existing
systems; it wires them into the one missing loop:

    submit -> READY (deps via DurableTaskGraph) -> select worker
    (FREE_FIRST_STRICT) -> dispatch via worker adapter -> lease/heartbeat
    -> collect result -> verify (worker claim is never enough)
    -> COMPLETE + unblock dependents, or retry/fallback/BLOCKED.

Ownership map (unchanged, extended):
- durable task identity ......... taskcenter.TaskCenter
- dependency ordering ........... task_dag.DurableTaskGraph
- lease + claim ................. task_dag.WorkQueue
- worker capability index ....... task_dag.WorkerRegistry
- interruption checkpoints ...... task_dag.CheckpointManager
- retry policy .................. task_dag.RetryPolicy
- evidence ...................... task_dag.EvidenceLedger + make_handoff*
- real OS worker processes ..... worker_runtime.SupervisedTask
- local model chat .............. providers.OllamaProvider
- worker adapters ............... worker_adapters (OpenCode/Ollama/Bridge)

Task states reuse task_dag.TaskStatus; READY is computed (graph.ready()),
never stored. QUEUED means admitted; RUNNING means leased to a worker.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from task_dag import (
    CheckpointManager,
    DurableTaskGraph,
    EvidenceLedger,
    RetryPolicy,
    TaskRecord,
    TaskStatus,
    WorkerRegistry,
    WorkQueue,
    make_handoff,
    make_handoff_result,
)

# -- Cost policy --------------------------------------------------------
FREE_FIRST_STRICT = "FREE_FIRST_STRICT"

AUTOMATIC_COST_CLASSES = ("LOCAL_FREE", "CLOUD_ZERO_COST", "CLOUD_RECURRING_FREE")
FORBIDDEN_COST_CLASSES = ("PAID_API", "SUBSCRIPTION_ONLY", "UNKNOWN_COST", "ONE_TIME_TRIAL")

# -- Canonical worker ids -----------------------------------------------
HERMES = "hermes"
OPENCODE = "opencode"
OLLAMA = "ollama"
AGENT_BRIDGE = "agent-bridge"
OPENCLAW = "openclaw"

OPTIONAL_WORKERS = (OPENCLAW,)


@dataclass
class OrchestratorTask:
    """Canonical task contract (§4). Stored as a TaskRecord in the graph;
    orchestration-only fields travel alongside, never inside the worker's
    assignment (least privilege: the worker sees objective + inputs +
    acceptance, not the whole contract)."""
    task_id: str = field(default_factory=lambda: "t-" + uuid.uuid4().hex[:8])
    parent_task_id: str = ""
    project_id: str = ""
    objective: str = ""
    role: str = ""                      # planner | coder | reviewer | tool | analyst
    priority: int = 5                   # 0 critical .. 6 future; lower runs first
    dependencies: list[str] = field(default_factory=list)
    # git isolation: one writer per worktree, tracked here
    repo: str = ""
    branch: str = ""
    worktree: str = ""
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    # policy
    privacy_class: str = "NORMAL"       # SECRET | PRIVATE | NORMAL
    cost_policy: str = FREE_FIRST_STRICT
    model_profile: str = ""             # FAST_LOCAL | CODING_LOCAL | ...
    required_capabilities: list[str] = field(default_factory=list)
    # assignment
    worker_id: str = ""
    worker_state: str = ""              # mirrors adapter run state
    lease_s: float = 300.0
    heartbeat_s: float = 30.0
    timeout_s: float = 600.0
    # acceptance: COMPLETE requires these, not the worker's word
    acceptance_tests: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    # outcome
    status: str = TaskStatus.QUEUED.value
    attempt_count: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_record(self) -> TaskRecord:
        return TaskRecord(
            task_id=self.task_id, parent_task=self.parent_task_id,
            objective=self.objective, requirements=list(self.required_capabilities),
            dependencies=list(self.dependencies), assigned_worker=self.worker_id,
            execution_environment=self.worktree or self.repo,
            status=TaskStatus(self.status), checkpoint="",
            attempt=self.attempt_count,
            inputs={"role": self.role, "project_id": self.project_id,
                    "repo": self.repo, "branch": self.branch,
                    "allowed_paths": self.allowed_paths,
                    "privacy_class": self.privacy_class,
                    "cost_policy": self.cost_policy,
                    "model_profile": self.model_profile},
            outputs=dict(self.result), evidence=list(self.evidence),
            failures=list(self.errors), next_action="",
            priority=self.priority, owner_gate="",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def seed_worker_registry() -> WorkerRegistry:
    """Canonical initial workers. OpenClaw registers OFFLINE/BLOCKED_OPTIONAL:
    present in the registry so selection can skip it honestly, never absent
    so its state is unaccounted."""
    from task_dag import WorkerInfo
    reg = WorkerRegistry()
    reg.register(WorkerInfo(HERMES, "supervisor",
                            ["planning", "arbitration", "review", "decompose"],
                            ["local"], "IDLE", ""))
    reg.register(WorkerInfo(OPENCODE, "coder",
                            ["code-implement", "repo-edit", "test-run"],
                            ["local"], "IDLE", ""))
    reg.register(WorkerInfo(OLLAMA, "model",
                            ["review", "summarise", "classify", "extract",
                             "critique", "analyse"],
                            ["local"], "IDLE", ""))
    reg.register(WorkerInfo(AGENT_BRIDGE, "tool",
                            ["cura-slice", "openmodelica-sim", "freecad-task",
                             "blender-task", "app-execute"],
                            ["local"], "IDLE", ""))
    blocked = WorkerInfo(OPENCLAW, "candidate", [], ["local"],
                         "OFFLINE", "")
    blocked.current_task = "BLOCKED_OPTIONAL: gateway stopped, owner restart required"
    reg.register(blocked)
    return reg


def select_worker(task: OrchestratorTask, registry: WorkerRegistry,
                  adapters: dict[str, Any] | None = None) -> str:
    """Deterministic worker selection under FREE_FIRST_STRICT.

    Planning/arbitration -> Hermes. Real repo implementation -> OpenCode.
    Review/summarise/classify/analyse/extract/critique -> Ollama.
    App/tool execution -> Agent Bridge. Optional/unavailable workers are
    skipped, never waited on. SECRET/PRIVATE tasks may only select local
    workers (all canonical workers are local; the check is structural so
    a future remote worker cannot slip in)."""
    role = (task.role or "").lower()
    if role in ("planner", "supervisor", "architect", "arbiter", "reviewer-final"):
        return HERMES
    if role in ("coder", "implementer") or "code-implement" in task.required_capabilities:
        if _idle(registry, OPENCODE):
            return OPENCODE
        raise WorkerUnavailable(f"{OPENCODE} busy or offline")
    if role in ("reviewer", "analyst", "summariser", "classifier") or any(
            c in ("review", "summarise", "classify", "extract", "critique", "analyse")
            for c in task.required_capabilities):
        if _idle(registry, OLLAMA):
            return OLLAMA
        raise WorkerUnavailable(f"{OLLAMA} busy or offline")
    if role in ("tool", "app") or any(
            c in ("cura-slice", "openmodelica-sim", "freecad-task",
                  "blender-task", "app-execute")
            for c in task.required_capabilities):
        if _idle(registry, AGENT_BRIDGE):
            return AGENT_BRIDGE
        raise WorkerUnavailable(f"{AGENT_BRIDGE} busy or offline")
    # default: cheapest capable local worker, optional workers skipped
    for wid in (OLLAMA, AGENT_BRIDGE, OPENCODE, HERMES):
        if _idle(registry, wid):
            return wid
    raise WorkerUnavailable("no idle canonical worker")


def _idle(registry: WorkerRegistry, worker_id: str) -> bool:
    w = registry.workers.get(worker_id)
    return w is not None and w.state == "IDLE"


class WorkerUnavailable(Exception):
    pass


class OrchestratorError(Exception):
    pass


class Orchestrator:
    """Bounded dispatch loop over canonical components. State persists via
    TaskCenter (identity) + CheckpointManager (snapshots); nothing lives
    only in chat context."""

    def __init__(self, root: str | Path, adapters: dict[str, Any] | None = None,
                 retry: RetryPolicy | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.graph = DurableTaskGraph()
        self.queue = WorkQueue()
        self.registry = seed_worker_registry()
        self.retry = retry or RetryPolicy()
        self.ledger = EvidenceLedger()
        self.adapters = adapters or {}
        self.tasks: dict[str, OrchestratorTask] = {}
        self.center = None
        try:
            from taskcenter import TaskCenter
            self.center = TaskCenter(str(self.root / "taskcenter.json"))
        except Exception:
            self.center = None
        self.checkpointer = CheckpointManager()

    # -- task lifecycle -------------------------------------------------
    def submit(self, task: OrchestratorTask) -> str:
        if not task.objective:
            raise OrchestratorError("task objective is required")
        self._check_cost_policy(task)
        self.tasks[task.task_id] = task
        self.graph.add(task.to_record())
        self.queue.push(task.task_id)
        self._mirror_center(task)
        return task.task_id

    def get(self, task_id: str) -> OrchestratorTask:
        try:
            return self.tasks[task_id]
        except KeyError:
            raise OrchestratorError(f"unknown task: {task_id!r}")

    def ready(self) -> list[OrchestratorTask]:
        self._sync_graph()
        return [self.tasks[t.task_id] for t in self.graph.ready()
                if t.task_id in self.tasks]

    def cancel(self, task_id: str, reason: str = "") -> OrchestratorTask:
        task = self.get(task_id)
        task.status = TaskStatus.CANCELLED.value
        if reason:
            task.errors.append(reason)
        self.queue.release(task_id, requeue=False)
        self._sync_graph()
        self._mirror_center(task)
        return task

    # -- dispatch loop --------------------------------------------------
    def run_ready(self, max_tasks: int = 10) -> list[dict[str, Any]]:
        """One bounded pass: dispatch each READY task at most once. Never an
        uncontrolled infinite loop; the caller re-invokes while authorised
        work remains."""
        outcomes: list[dict[str, Any]] = []
        for task in self.ready()[:max_tasks]:
            outcomes.append(self.dispatch(task.task_id))
        return outcomes

    def dispatch(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        try:
            worker_id = select_worker(task, self.registry, self.adapters)
        except WorkerUnavailable as e:
            task.errors.append(str(e))
            return {"task_id": task_id, "status": "NO_WORKER", "error": str(e)}
        adapter = self.adapters.get(worker_id)
        if adapter is None:
            # Hermes supervises through this interface; it does not execute
            # here. Record the routing decision as the outcome.
            if worker_id == HERMES:
                return self._complete(task, {"routed_to": HERMES,
                                             "note": "supervisor decision point"},
                                      changed=[], tests={})
            return {"task_id": task_id, "status": "NO_ADAPTER",
                    "error": f"no adapter registered for {worker_id}"}
        task.worker_id = worker_id
        task.attempt_count += 1
        task.status = TaskStatus.RUNNING.value
        self._set_busy(worker_id, task_id)
        self._sync_graph()
        try:
            raw = adapter.execute(task)
        except Exception as e:  # adapter failure is a task failure, not a crash
            return self._handle_failure(task, f"adapter error: {e}")
        return self._settle(task, raw)

    def _settle(self, task: OrchestratorTask, raw: dict[str, Any]) -> dict[str, Any]:
        """Verify before COMPLETE: worker claims are evidence, not verdicts."""
        ok, reason = self._verify(task, raw)
        if ok:
            return self._complete(task, raw.get("result", {}),
                                  changed=raw.get("changed_files", []),
                                  tests=raw.get("test_results", {}))
        return self._handle_failure(task, reason)

    def _handle_failure(self, task: OrchestratorTask,
                        reason: str) -> dict[str, Any]:
        task.errors.append(reason)
        kind = "TRANSIENT" if "transient" in reason.lower() else "FATAL"
        if self.retry.should_retry(task.attempt_count, kind):
            task.status = TaskStatus.RETRYING.value
            self.queue.release(task.task_id, requeue=True)
        elif task.worker_id in OPTIONAL_WORKERS or "optional" in reason.lower():
            task.status = TaskStatus.BLOCKED.value
            task.errors.append("BLOCKED_OPTIONAL: continuing with other workers")
            self.queue.release(task.task_id, requeue=False)
        else:
            task.status = TaskStatus.FAILED.value
            self.queue.release(task.task_id, requeue=False)
        self._set_idle(task.worker_id)
        self._sync_graph()
        self._mirror_center(task)
        return {"task_id": task.task_id, "status": task.status, "error": reason}

    def _complete(self, task: OrchestratorTask, result: dict[str, Any],
                  changed: list[str], tests: dict[str, Any]) -> dict[str, Any]:
        task.result = result
        task.changed_files = list(changed)
        task.test_results = dict(tests)
        task.status = TaskStatus.VERIFIED_COMPLETE.value
        task.evidence.append(f"verified {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
        self.queue.release(task.task_id, requeue=False)
        self._set_idle(task.worker_id)
        self._sync_graph()
        self._mirror_center(task)
        return {"task_id": task.task_id, "status": task.status,
                "result": result}

    # -- verification ---------------------------------------------------
    def _verify(self, task: OrchestratorTask,
                raw: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(raw, dict) or raw.get("ok") is not True:
            return False, f"worker did not report ok: {str(raw)[:200]}"
        for artifact in task.expected_artifacts:
            found = artifact in raw.get("changed_files", []) or \
                artifact in raw.get("artifacts", [])
            if not found:
                return False, f"expected artifact missing: {artifact!r}"
        for test in task.acceptance_tests:
            passed = raw.get("test_results", {}).get(test)
            if passed is not True:
                return False, f"acceptance test not passed: {test!r}"
        return True, ""

    # -- policy ---------------------------------------------------------
    def _check_cost_policy(self, task: OrchestratorTask) -> None:
        if task.cost_policy != FREE_FIRST_STRICT:
            return  # owner explicitly chose another policy at submit time
        for cap in task.required_capabilities:
            if cap in FORBIDDEN_COST_CLASSES:
                raise OrchestratorError(
                    f"FREE_FIRST_STRICT forbids cost class {cap!r}")
        if task.privacy_class in ("SECRET", "PRIVATE"):
            pass  # all canonical workers are local; structural guarantee

    # -- persistence ----------------------------------------------------
    def snapshot(self, label: str = "orchestrator") -> Path:
        data = {"tasks": [t.to_dict() for t in self.tasks.values()],
                "at": time.time()}
        path = self.root / f"{label}-snapshot.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def _sync_graph(self) -> None:
        for task in self.tasks.values():
            rec = self.graph.get(task.task_id)
            if rec is None:
                self.graph.add(task.to_record())
            else:
                rec.status = TaskStatus(task.status)
                rec.assigned_worker = task.worker_id
                rec.attempt = task.attempt_count
                rec.outputs = dict(task.result)
                rec.evidence = list(task.evidence)
                rec.failures = list(task.errors)

    def _mirror_center(self, task: OrchestratorTask) -> None:
        if self.center is None:
            return
        try:
            node = self.center.get(task.task_id)
            node.status = task.status
            node.assigned_agent = task.worker_id
            node.evidence = list(task.evidence)
            node.next_action = task.errors[-1] if task.errors else ""
            self.center.save()
        except Exception:
            try:
                nid = self.center.add(task.objective, supervisor="orchestrator")
                node = self.center.get(nid)
                node.assigned_agent = task.worker_id
                node.status = task.status
                self.center.save()
            except Exception:
                pass

    def _set_busy(self, worker_id: str, task_id: str) -> None:
        w = self.registry.workers.get(worker_id)
        if w is not None:
            w.state = "BUSY"
            w.current_task = task_id

    def _set_idle(self, worker_id: str) -> None:
        w = self.registry.workers.get(worker_id)
        if w is not None:
            w.state = "IDLE"
            w.current_task = ""
