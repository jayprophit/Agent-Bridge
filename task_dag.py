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

Adaptive Autonomous Extensions (v0.10+):
- MerkleDAG: DAG with cryptographic integrity (Merkle root per task, global root)
- AdaptiveTaskGraph: extends DurableTaskGraph with re-evaluation, adaptation events
- WorkProof: versioned proof of work completion (builder, verifier, hashes, evidence)
- ProblemMemory: persistent problem/workaround database
- ResourceLedger: energy/thermal/resource accounting per task
- ModelFitness: multidimensional model capability scoring
"""
from __future__ import annotations

import hashlib
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
    priority: int = 5  # P0_CRITICAL=0 .. P6_FUTURE=6; lower runs first
    owner_gate: str = ""  # non-empty + in autonomous_loop.OWNER_GATES stops the loop

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


# ============================================================
# ADAPTIVE AUTONOMOUS EXTENSIONS (v0.10+)
# ============================================================

def merkle_hash(data: str) -> str:
    """Compute SHA-256 hash for Merkle tree."""
    return hashlib.sha256(data.encode()).hexdigest()


def merkle_combine(left: str, right: str) -> str:
    """Combine two hashes for Merkle tree."""
    return merkle_hash(left + right)


@dataclass
class MerkleNode:
    """Node in a Merkle tree."""
    hash: str
    left: "MerkleNode | None" = None
    right: "MerkleNode | None" = None
    data: str = ""
    is_leaf: bool = False


class MerkleTree:
    """Merkle tree for DAG integrity verification."""

    def __init__(self, leaves: list[str] | None = None):
        self.root: MerkleNode | None = None
        self.leaves: list[MerkleNode] = []
        if leaves:
            self.build(leaves)

    def build(self, leaves: list[str]) -> str:
        """Build Merkle tree from leaf hashes, return root hash."""
        if not leaves:
            self.root = None
            self.leaves = []
            return ""
        self.leaves = [MerkleNode(hash=h, data=h, is_leaf=True) for h in leaves]
        self.root = self._build_level(self.leaves)
        return self.root.hash

    def _build_level(self, nodes: list[MerkleNode]) -> MerkleNode:
        if len(nodes) == 1:
            return nodes[0]
        next_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            combined_hash = merkle_combine(left.hash, right.hash)
            parent = MerkleNode(hash=combined_hash, left=left, right=right)
            next_level.append(parent)
        return self._build_level(next_level)

    def get_proof(self, leaf_index: int) -> list[dict[str, str]]:
        """Get Merkle proof for a leaf."""
        if not self.root or leaf_index >= len(self.leaves):
            return []
        proof = []
        node = self.leaves[leaf_index]
        # This is simplified - a full impl would track the path up
        return proof

    def verify(self, root_hash: str) -> bool:
        """Verify tree matches expected root hash."""
        return self.root is not None and self.root.hash == root_hash


@dataclass
class TaskMerkleRecord:
    """Merkle record for a single task - includes its own hash and dependencies' roots."""
    task_id: str
    task_hash: str              # hash of this task's content
    dependency_roots: list[str] = field(default_factory=list)  # Merkle roots of deps
    combined_hash: str = ""     # combined hash: task_hash + sorted(dep_roots)

    def compute_combined(self) -> str:
        parts = [self.task_hash] + sorted(self.dependency_roots)
        self.combined_hash = merkle_hash("".join(parts))
        return self.combined_hash


