"""AdaptiveBalancer (v0.8). Evidence-weighted workload placement.

Score factors (all configurable via weights): compatibility, measured
benchmark performance, current pressure, latency, energy/power, memory cost,
reliability, task priority, owner preference. Benchmark evidence is used
where available; capability always outranks speed (a fast model that emits
malformed actions must not beat a slower reliable one).
"""
from __future__ import annotations

from typing import Any

from resources.descriptors import (
    CPU_COMPUTE, GPU_COMPUTE, LANE_BACKGROUND, LANE_BALANCED,
    PlacementDecision, PressureState, WorkloadDescriptor,
)
from resources.monitor import LANE_RESERVE
from resources.pool import ResourcePool

DEFAULT_WEIGHTS = {
    "compatibility": 30.0,
    "benchmark": 20.0,
    "pressure": 15.0,
    "latency": 8.0,
    "energy": 5.0,
    "memory": 7.0,
    "reliability": 25.0,
    "priority": 10.0,
    "owner_preference": 12.0,
}


class AdaptiveBalancer:
    """Places workloads onto pool resources with transparent scoring."""

    def __init__(self, pool: ResourcePool,
                 weights: dict[str, float] | None = None,
                 benchmark_summary=None,
                 owner_preferences: dict[str, Any] | None = None):
        self.pool = pool
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self.benchmark_summary = benchmark_summary
        self.owner_preferences = dict(owner_preferences or {})

    def place(self, workload: WorkloadDescriptor,
              pressure: PressureState | None = None,
              lane: str = "") -> PlacementDecision:
        """Place one workload. Never places onto an incompatible resource."""
        lane = lane or workload.lane or LANE_BALANCED
        candidates = self.pool.compatible(workload)
        if not candidates:
            return PlacementDecision(
                workload_id=workload.workload_id, resource_id="",
                lane=lane, reasons=["no compatible resource"],
                deferred=True)
        scored = [(self._score(workload, r, pressure, lane), r) for r in candidates]
        scored.sort(key=lambda kv: -kv[0][0])
        (total, parts), best = scored[0]
        fallbacks = [r.resource_id for _, r in scored[1:3]]
        return PlacementDecision(
            workload_id=workload.workload_id, resource_id=best.resource_id,
            lane=lane, reasons=parts, score=round(total, 2),
            fallback_resource_ids=fallbacks,
            benchmark_evidence_used=any("benchmark" in p for p in parts))

    def _score(self, workload: WorkloadDescriptor, resource,
               pressure: PressureState | None,
               lane: str) -> tuple[float, list[str]]:
        w = self.weights
        total, parts = 0.0, []
        # Compatibility (gate already passed; reward native fit).
        total += w["compatibility"]
        parts.append(f"compatible:{resource.kind}")
        # Owner preference.
        preferred = self.owner_preferences.get("preferred_resource")
        if preferred and (preferred == resource.resource_id or preferred == resource.kind):
            total += w["owner_preference"]
            parts.append("owner_preferred")
        # Priority.
        total += (workload.priority / 100.0) * w["priority"]
        # Pressure: penalize hot axes, reward cool ones; respect lane reserve.
        if pressure is not None:
            axis = {"CPU_COMPUTE": pressure.cpu, "GPU_COMPUTE": pressure.gpu,
                    "VRAM": pressure.vram, "MEMORY": pressure.ram}.get(resource.kind, 0.0)
            total += (1.0 - axis) * w["pressure"]
            reserve = LANE_RESERVE.get(lane, LANE_RESERVE[LANE_BALANCED])
            key = {"CPU_COMPUTE": "cpu", "GPU_COMPUTE": "gpu",
                   "VRAM": "vram", "MEMORY": "ram"}.get(resource.kind)
            if key and axis > 1.0 - reserve.get(key, 0.2):
                total -= w["pressure"]
                parts.append("reserve breached: penalized")
        # Benchmark evidence (reliability first, then speed).
        bench = self._benchmark_for(workload, resource)
        if bench:
            rel = bench.get("reliability")
            if rel is not None:
                total += rel * w["reliability"]
                parts.append(f"benchmark reliability={rel:.2f}")
            tps = bench.get("tokens_per_second")
            if tps:
                total += min(tps / 50.0, 1.0) * w["benchmark"]
                parts.append(f"benchmark tps={tps:.1f}")
        # Memory cost: prefer the smaller footprint under pressure.
        if workload.min_vram_mb and resource.kind == CPU_COMPUTE:
            total += w["memory"] * 0.5
            parts.append("cpu avoids vram cost")
        # Energy: NPU/GPU over CPU for inference-shaped work when cool.
        if resource.kind in (GPU_COMPUTE,) and workload.kind == "MODEL_INFERENCE":
            total += w["energy"] * 0.5
            parts.append("efficient inference lane")
        # Latency: interactive lane prefers lowest-latency resource class.
        if lane == "INTERACTIVE" and resource.kind in (GPU_COMPUTE, CPU_COMPUTE):
            total += w["latency"] * 0.5
            parts.append("interactive latency lane")
        # Background lane prefers shared, cheap resources.
        if lane == LANE_BACKGROUND and resource.shared:
            total += w["latency"] * 0.3
        return total, parts

    def _benchmark_for(self, workload, resource) -> dict[str, Any] | None:
        """Pull benchmark evidence via the injected summary (any shape)."""
        if self.benchmark_summary is None:
            return None
        try:
            getter = getattr(self.benchmark_summary, "for_workload", None)
            if callable(getter):
                return getter(workload.kind, resource.resource_id)
            getter = getattr(self.benchmark_summary, "get", None)
            if callable(getter):
                return getter(workload.kind)
        except Exception:
            return None
        return None
