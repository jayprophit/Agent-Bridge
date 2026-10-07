"""Supervised real-process workers through the canonical P20 owners.

Nothing here invents a queue, a task record, a checkpoint, a lock or an
authority model. It wires the ones that already exist into the one thing that
was missing: a supervisor that starts a REAL operating-system worker process,
holds it to a lease, watches its heartbeat, collects its result, verifies the
result independently of the worker, and recovers honestly when the process
dies, hangs or is killed.

Ownership map (unchanged):
- durable task identity ......... taskcenter.TaskCenter
- lease + claim ................. task_dag.WorkQueue
- interruption checkpoints ...... checkpoints.CheckpointManager
- cross-process mutual exclusion . executor.WorkspaceLock
- world-state readback .......... plain filesystem reads (the world, not a record)

The worker process itself (worker_main.py) holds no authority and performs no
consequential action: it transforms bytes inside one assigned directory. Every
consequential decision -- retry, recovery, acceptance -- happens here, in the
supervisor, and acceptance additionally requires independent verification.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from checkpoints import CheckpointManager
from executor import WorkspaceLock
from task_dag import WorkQueue
from taskcenter import TaskCenter

HERE = Path(__file__).resolve().parent
WORKER_ENTRYPOINT = HERE / "worker_main.py"

LEASE_S = 120.0
HEARTBEAT_STALE_S = 10.0


class WorkerError(Exception):
    pass


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SupervisedTask:
    """One durable task bound to one real worker process under one lease."""

    def __init__(self, root: Path, task_id: str, worker_id: str = "worker-1"):
        self.root = Path(root).resolve()
        self.task_id = task_id
        self.worker_id = worker_id
        self.task_dir = self.root / "tasks" / task_id
        self.center = TaskCenter(str(self.root / "taskcenter.json"))
        self.queue = WorkQueue()
        self.node_id: str | None = None
        self.proc: subprocess.Popen | None = None
        self._lease: str | None = None

    def _node(self) -> str:
        if self.node_id is None:
            raise WorkerError('no durable task node exists yet: call assign() first')
        return self.node_id

    @classmethod
    def attach(cls, root: Path, task_id: str, worker_id: str = "worker-1") -> "SupervisedTask":
        """A new supervisor takes over an existing task after the previous
        supervisor died. The binding file is the durable link between the
        task directory and its TaskCenter node; the new supervisor inherits
        the lease file, the heartbeat history and the checkpoint -- never a
        live process handle, which cannot survive a crash by definition."""
        task = cls(root, task_id, worker_id)
        try:
            binding = json.loads((task.task_dir / "binding.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise WorkerError(f"cannot attach to {task_id}: no durable binding: {e}")
        if binding.get("task_id") != task_id:
            raise WorkerError(f"binding mismatch for {task_id}")
        task.node_id = binding["node_id"]
        return task

    # -- assignment ------------------------------------------------------
    def assign(self, input_text: str, supervisor: str = "supervisor") -> dict:
        """Create the durable task, the lease and the worker's assignment.

        The expected output digest is computed from the INPUT here, by the
        supervisor, before any worker exists. That is what makes the later
        verification independent: the check never sees the worker's output
        until the moment it compares.
        """
        self.task_dir.mkdir(parents=True, exist_ok=True)
        took_over = self._take_lease(supervisor)
        (self.task_dir / "input.txt").write_bytes(input_text.encode("utf-8"))
        lines = sorted(set(input_text.splitlines()))
        expected = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
        assignment = {
            "kind": "transform-lines",
            "mode": "sort-unique",
            "input": "input.txt",
            "output": "output.txt",
            "expected_output_digest": expected,
            "worker_id": self.worker_id,
        }
        (self.task_dir / "task.json").write_text(json.dumps(assignment, indent=2), encoding="utf-8")
        return self._register(assignment, supervisor, took_over)

    def assign_model_query(self, questions: list[dict],
                           model: str, supervisor: str = "supervisor",
                           endpoint: str = "http://127.0.0.1:11434") -> dict:
        """Delegate answering to an external model backend.

        Each question carries its own ground truth (`expect`) and match rule,
        declared here by the supervisor before any worker exists. The model
        genuinely performs the answering -- and if it answers wrongly,
        verification fails honestly. That failure is a valid, informative
        outcome, not a broken test.
        """
        self.task_dir.mkdir(parents=True, exist_ok=True)
        took_over = self._take_lease(supervisor)
        for question in questions:
            if not question.get("id") or not question.get("prompt") or "expect" not in question:
                raise WorkerError("each model question needs id, prompt and expect")
            if question.get("match", "exact") not in ("exact", "contains"):
                raise WorkerError(f"unknown match rule {question.get('match')!r}")
        assignment = {
            "kind": "model-query",
            "questions": questions,
            "model": model,
            "endpoint": endpoint,
            "output": "answers.json",
            "per_question_timeout_s": 180.0,
            "worker_id": self.worker_id,
        }
        (self.task_dir / "task.json").write_text(json.dumps(assignment, indent=2), encoding="utf-8")
        return self._register(assignment, supervisor, took_over)

    def assign_freecad(self, script: str, expected_marker: str, artifact: str,
                       timeout_s: float = 300.0,
                       supervisor: str = "supervisor") -> dict:
        """Delegate a bounded application operation.

        The supervisor authors the script, declares the success marker and the
        expected artifact BEFORE any worker exists. The worker only transports
        the approved script to the adapter; authorization happened when the
        supervisor approved this assignment, and verification re-checks the
        marker plus the artifact's existence independently.
        """
        self.task_dir.mkdir(parents=True, exist_ok=True)
        took_over = self._take_lease(supervisor)
        for rel in (script, artifact):
            if rel.startswith("/") or ".." in Path(rel).parts or Path(rel).is_absolute():
                raise WorkerError(f"freecad assignment path escapes the task dir: {rel!r}")
        assignment = {
            "kind": "freecad-task",
            "script": script,
            "expected_marker": expected_marker,
            "artifact": artifact,
            "timeout_s": timeout_s,
            "worker_id": self.worker_id,
        }
        (self.task_dir / "task.json").write_text(json.dumps(assignment, indent=2), encoding="utf-8")
        return self._register(assignment, supervisor, took_over)

    def assign_cura_slice(self, stl: str, artifact: str,
                          settings: dict | None = None,
                          timeout_s: float = 300.0,
                          supervisor: str = "supervisor") -> dict:
        """Delegate a bounded slicing operation.

        The supervisor authors the mesh, declares the expected artifact and
        any extra Cura settings BEFORE any worker exists. The worker only
        transports the approved mesh to the adapter; verification re-checks
        the g-code independently (layer count, extrusion moves).
        """
        self.task_dir.mkdir(parents=True, exist_ok=True)
        took_over = self._take_lease(supervisor)
        for rel in (stl, artifact):
            if rel.startswith("/") or ".." in Path(rel).parts or Path(rel).is_absolute():
                raise WorkerError(f"cura assignment path escapes the task dir: {rel!r}")
        if not stl.lower().endswith(".stl"):
            raise WorkerError(f"cura assignment input is not a .stl file: {stl!r}")
        assignment = {
            "kind": "cura-task",
            "stl": stl,
            "artifact": artifact,
            "settings": dict(settings or {}),
            "timeout_s": timeout_s,
            "worker_id": self.worker_id,
        }
        (self.task_dir / "task.json").write_text(json.dumps(assignment, indent=2), encoding="utf-8")
        return self._register(assignment, supervisor, took_over)

    def assign_openmodelica(self, script: str, expected_marker: str, artifact: str,
                            timeout_s: float = 600.0,
                            supervisor: str = "supervisor") -> dict:
        """Delegate a bounded Modelica simulation.

        The supervisor authors the .mos script, declares the success marker
        and the expected result artifact BEFORE any worker exists. The worker
        only transports the approved script to the adapter; verification
        re-checks the marker plus the artifact's existence independently.
        """
        self.task_dir.mkdir(parents=True, exist_ok=True)
        took_over = self._take_lease(supervisor)
        for rel in (script, artifact):
            if rel.startswith("/") or ".." in Path(rel).parts or Path(rel).is_absolute():
                raise WorkerError(f"openmodelica assignment path escapes the task dir: {rel!r}")
        assignment = {
            "kind": "openmodelica-task",
            "script": script,
            "expected_marker": expected_marker,
            "artifact": artifact,
            "timeout_s": timeout_s,
            "worker_id": self.worker_id,
        }
        (self.task_dir / "task.json").write_text(json.dumps(assignment, indent=2), encoding="utf-8")
        return self._register(assignment, supervisor, took_over)

    def _register(self, assignment: dict, supervisor: str, took_over: bool = False) -> dict:
        node = self.center.add(
            objective=f"{assignment.get('kind', 'task')} {self.task_id}",
            status="ASSIGNED",
            supervisor=supervisor,
            assigned_agent=self.worker_id,
            execution_mode="DELEGATED",
            next_action="spawn worker process",
        )
        self.queue.push(node.task_id)
        claimed = self.queue.claim(lease_s=LEASE_S)
        if claimed != node.task_id:
            raise WorkerError(f"lease claim returned an unexpected task: {claimed!r}")
        self._lease = claimed
        self.node_id = node.task_id
        (self.task_dir / "binding.json").write_text(json.dumps({
            "task_id": self.task_id,
            "node_id": node.task_id,
            "worker_id": self.worker_id,
            "bound_at": time.time(),
        }), encoding="utf-8")
        if took_over:
            self.center.record_evidence(node.task_id, json.dumps({
                "kind": "lease-takeover",
                "at": _utcnow(),
            }))
        self.center.set_status(node.task_id, "RUNNING", by=supervisor,
                               next_action="worker running")
        self.center.save()
        return assignment

    def _lease_path(self) -> Path:
        return self.task_dir / "lease.json"

    def _read_lease(self) -> dict | None:
        try:
            return json.loads(self._lease_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _take_lease(self, supervisor: str) -> bool:
        """Durable, cross-process lease on this task. Returns True when this
        call took over an expired lease left by a previous holder.

        The in-memory WorkQueue orders work inside one supervisor; the lease
        file is what stops two supervisors -- or two processes -- from running
        the same task. It is taken under the workspace lock, expires by time,
        and its takeover is recorded rather than silent.
        """
        with WorkspaceLock(self.root, f"worker-lease-{self.task_id}"):
            existing = self._read_lease()
            if existing is not None and float(existing.get("expires_at", 0.0)) > time.time():
                raise WorkerError(
                    f"task {self.task_id} is leased to {existing.get('holder')!r} "
                    f"until {existing.get('expires_at')}")
            took_over = existing is not None
            self._lease_path().write_text(json.dumps({
                "holder": self.worker_id,
                "supervisor": supervisor,
                "acquired_at": time.time(),
                "expires_at": time.time() + LEASE_S,
            }), encoding="utf-8")
            return took_over

    def _release_lease(self) -> None:
        try:
            self._lease_path().unlink()
        except OSError:
            pass

    # -- execution --------------------------------------------------------
    def spawn(self) -> int:
        """Start the REAL worker process. Returns its OS pid."""
        if self.proc is not None and self.proc.poll() is None:
            raise WorkerError("a worker process is already running for this task")
        with WorkspaceLock(self.root, f"worker-spawn-{self.task_id}"):
            self.proc = subprocess.Popen(
                [sys.executable, str(WORKER_ENTRYPOINT), str(self.task_dir)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return self.proc.pid

    def heartbeat(self) -> dict | None:
        try:
            return json.loads((self.task_dir / "heartbeat.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def heartbeat_age_s(self) -> float | None:
        hb = self.heartbeat()
        if hb is None:
            return None
        return max(0.0, time.time() - float(hb.get("at", 0.0)))

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait_for_completion(self, timeout_s: float = 60.0) -> bool:
        """For a supervisor that attached after a crash: it holds no process
        handle, so it cannot wait() on anything. It observes the durable
        files instead -- result.json appearing means done, heartbeat going
        stale while the process is gone means stalled. Returns True when the
        task reached DONE within the budget."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.check_health() == "DONE":
                return True
            time.sleep(0.2)
        return self.check_health() == "DONE"

    def wait(self, timeout_s: float = 60.0) -> int | None:
        """Wait for exit. Returns the exit code, or None on timeout."""
        if self.proc is None:
            raise WorkerError("no worker process was spawned")
        try:
            return self.proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return None

    def terminate(self) -> None:
        """Kill the worker process. Used for cancellation, timeout and tests
        that prove recovery from a real death -- never from a simulated one."""
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                pass

    # -- recovery ----------------------------------------------------------
    def check_health(self) -> str:
        """RUNNING, STALLED (process dead), STALE (heartbeat too old) or DONE."""
        result_file = self.task_dir / "result.json"
        if result_file.exists():
            try:
                if json.loads(result_file.read_text(encoding="utf-8")).get("ok") is True:
                    return "DONE"
            except (OSError, ValueError):
                pass
        if not self.alive():
            return "STALLED"
        age = self.heartbeat_age_s()
        if age is None or age > HEARTBEAT_STALE_S:
            return "STALE"
        return "RUNNING"

    def recover(self, by: str = "supervisor") -> str:
        """Reconcile a dead or stalled worker WITHOUT re-running blindly.

        The checkpoint tells us how far the worker got; the world (the output
        file, if any) tells us what actually landed. A partial output from a
        killed worker is discarded -- not resumed mid-byte -- because the
        transform is deterministic and re-running it is cheap and safe. That
        reconciliation decision is recorded before any retry happens.
        """
        health = self.check_health()
        if health in ("RUNNING", "DONE"):
            return health
        self.terminate()
        out = self.task_dir / "output.txt"
        partial = out.exists()
        if partial:
            out.unlink()
        self.center.set_status(
            self._node(), "INTERRUPTED", by=by,
            checkpoint=f"health={health} partial_output_discarded={partial}",
            next_action="respawn worker process",
        )
        self.center.record_evidence(self._node(), json.dumps({
            "kind": "worker-recovery",
            "health": health,
            "partial_output_discarded": partial,
            "at": _utcnow(),
        }))
        self.center.save()
        return "INTERRUPTED"

    # -- verification + completion ------------------------------------------
    def verify(self) -> dict:
        """Independent verification, per task kind.

        transform-lines: recompute the expected effect from the INPUT and
        compare digests against the world.
        model-query: apply each question's match rule -- declared by the
        supervisor BEFORE any worker existed -- to the worker's raw answers.
        The worker's claims are not used. A successful process exit alone is
        never sufficient either way.
        """
        assignment = json.loads((self.task_dir / "task.json").read_text(encoding="utf-8"))
        if assignment.get("kind") == "freecad-task":
            return self._verify_freecad_task(assignment)
        if assignment.get("kind") == "cura-task":
            return self._verify_cura_task(assignment)
        if assignment.get("kind") == "openmodelica-task":
            return self._verify_openmodelica_task(assignment)
        out = self.task_dir / Path(assignment.get("output", "output.txt")).name
        if not out.exists():
            return {"verified": False, "reason": "output file absent from the world"}
        if assignment.get("kind") == "model-query":
            return self._verify_model_answers(assignment, out)
        expected = assignment["expected_output_digest"]
        actual = hashlib.sha256(out.read_bytes()).hexdigest()
        if actual != expected:
            return {"verified": False, "reason": "output digest does not match the expected effect"}
        return {"verified": True, "output_digest": actual}

    def _verify_freecad_task(self, assignment: dict) -> dict:
        """The marker declared upfront must appear in the application's own
        transcript, and the declared artifact must exist in the world. The
        worker's exit code is not consulted: FreeCADCmd exits 0 even when
        the script raises, which the adapter tests prove."""
        try:
            result = json.loads((self.task_dir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return {"verified": False, "reason": f"worker result unreadable: {e}"}
        if not result.get("ok"):
            return {"verified": False, "reason": f"worker reported failure: {result.get('stderr_tail', '')[:200]}"}
        marker = assignment.get("expected_marker", "")
        if marker and marker not in result.get("stdout_tail", ""):
            return {"verified": False, "reason": f"expected marker {marker!r} absent from application transcript"}
        artifact = self.task_dir / Path(assignment.get("artifact", "")).name
        if not artifact.exists():
            return {"verified": False, "reason": f"declared artifact {artifact.name} absent from the world"}
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return {"verified": True, "output_digest": digest}

    def _verify_cura_task(self, assignment: dict) -> dict:
        """The worker's exit code is not consulted: CuraEngine happily writes
        an empty file on some failure paths. The declared artifact must pass
        the adapter's independent g-code parse (real layers + extrusion
        moves), recomputed here from the world, not from worker claims."""
        import cura_adapter
        try:
            result = json.loads((self.task_dir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return {"verified": False, "reason": f"worker result unreadable: {e}"}
        if not result.get("ok"):
            return {"verified": False, "reason": f"worker reported failure: {result.get('stderr_tail', '')[:200]}"}
        artifact = self.task_dir / Path(assignment.get("artifact", "")).name
        report = cura_adapter.verify_gcode(artifact)
        if not report.ok:
            return {"verified": False, "reason": f"g-code failed verification: {report.reason}"}
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return {"verified": True, "output_digest": digest,
                "layers": report.layers, "g1_moves": report.g1_moves}

    def _verify_openmodelica_task(self, assignment: dict) -> dict:
        """The marker declared upfront must appear in omc's own transcript,
        and the declared result artifact must exist in the world. The
        worker's exit code is not consulted: omc exits 0 on script paths
        whose simulation never converged, which only marker + artifact
        together exclude."""
        try:
            result = json.loads((self.task_dir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return {"verified": False, "reason": f"worker result unreadable: {e}"}
        if not result.get("ok"):
            return {"verified": False, "reason": f"worker reported failure: {result.get('stderr_tail', '')[:200]}"}
        marker = assignment.get("expected_marker", "")
        if marker and marker not in result.get("stdout_tail", ""):
            return {"verified": False, "reason": f"expected marker {marker!r} absent from application transcript"}
        artifact = self.task_dir / Path(assignment.get("artifact", "")).name
        if not artifact.exists():
            return {"verified": False, "reason": f"declared artifact {artifact.name} absent from the world"}
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return {"verified": True, "output_digest": digest}

    @staticmethod
    def _verify_model_answers(assignment: dict, out: Path) -> dict:

        try:
            answers = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return {"verified": False, "reason": f"answers unreadable: {e}"}
        if not isinstance(answers, dict):
            return {"verified": False, "reason": "answers are not an object"}
        failures: list[str] = []
        for question in assignment.get("questions", []):
            qid = question.get("id", "")
            actual = answers.get(qid, "")
            if not isinstance(actual, str):
                failures.append(f"{qid}: not a string")
                continue
            rule = question.get("match", "exact")
            want = question.get("expect", "")
            if rule == "exact":
                ok = actual.strip() == want
            elif rule == "contains":
                ok = want.lower() in actual.lower()
            else:
                return {"verified": False, "reason": f"unknown match rule {rule!r}"}
            if not ok:
                failures.append(f"{qid}: {actual[:80]!r} does not satisfy {rule} {want!r}")
        if failures:
            return {"verified": False, "reason": "; ".join(failures)}
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        return {"verified": True, "output_digest": digest}

    def complete(self, by: str = "supervisor") -> dict:
        """Verify, record, release the lease and clean up. Refuses to complete
        an unverified task: completion is a verdict, not a status flip."""
        verdict = self.verify()
        if not verdict["verified"]:
            self.center.set_status(self._node(), "FAILED", by=by,
                                   next_action="do not retry without a new assignment")
            self.center.save()
            raise WorkerError(f"refusing to complete an unverified task: {verdict['reason']}")
        self.center.record_evidence(self._node(), json.dumps({
            "kind": "verified-result",
            "output_digest": verdict["output_digest"],
            "verified_by": "supervisor-readback",
            "at": _utcnow(),
        }))
        self.center.set_status(self._node(), "COMPLETED", by=by, next_action="none")
        self.center.save()
        if self._lease is not None:
            self.queue.release(self._lease, requeue=False)
            self._lease = None
        self._release_lease()
        return verdict

    def cleanup(self) -> None:
        """Terminate anything still running and release the lease. The task
        directory (assignment, heartbeats, checkpoints, result) is kept: it is
        the audit trail, and deleting evidence is not cleanup."""
        self.terminate()
        if self._lease is not None:
            try:
                self.queue.release(self._lease, requeue=False)
            finally:
                self._lease = None
        self._release_lease()


def run_supervised(root: Path, task_id: str, input_text: str,
                    timeout_s: float = 60.0) -> dict:
    """The whole honest loop in one call: assign, spawn, wait, verify, close.

    Timeout kills the worker and reports TIMEOUT rather than hanging; an
    unverified result raises instead of completing. Returns the verification
    verdict on success.
    """
    task = SupervisedTask(root, task_id)
    try:
        task.assign(input_text)
        task.spawn()
        code = task.wait(timeout_s=timeout_s)
        if code is None:
            task.terminate()
            task.center.set_status(task._node(), "TIMEOUT", by="supervisor",
                                   next_action="retry with a smaller assignment or larger budget")
            task.center.save()
            raise WorkerError(f"worker exceeded its {timeout_s}s budget and was terminated")
        if code != 0:
            raise WorkerError(f"worker exited with code {code}")
        return task.complete()
    finally:
        task.cleanup()