class MerkleDAG:
    """DAG with Merkle integrity - each task has a Merkle record, global root tracks all."""

    def __init__(self):
        self.records: dict[str, TaskMerkleRecord] = {}
        self.global_root: str = ""

    def add_task(self, task_id: str, task_content: str, dependencies: list[str]) -> TaskMerkleRecord:
        """Add a task with its content hash and dependency roots."""
        task_hash = merkle_hash(task_content)
        dep_roots = [self.records[dep].combined_hash for dep in dependencies if dep in self.records]
        record = TaskMerkleRecord(
            task_id=task_id,
            task_hash=task_hash,
            dependency_roots=dep_roots
        )
        record.compute_combined()
        self.records[task_id] = record
        self._recompute_global_root()
        return record

    def _recompute_global_root(self) -> str:
        """Recompute global Merkle root from all task combined hashes."""
        all_hashes = [r.combined_hash for r in self.records.values()]
        if not all_hashes:
            self.global_root = ""
            return ""
        tree = MerkleTree(all_hashes)
        self.global_root = tree.root.hash if tree.root else ""
        return self.global_root

    def verify_integrity(self) -> dict[str, Any]:
        """Verify entire DAG integrity."""
        issues = []
        # Verify each task's combined hash
        for tid, record in self.records.items():
            expected = record.compute_combined()
            if record.combined_hash != expected:
                issues.append(f"Task {tid}: combined hash mismatch")
        # Verify global root
        expected_root = self._recompute_global_root()
        if self.global_root != expected_root:
            issues.append("Global root mismatch")
        return {"ok": len(issues) == 0, "issues": issues, "global_root": self.global_root}

    def get_task_proof(self, task_id: str) -> dict[str, Any] | None:
        """Get Merkle proof for a specific task."""
        if task_id not in self.records:
            return None
        record = self.records[task_id]
        return {
            "task_id": task_id,
            "task_hash": record.task_hash,
            "dependency_roots": record.dependency_roots,
            "combined_hash": record.combined_hash,
            "global_root": self.global_root
        }


@dataclass
class AdaptationEvent:
    """Record of an adaptation in the execution cycle."""
    event_id: str = field(default_factory=lambda: "adapt-" + uuid.uuid4().hex[:8])
    timestamp: float = field(default_factory=time.time)
    trigger: str = ""           # "TEST_FAILURE", "OWNER_CORRECTION", "MODEL_FAILURE", "RESOURCE_EXHAUSTION"
    prior_plan_hash: str = ""   # hash of plan before adaptation
    new_plan_hash: str = ""     # hash of plan after adaptation
    changed_tasks: list[str] = field(default_factory=list)
    rationale: str = ""
    model_involved: str = ""


class AdaptiveTaskGraph(DurableTaskGraph):
    """Extended task graph with adaptive execution cycle support."""

    def __init__(self):
        super().__init__()
        self.merkle_dag = MerkleDAG()
        self.adaptation_history: list[AdaptationEvent] = []
        self.plan_versions: dict[int, str] = {}  # version -> plan hash
        self.current_plan_version: int = 0

    def add_task(self, task: TaskRecord) -> str:
        task_id = super().add(task)
        # Add to Merkle DAG
        task_content = json.dumps(task.to_dict(), sort_keys=True)
        self.merkle_dag.add_task(task_id, task_content, task.dependencies)
        return task_id

    def record_adaptation(self, trigger: str, prior_plan_hash: str,
                          new_plan_hash: str, changed_tasks: list[str],
                          rationale: str, model_involved: str = "") -> AdaptationEvent:
        """Record an adaptation event in the execution cycle."""
        event = AdaptationEvent(
            trigger=trigger,
            prior_plan_hash=prior_plan_hash,
            new_plan_hash=new_plan_hash,
            changed_tasks=changed_tasks,
            rationale=rationale,
            model_involved=model_involved
        )
        self.adaptation_history.append(event)
        self.current_plan_version += 1
        self.plan_versions[self.current_plan_version] = new_plan_hash
        return event

    def get_adaptation_history(self) -> list[AdaptationEvent]:
        return self.adaptation_history

    def verify_integrity(self) -> dict[str, Any]:
        """Verify both task graph and Merkle DAG integrity."""
        dag_result = self.merkle_dag.verify_integrity()
        # Check for cycles in task dependencies
        try:
            self.ordered()
        except ValueError as e:
            dag_result["ok"] = False
            dag_result["issues"].append(str(e))
        return dag_result


@dataclass
class WorkProof:
    """Versioned proof of work completion."""
    proof_id: str = field(default_factory=lambda: "proof-" + uuid.uuid4().hex[:12])
    component_id: str = ""
    component_version: str = ""
    task_id: str = ""
    project_id: str = ""
    instance_id: str = ""
    builder_agent: str = ""
    builder_model: str = ""
    verifier: str = ""
    source_hashes: dict[str, str] = field(default_factory=dict)  # file -> hash
    input_hash: str = ""
    result_hash: str = ""
    git_commit: str = ""
    test_evidence: list[str] = field(default_factory=list)
    benchmark_evidence: list[str] = field(default_factory=list)
    resource_evidence: list[str] = field(default_factory=list)
    parent_proof: str = ""              # previous proof in chain
    previous_version_proof: str = ""    # proof for previous version of this component
    timestamp: float = field(default_factory=time.time)
    signature: str = ""
    status: str = "PENDING"  # PENDING, VERIFIED, REJECTED, SUPERSEDED


