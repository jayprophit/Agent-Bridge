"""Instance Registry — tracks every running model instance (§65).

Model instance != model. A single logical model may have multiple running
instances on different execution targets. Instances appear and disappear
(elastically); the registry tracks them with health, resource usage,
and lease state.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InstanceRecord:
    """A single running model instance on an execution target."""
    instance_id: str = ""
    model_id: str = ""
    model_variant: str = ""    # quantization/format, e.g. "q4_K_M"
    execution_target: str = "" # execution-target ID
    provider: str = ""
    endpoint: str = ""         # inference endpoint URL
    created_at: float = 0.0
    health: str = "UNKNOWN"    # HEALTHY | DEGRADED | OFFLINE | UNKNOWN
    current_workload: str = "" # task_id or job_id currently using this instance
    queue_depth: int = 0
    ram_used_mb: float = 0.0
    vram_used_mb: float = 0.0
    total_ram_mb: float = 0.0
    total_vram_mb: float = 0.0
    tokens_per_sec: float = 0.0
    latency_ms: float = 0.0
    cost_accumulated_usd: float = 0.0
    lease: str = ""            # lease ID this instance is bound to
    shutdown_policy: str = ""  # NEVER | ON_IDLE | ON_LEASE_EXPIRE | ON_CLOUD_PREEMPTION
    last_heartbeat: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()
        if not self.last_heartbeat:
            self.last_heartbeat = time.time()

    def is_stale(self, heartbeat_timeout_s: float = 60.0) -> bool:
        """True if no heartbeat seen within the timeout."""
        if not self.last_heartbeat:
            return True
        return (time.time() - self.last_heartbeat) > heartbeat_timeout_s

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


class InstanceRegistry:
    """ID-keyed registry of running model instances.

    Supports elastic instances that appear/disappear. The control plane
    queries this to find available instances for scheduling.
    """

    def __init__(self) -> None:
        self._instances: dict[str, InstanceRecord] = {}

    def register(self, record: InstanceRecord) -> None:
        if not record.instance_id:
            raise ValueError("instance_id must be non-empty")
        if record.instance_id in self._instances:
            raise ValueError(f"duplicate instance_id: {record.instance_id!r}")
        self._instances[record.instance_id] = record

    def get(self, instance_id: str) -> InstanceRecord:
        try:
            return self._instances[instance_id]
        except KeyError:
            raise KeyError(f"unknown instance: {instance_id!r}")

    def unregister(self, instance_id: str) -> None:
        """Remove an instance (e.g. shutdown, eviction, crash)."""
        self._instances.pop(instance_id, None)

    def update_health(self, instance_id: str, health: str) -> InstanceRecord:
        rec = self.get(instance_id)
        rec.health = health
        rec.last_heartbeat = time.time()
        return rec

    def heartbeat(self, instance_id: str) -> bool:
        rec = self.get(instance_id)
        rec.last_heartbeat = time.time()
        return True

    def available(self) -> list[InstanceRecord]:
        """Healthy, non-stale instances with available capacity."""
        return sorted(
            (r for r in self._instances.values()
             if r.health in ("HEALTHY", "DEGRADED")
             and not r.is_stale()),
            key=lambda r: r.instance_id,
        )

    def by_model(self, model_id: str) -> list[InstanceRecord]:
        return sorted(
            (r for r in self._instances.values()
             if r.model_id == model_id),
            key=lambda r: r.instance_id,
        )

    def by_target(self, target_id: str) -> list[InstanceRecord]:
        return sorted(
            (r for r in self._instances.values()
             if r.execution_target == target_id),
            key=lambda r: r.instance_id,
        )

    def free_instances(self) -> list[InstanceRecord]:
        """Instances not currently assigned to a workload."""
        return [r for r in self._instances.values()
                if not r.current_workload]

    def ids(self) -> list[str]:
        return sorted(self._instances)

    def __len__(self) -> int:
        return len(self._instances)

    def gc_stale(self, heartbeat_timeout_s: float = 60.0) -> list[str]:
        """Garbage-collect stale instances. Returns removed IDs."""
        stale = [iid for iid, rec in self._instances.items()
                 if rec.is_stale(heartbeat_timeout_s)]
        for iid in stale:
            self.unregister(iid)
        return stale

    def to_dict(self) -> dict[str, Any]:
        return {iid: r.to_dict() for iid, r in self._instances.items()}


__all__ = [
    "InstanceRecord",
    "InstanceRegistry",
]
