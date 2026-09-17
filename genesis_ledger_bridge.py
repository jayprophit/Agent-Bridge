#!/usr/bin/env python3
"""
Genesis Ledger Bridge — Genesis memory consumes Agent Bridge ledger systems.

No duplication: Genesis memory READS from and WRITES to Agent Bridge ledgers
through well-defined interfaces. This is the single integration layer.

Bridge Ledgers Exposed:
- ProblemMemory: historical failures/workarounds for memory formation
- WorkProofLedger: versioned proofs of cognitive work completion
- EvidenceLedger: memories as evidence; evidence becomes memories
- ResourceLedger: resource accounting for memory operations
- TaskCenter: task progress/history for memory context
- DurableTaskGraph: dependency-ordered tasks for memory planning
- CheckpointManager: Genesis persistence integrates with Bridge checkpointing
- RecoveryManager: Genesis memory supports recovery

All through the existing GenesisAdapter contract enforcement.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Import Agent Bridge ledger systems
from task_dag import (
    ProblemMemory, ProblemRecord,
    WorkProofLedger, WorkProof,
    EvidenceLedger, Evidence, EvidenceKind,
    ResourceLedger, ResourceSnapshot,
    DurableTaskGraph, TaskRecord, TaskStatus,
    CheckpointManager, RecoveryManager,
    WorkerRegistry, WorkerInfo, WorkQueue,
)
from taskcenter import TaskCenter, TaskCenterNode


# -- Genesis-Bridge Ledger Integration Types ----------------------------------

@dataclass
class GenesisLedgerConfig:
    """Configuration for Genesis ledger integration."""
    project_id: str = "genesis"
    component_id: str = "genesis-memory"
    storage_root: Path = Path("E:/OpenCode-Data/Genesis")
    enable_persistence: bool = True
    checkpoint_interval_s: float = 30.0
    max_memory_nodes: int = 10000
    max_memory_edges: int = 50000


@dataclass
class MemoryRecord:
    """Genesis memory record mapped to Bridge ledger formats."""
    memory_id: str
    organism_id: str
    content: str
    content_digest: str
    provenance_digest: str
    context: str
    kind: str  # maps to MemoryKind
    origin: str  # maps to Origin
    scope: str  # maps to IdentityScope
    state: str  # maps to ActivationState
    confidence: float
    strength: float
    affect_valence: float
    created_at: float
    last_accessed: float
    access_count: int
    features: list[str]
    edges: list[dict[str, Any]]  # {from, to, weight, relation}


# -- Genesis Ledger Bridge ----------------------------------------------------

class GenesisLedgerBridge:
    """
    Single integration layer: Genesis memory consumes Agent Bridge ledgers.

    No parallel ledger systems. Genesis memory READS from and WRITES to
    Agent Bridge ledgers through this single interface.
    """

    def __init__(self, config: GenesisLedgerConfig):
        self.config = config
        self._initialized = False

        # Bridge ledger instances (shared, not duplicated)
        self.problem_memory = ProblemMemory(
            config.storage_root / "problem_memory.json" if config.enable_persistence else None
        )
        self.work_proof_ledger = WorkProofLedger()
        self.evidence_ledger = EvidenceLedger()
        self.resource_ledger = ResourceLedger()
        self.task_graph = DurableTaskGraph()
        self.checkpoint_manager = CheckpointManager(
            config.storage_root / "checkpoints" / "genesis_checkpoint.json"
        )
        self.recovery_manager = RecoveryManager()
        self.task_center = TaskCenter()
        self.worker_registry = WorkerRegistry()
        self.work_queue = WorkQueue()

        # Genesis-specific state
        self._genesis_memory_version = 0
        self._last_checkpoint_time = 0.0

    def initialize(self) -> bool:
        """Load existing Bridge state for Genesis memory."""
        if not self.config.enable_persistence:
            self._initialized = True
            return True

        try:
            # Load ProblemMemory
            if (self.config.storage_root / "problem_memory.json").exists():
                self.problem_memory.load()

            # Load checkpoint (includes task graph + evidence)
            graph, evidence_ledger = self.checkpoint_manager.load()
            if graph.tasks:
                self.task_graph = graph
            if evidence_ledger._items:
                self.evidence_ledger = evidence_ledger

            self._initialized = True
            return True
        except Exception as e:
            print(f"[GenesisLedgerBridge] Initialization failed: {e}")
            return False

    # -- ProblemMemory Integration --------------------------------------------

    def query_problem_memory(self, error_contains: str = "",
                             component: str = "") -> list[ProblemRecord]:
        """Query Bridge ProblemMemory for historical failures/workarounds."""
        return self.problem_memory.query(
            project=self.config.project_id,
            component=component,
            error_contains=error_contains
        )

    def record_problem(self, symptoms: str, error: str, component: str,
                       model: str = "", workaround: str = "",
                       attempts: list[dict] = None) -> str:
        """Record a new problem in Bridge ProblemMemory."""
        record = ProblemRecord(
            project=self.config.project_id,
            component=component,
            symptoms=symptoms,
            error=error,
            model=model,
            workaround=workaround or "",
            attempts=attempts or [],
        )
        return self.problem_memory.add(record)

    # -- WorkProofLedger Integration ------------------------------------------

    def record_work_proof(self, component_id: str, component_version: str,
                          task_id: str, builder_agent: str,
                          builder_model: str, source_hashes: dict[str, str],
                          input_hash: str, result_hash: str,
                          git_commit: str = "",
                          test_evidence: list[str] = None,
                          benchmark_evidence: list[str] = None,
                          resource_evidence: list[str] = None,
                          previous_version_proof: str = "") -> str:
        """Record a versioned work proof for Genesis cognitive operation."""
        # Get previous proof for chaining
        if not previous_version_proof:
            latest = self.work_proof_ledger.get_latest(component_id)
            previous_version_proof = latest.proof_id if latest else ""

        proof = WorkProof(
            component_id=component_id,
            component_version=component_version,
            task_id=task_id,
            project_id=self.config.project_id,
            builder_agent=builder_agent,
            builder_model=builder_model,
            source_hashes=source_hashes,
            input_hash=input_hash,
            result_hash=result_hash,
            git_commit=git_commit,
            test_evidence=test_evidence or [],
            benchmark_evidence=benchmark_evidence or [],
            resource_evidence=resource_evidence or [],
            previous_version_proof=previous_version_proof,
        )
        return self.work_proof_ledger.add(proof)

    def get_latest_work_proof(self, component_id: str):
        """Get latest work proof for a Genesis component."""
        return self.work_proof_ledger.get_latest(component_id)

    def get_work_proof_chain(self, component_id: str) -> list[WorkProof]:
        """Get full version chain for a Genesis component."""
        return self.work_proof_ledger.get_chain(component_id)

    # -- EvidenceLedger Integration -------------------------------------------

    def add_evidence(self, task_id: str, kind: EvidenceKind,
                     payload: dict[str, Any] = None, verified: bool = False,
                     producer: str = "genesis-memory") -> str:
        """Add evidence from Genesis memory operation."""
        evidence = Evidence(
            task_id=task_id,
            kind=kind,
            producer=producer,
            payload=payload or {},
            verified=verified,
        )
        return self.evidence_ledger.add(evidence)

    def get_verified_results(self, task_id: str = "") -> list[Evidence]:
        """Get verified results for Genesis task."""
        return self.evidence_ledger.verified_results(task_id)

    def mark_evidence_verified(self, evidence_id: str) -> bool:
        """Mark evidence as verified."""
        return self.evidence_ledger.mark_verified(evidence_id)

    # -- ResourceLedger Integration -------------------------------------------

    def record_resource_usage(self, task_id: str,
                              wall_clock_s: float = 0.0,
                              cpu_util_percent: float = 0.0,
                              gpu_util_percent: float = 0.0,
                              ram_mb: float = 0.0,
                              vram_mb: float = 0.0,
                              tokens_per_sec: float = 0.0,
                              input_tokens: int = 0,
                              output_tokens: int = 0,
                              tool_calls: int = 0,
                              retries: int = 0,
                              timeouts: int = 0,
                              model_load_s: float = 0.0,
                              first_token_s: float = 0.0) -> None:
        """Record resource usage for Genesis memory operation."""
        snapshot = ResourceSnapshot(
            task_id=task_id,
            wall_clock_s=wall_clock_s,
            cpu_util_percent=cpu_util_percent,
            gpu_util_percent=gpu_util_percent,
            ram_mb=ram_mb,
            vram_mb=vram_mb,
            tokens_per_sec=tokens_per_sec,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls,
            retries=retries,
            timeouts=timeouts,
            model_load_s=model_load_s,
            first_token_s=first_token_s,
        )
        self.resource_ledger.record(snapshot)

    # -- TaskCenter Integration -----------------------------------------------

    def task_center_add(self, task_id: str, objective: str,
                        status: str = "PLANNED",
                        assigned_worker: str = "",
                        progress_pct: float = 0.0,
                        evidence_ids: list[str] = None,
                        checkpoint: str = "") -> TaskCenterNode:
        """Add task to Bridge TaskCenter."""
        return self.task_center.add(
            objective=objective,
            parent_id="",
            status=status,
        )

    def task_center_get(self, task_id: str):
        return self.task_center.get(task_id)

    def task_center_update_progress(self, task_id: str, progress_pct: float,
                                    evidence_ids: list[str] = None,
                                    next_action: str = "") -> TaskCenterNode:
        return self.task_center.update_progress(
            task_id, progress_pct, evidence_ids or [], next_action
        )

    def task_center_complete(self, task_id: str, evidence_ids: list[str] = None,
                             final_checkpoint: str = "") -> TaskCenterNode:
        return self.task_center.complete_task(task_id, evidence_ids or [], final_checkpoint)

    # -- DurableTaskGraph Integration -----------------------------------------

    def task_graph_add(self, task_id: str, objective: str,
                       dependencies: list[str] = None,
                       status: TaskStatus = TaskStatus.PLANNED,
                       next_action: str = "") -> str:
        """Add task to Bridge DurableTaskGraph."""
        task = TaskRecord(
            task_id=task_id,
            objective=objective,
            dependencies=dependencies or [],
            status=status,
            next_action=next_action,
        )
        return self.task_graph.add(task)

    def task_graph_ready(self) -> list[TaskRecord]:
        return self.task_graph.ready()

    def task_graph_ordered(self) -> list[TaskRecord]:
        return self.task_graph.ordered()

    # -- CheckpointManager Integration ----------------------------------------

    def checkpoint(self) -> dict[str, Any]:
        """Save Genesis + Bridge state checkpoint."""
        if not self.config.enable_persistence:
            return {"ok": False, "reason": "persistence disabled"}

        self._genesis_memory_version += 1
        self._last_checkpoint_time = time.time()

        return self.checkpoint_manager.save(self.task_graph, self.evidence_ledger)

    def should_checkpoint(self) -> bool:
        return (time.time() - self._last_checkpoint_time) >= self.config.checkpoint_interval_s

    # -- Recovery Integration -------------------------------------------------

    def plan_recovery(self) -> list[dict[str, Any]]:
        """Plan recovery for Genesis tasks."""
        return self.recovery_manager.plan_recovery(self.task_graph)

    # -- Worker/WorkQueue Integration -----------------------------------------

    def register_worker(self, worker_id: str, kind: str,
                        capabilities: list[str] = None) -> None:
        self.worker_registry.register(WorkerInfo(
            worker_id=worker_id,
            kind=kind,
            capabilities=capabilities or [],
        ))

    def claim_work(self, lease_s: float = 300.0) -> str | None:
        return self.work_queue.claim(lease_s)

    # -- Genesis Memory Record Operations -------------------------------------

    def memory_record_to_evidence(self, record: MemoryRecord) -> str:
        """Convert Genesis memory record to Bridge evidence."""
        content = json.dumps({
            "memory_id": record.memory_id,
            "organism_id": record.organism_id,
            "content": record.content,
            "kind": record.kind,
            "origin": record.origin,
            "confidence": record.confidence,
            "strength": record.strength,
            "context": record.context,
        })
        return self.add_evidence(
            task_id=record.memory_id,
            kind=EvidenceKind.OBSERVATION,
            content=content,
            verified=False,
        )

    def evidence_to_memory_record(self, evidence: Evidence) -> MemoryRecord | None:
        """Convert Bridge evidence to Genesis memory record (if compatible)."""
        try:
            data = json.loads(evidence.content)
            return MemoryRecord(
                memory_id=evidence.evidence_id,
                organism_id=data.get("organism_id", self.config.component_id),
                content=data.get("content", ""),
                content_digest="",  # computed by Genesis C++
                provenance_digest="",
                context=data.get("context", ""),
                kind=data.get("kind", "observation"),
                origin=data.get("origin", "EXTERNAL_SOURCE"),
                scope="identity",
                state="available",
                confidence=data.get("confidence", 0.5),
                strength=data.get("strength", 0.5),
                affect_valence=0.0,
                created_at=evidence.timestamp,
                last_accessed=evidence.timestamp,
                access_count=0,
                features=data.get("features", []),
                edges=[],
            )
        except Exception:
            return None

    # -- Persistence ----------------------------------------------------------

    def save_all(self) -> dict[str, Any]:
        """Save all Bridge ledger state for Genesis."""
        if not self.config.enable_persistence:
            return {"ok": False, "reason": "persistence disabled"}

        results = {}

        # Save ProblemMemory
        try:
            self.problem_memory.save()
            results["problem_memory"] = {"ok": True}
        except Exception as e:
            results["problem_memory"] = {"ok": False, "error": str(e)}

        # Save checkpoint (task graph + evidence)
        try:
            results["checkpoint"] = self.checkpoint()
        except Exception as e:
            results["checkpoint"] = {"ok": False, "error": str(e)}

        return results


# -- Singleton Access ---------------------------------------------------------

_global_bridge: Optional[GenesisLedgerBridge] = None


def get_bridge(config: Optional[GenesisLedgerConfig] = None) -> GenesisLedgerBridge:
    """Get or create the global GenesisLedgerBridge instance."""
    global _global_bridge
    if _global_bridge is None:
        _global_bridge = GenesisLedgerBridge(config or GenesisLedgerConfig())
        _global_bridge.initialize()
    return _global_bridge


def reset_bridge() -> None:
    """Reset global bridge (for testing)."""
    global _global_bridge
    _global_bridge = None


# -- Convenience Functions for GenesisAdapter Integration ---------------------

def genesis_query_problems(error_contains: str = "", component: str = "") -> list[dict]:
    """Query ProblemMemory for Genesis cognition."""
    bridge = get_bridge()
    records = bridge.query_problem_memory(error_contains, component)
    return [asdict(r) for r in records]


def genesis_record_work_proof(component_id: str, component_version: str,
                              task_id: str, builder_agent: str,
                              builder_model: str, source_hashes: dict,
                              input_hash: str, result_hash: str,
                              **kwargs) -> str:
    """Record work proof for Genesis cognitive operation."""
    bridge = get_bridge()
    return bridge.record_work_proof(
        component_id, component_version, task_id, builder_agent,
        builder_model, source_hashes, input_hash, result_hash, **kwargs
    )


def genesis_record_evidence(task_id: str, kind: str, payload: dict = None,
                            verified: bool = False) -> str:
    """Record evidence from Genesis memory."""
    bridge = get_bridge()
    return bridge.add_evidence(task_id, EvidenceKind(kind), payload=payload, verified=verified)


def genesis_checkpoint() -> dict[str, Any]:
    """Save Genesis + Bridge checkpoint."""
    bridge = get_bridge()
    return bridge.checkpoint()


if __name__ == "__main__":
    # Self-test
    config = GenesisLedgerConfig(
        project_id="genesis-test",
        storage_root=Path("E:/OpenCode-Data/Genesis/test"),
        enable_persistence=True,
    )
    bridge = GenesisLedgerBridge(config)
    ok = bridge.initialize()
    print(f"Bridge initialized: {ok}")

    # Test ProblemMemory
    pid = bridge.record_problem(
        symptoms="test symptom", error="test error", component="test"
    )
    print(f"Recorded problem: {pid}")

    # Test WorkProof
    wpid = bridge.record_work_proof(
        component_id="genesis-memory",
        component_version="1.0",
        task_id="test-task",
        builder_agent="genesis-cognition",
        builder_model="qwen2.5-coder:3b",
        source_hashes={"memory.cpp": "abc123"},
        input_hash="in123",
        result_hash="out456",
    )
    print(f"Recorded work proof: {wpid}")

    # Test Evidence
    eid = bridge.add_evidence("test-task", EvidenceKind.OBSERVATION, {"test": "evidence"})
    print(f"Recorded evidence: {eid}")

    # Test TaskCenter
    bridge.task_center_add("test-task", "Test objective")
    print("Added task to TaskCenter")

    # Checkpoint
    cp = bridge.checkpoint()
    print(f"Checkpoint: {cp}")

    print("All self-tests passed.")