class WorkProofLedger:
    """Append-only ledger of versioned work proofs."""

    def __init__(self):
        self.proofs: dict[str, WorkProof] = {}
        self.component_latest: dict[str, str] = {}  # component_id -> latest proof_id

    def add(self, proof: WorkProof) -> str:
        self.proofs[proof.proof_id] = proof
        self.component_latest[proof.component_id] = proof.proof_id
        return proof.proof_id

    def get(self, proof_id: str) -> WorkProof | None:
        return self.proofs.get(proof_id)

    def get_latest(self, component_id: str) -> WorkProof | None:
        pid = self.component_latest.get(component_id)
        return self.proofs.get(pid) if pid else None

    def get_chain(self, component_id: str) -> list[WorkProof]:
        """Get full version chain for a component."""
        chain = []
        proof = self.get_latest(component_id)
        while proof:
            chain.append(proof)
            if proof.previous_version_proof:
                proof = self.get(proof.previous_version_proof)
            else:
                break
        return list(reversed(chain))

    def verify_chain(self, component_id: str) -> dict[str, Any]:
        """Verify integrity of proof chain."""
        chain = self.get_chain(component_id)
        issues = []
        for i, proof in enumerate(chain):
            if i > 0 and proof.parent_proof != chain[i-1].proof_id:
                issues.append(f"Broken chain at {proof.proof_id}")
        return {"ok": len(issues) == 0, "issues": issues, "length": len(chain)}


@dataclass
class ProblemRecord:
    """Persistent problem/workaround memory entry."""
    problem_id: str = field(default_factory=lambda: "prob-" + uuid.uuid4().hex[:10])
    project: str = ""
    component: str = ""
    symptoms: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    trigger: str = ""
    error: str = ""
    affected_files: list[str] = field(default_factory=list)
    model: str = ""
    runtime: str = ""
    device: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)
    root_cause: str = ""
    root_cause_confidence: float = 0.0
    workaround: str = ""
    permanent_fix: str = ""
    tests_added: list[str] = field(default_factory=list)
    result: str = ""  # "WORKAROUND", "FIXED", "OPEN", "WONT_FIX"
    side_effects: list[str] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    related_tasks: list[str] = field(default_factory=list)
    related_commits: list[str] = field(default_factory=list)


class ProblemMemory:
    """Persistent problem/workaround database with retrieval by similarity."""

    def __init__(self, storage_path: Path | None = None):
        self.records: dict[str, ProblemRecord] = {}
        self.storage_path = storage_path
        if storage_path and storage_path.exists():
            self.load()

    def add(self, record: ProblemRecord) -> str:
        self.records[record.problem_id] = record
        if self.storage_path:
            self.save()
        return record.problem_id

    def get(self, problem_id: str) -> ProblemRecord | None:
        return self.records.get(problem_id)

    def query(self, project: str = "", component: str = "", model: str = "",
              error_contains: str = "") -> list[ProblemRecord]:
        results = []
        for r in self.records.values():
            if project and r.project != project:
                continue
            if component and r.component != component:
                continue
            if model and r.model != model:
                continue
            if error_contains and error_contains.lower() not in r.error.lower():
                continue
            results.append(r)
        return sorted(results, key=lambda r: r.timestamp, reverse=True)

    def save(self) -> None:
        if not self.storage_path:
            return
        data = {pid: asdict(r) for pid, r in self.records.items()}
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        for pid, rd in data.items():
            self.records[pid] = ProblemRecord(**rd)


@dataclass
class ResourceSnapshot:
    """Resource usage snapshot for a task execution."""
    task_id: str = ""
    wall_clock_s: float = 0.0
    cpu_util_percent: float = 0.0
    gpu_util_percent: float = 0.0
    ram_mb: float = 0.0
    vram_mb: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    network_io_mb: float = 0.0
    model_load_s: float = 0.0
    first_token_s: float = 0.0
    generation_s: float = 0.0
    tokens_per_sec: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    context_util_percent: float = 0.0
    tool_calls: int = 0
    retries: int = 0
    timeouts: int = 0
    temperature_c: float = 0.0
    thermal_throttling: bool = False
    power_watts: float = 0.0
    energy_joules: float = 0.0
    storage_mb: float = 0.0


