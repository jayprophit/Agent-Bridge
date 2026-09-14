"""Automatic agent routing + worker economics (v0.9.0 continuous build).

AUTOMATIC ROUTING IS THE DEFAULT. MANUAL SELECTION IS AN OVERRIDE.

Main AI owns objective/task-graph/integration/decision; specialists
contribute where they provide useful benefit. Worker economics decides:
one capable model beats five agents for trivial work; specialists win
when they materially improve speed or quality.

Additive only; no side effects. Native vs third-party worker kinds stay
separate (native Genesis workers are never disposable plugins).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WorkerSpec:
    worker_id: str = ""
    kind: str = "native"       # native | genesis-native | third-party | remote
    capabilities: list[str] = field(default_factory=list)
    cost_per_task: float = 1.0
    latency_s: float = 5.0
    quality: float = 0.7       # 0..1 measured or estimated
    reliability: float = 0.9   # historical success rate


@dataclass
class DelegationPlan:
    use_workers: bool = False
    workers: list[str] = field(default_factory=list)
    reason: str = ""
    estimated_gain: float = 0.0


class WorkerEconomics:
    """Decide single-model vs delegation from measured-ish inputs."""

    @staticmethod
    def evaluate(task: dict[str, Any], workers: list[WorkerSpec]) -> DelegationPlan:
        subtasks = task.get("parallel_subtasks", []) or []
        if not subtasks:
            return DelegationPlan(False, [], "no parallelisable work")
        capable = [w for w in workers if w.reliability >= 0.5]
        if not capable:
            return DelegationPlan(False, [], "no reliable workers")
        # Benefit model: parallel coverage minus coordination overhead.
        gain = len(subtasks) * 1.0 - len(capable) * 0.3 \
            - float(task.get("context_cost", 0) or 0)
        if gain <= 0.5:
            return DelegationPlan(False, [],
                                  "coordination overhead exceeds benefit",
                                  gain)
        chosen = sorted(capable, key=lambda w: (-w.quality, w.cost_per_task))
        return DelegationPlan(True, [w.worker_id for w in chosen[:len(subtasks)]],
                              "parallel specialists improve speed/quality", gain)


class AgentRouter:
    """Route tasks to workers automatically; manual choice overrides."""

    def __init__(self, workers: list[WorkerSpec] | None = None):
        self.workers: dict[str, WorkerSpec] = {w.worker_id: w for w in (workers or [])}

    def register(self, worker: WorkerSpec) -> None:
        self.workers[worker.worker_id] = worker

    def route(self, task: dict[str, Any], override: str = "") -> dict[str, Any]:
        if override:
            if override not in self.workers:
                return {"worker": "", "error": f"unknown worker: {override}"}
            return {"worker": override, "override": True}
        need = set(task.get("capabilities", []))
        scored = []
        for w in self.workers.values():
            if w.kind == "third-party" and task.get("native_only"):
                continue
            missing = need - set(w.capabilities)
            score = len(missing) * 100 + (1.0 - w.reliability) * 10 \
                + w.cost_per_task
            scored.append((score, w))
        scored.sort(key=lambda t: (t[0], t[1].worker_id))
        if not scored or scored[0][0] >= 100:
            return {"worker": "", "error": "no capable worker"}
        return {"worker": scored[0][1].worker_id, "override": False}

    def fan_out(self, task: dict[str, Any]) -> dict[str, Any]:
        plan = WorkerEconomics.evaluate(
            task, [w for w in self.workers.values() if w.kind != "third-party"
                   or not task.get("native_only")])
        routed = {}
        if plan.use_workers:
            for i, wid in enumerate(plan.workers):
                sub = dict(task.get("parallel_subtasks", [])[i]
                           if i < len(task.get("parallel_subtasks", [])) else {})
                routed[wid] = sub
        return {"plan": asdict(plan), "assignments": routed}


def integrate_results(worker_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Integrator: combine specialist outputs, collect evidence intertwined."""
    artifacts, warnings, failures, evidence = [], [], [], []
    ok = True
    for out in worker_outputs:
        artifacts.extend(out.get("artifacts", []))
        warnings.extend(out.get("warnings", []))
        failures.extend(out.get("failures", []))
        evidence.extend(out.get("evidence", []))
        if out.get("status") not in ("COMPLETE", "VERIFIED_COMPLETE"):
            ok = False
    return {"ok": ok, "artifacts": artifacts, "warnings": warnings,
            "failures": failures, "evidence": evidence}
