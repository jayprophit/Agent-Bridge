"""ResourceScheduler (v0.8). Dependency/parallelism-aware work ordering.

Orders workloads respecting dependencies and write collisions; independent
workloads may run in parallel within lane budgets. Never schedules two
concurrent writers to the same file.
"""
from __future__ import annotations

from resources.descriptors import PlacementDecision, WorkloadDescriptor


class ResourceScheduler:
    """Plans execution waves for a set of workloads."""

    def order(self, workloads: list[WorkloadDescriptor]) -> list[list[WorkloadDescriptor]]:
        """Group workloads into waves. Later waves depend on earlier ones.

        Within a wave, workloads are independent and collision-free.
        """
        by_id = {w.workload_id: w for w in workloads}
        done: set[str] = set()
        remaining = list(workloads)
        waves: list[list[WorkloadDescriptor]] = []
        while remaining:
            wave: list[WorkloadDescriptor] = []
            claimed_files: set[str] = set()
            for w in list(remaining):
                if any(d not in done for d in w.depends_on if d in by_id):
                    continue
                if any(f in claimed_files for f in w.writes_files):
                    continue
                wave.append(w)
                claimed_files.update(w.writes_files)
                remaining.remove(w)
            if not wave:
                # Dependency cycle or unknown dep: serialize the rest in order.
                wave = [remaining.pop(0)]
            for w in wave:
                done.add(w.workload_id)
            waves.append(wave)
        return waves

    def parallelizable(self, workloads: list[WorkloadDescriptor]) -> bool:
        """True if more than one workload can run concurrently."""
        waves = self.order(workloads)
        return any(len(wave) > 1 for wave in waves)