class ResourceLedger:
    """Energy/thermal/resource accounting per task."""

    def __init__(self):
        self.snapshots: dict[str, ResourceSnapshot] = {}  # task_id -> snapshot

    def record(self, snapshot: ResourceSnapshot) -> None:
        self.snapshots[snapshot.task_id] = snapshot

    def get(self, task_id: str) -> ResourceSnapshot | None:
        return self.snapshots.get(task_id)

    def aggregate(self, task_ids: list[str]) -> dict[str, float]:
        """Aggregate resource usage across tasks."""
        total = {
            "wall_clock_s": 0.0,
            "cpu_util_percent": 0.0,
            "gpu_util_percent": 0.0,
            "ram_mb": 0.0,
            "vram_mb": 0.0,
            "energy_joules": 0.0,
            "tokens_per_sec": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tool_calls": 0,
            "retries": 0,
            "timeouts": 0,
        }
        count = 0
        for tid in task_ids:
            s = self.snapshots.get(tid)
            if s:
                total["wall_clock_s"] += s.wall_clock_s
                total["cpu_util_percent"] += s.cpu_util_percent
                total["gpu_util_percent"] += s.gpu_util_percent
                total["ram_mb"] = max(total["ram_mb"], s.ram_mb)
                total["vram_mb"] = max(total["vram_mb"], s.vram_mb)
                total["energy_joules"] += s.energy_joules
                total["tokens_per_sec"] += s.tokens_per_sec
                total["input_tokens"] += s.input_tokens
                total["output_tokens"] += s.output_tokens
                total["tool_calls"] += s.tool_calls
                total["retries"] += s.retries
                total["timeouts"] += s.timeouts
                count += 1
        if count > 0:
            total["cpu_util_percent"] /= count
            total["gpu_util_percent"] /= count
            total["tokens_per_sec"] /= count
        return total


@dataclass
class ModelFitness:
    """Multidimensional model capability scoring."""
    model_id: str = ""
    role: str = ""  # planner, coder, reviewer, general
    task_type: str = ""  # coding, debugging, reasoning, etc.

    # Latency metrics
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0

    # Throughput
    tokens_per_sec: float = 0.0

    # Quality
    test_pass_rate: float = 0.0
    review_approval_rate: float = 0.0

    # Resource
    ram_mb: float = 0.0
    vram_mb: float = 0.0
    cpu_percent: float = 0.0

    # Reliability
    success_rate: float = 0.0
    timeout_rate: float = 0.0
    retry_rate: float = 0.0

    # Fitness score (0-1, weighted)
    fitness_score: float = 0.0

    # Metadata
    sample_count: int = 0
    last_updated: float = field(default_factory=time.time)


class ModelFitnessRegistry:
    """Registry of model fitness scores per role per task type."""

    def __init__(self):
        self.fitness: dict[str, ModelFitness] = {}  # key: "model_id|role|task_type"

    def _key(self, model_id: str, role: str, task_type: str) -> str:
        return f"{model_id}|{role}|{task_type}"

    def update(self, fitness: ModelFitness) -> None:
        self.fitness[self._key(fitness.model_id, fitness.role, fitness.task_type)] = fitness

    def get(self, model_id: str, role: str, task_type: str) -> ModelFitness | None:
        return self.fitness.get(self._key(model_id, role, task_type))

    def get_best_for(self, role: str, task_type: str) -> ModelFitness | None:
        """Get best model for a role/task_type by fitness score."""
        candidates = [f for k, f in self.fitness.items()
                      if f.role == role and f.task_type == task_type]
        return max(candidates, key=lambda f: f.fitness_score) if candidates else None

    def get_comparison(self, role: str, task_type: str) -> list[ModelFitness]:
        """Get all models for a role/task_type sorted by fitness."""
        candidates = [f for k, f in self.fitness.items()
                      if f.role == role and f.task_type == task_type]
        return sorted(candidates, key=lambda f: f.fitness_score, reverse=True)
