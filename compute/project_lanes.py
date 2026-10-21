"""§14/§15 — Work Lanes + Project Starvation Detection.

Reservation of supervisor capacity across the active project portfolio so
"fixing Hermes" cannot consume 100% of the workforce while Genesis, IDE,
MAT, Agent-Bridge, etc. sit untouched.

A lane declares (a) the minimum workers that must make *meaningful
progress* on it each cycle-window, and (b) the role/capability it needs.
The starvation detector compares each lane's last_progress_epoch against
the live clock; a lane whose work is unblocked but progress-stale beyond
its threshold is a §15 violation that the scheduler must act on.

This module is pure data + predicates (no I/O side effects) so it can be
unit-tested in isolation and imported by the runtime, the watchdog, and
the dashboard read-model.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

# default per-project stale-progress threshold (§15): 1 hour of no
# meaningful progress while unblocked work exists = starvation.
DEFAULT_STALENESS_S = 3600.0

# the portfolio of active work lanes (§14 table)
DEFAULT_LANES = [
    {"id": "supervisor_infra", "project": "Agent-Bridge",
     "min_workers": 1, "roles": ["runtime", "security"],
     "priority": "MEDIUM", "stale_threshold_s": DEFAULT_STALENESS_S},
    {"id": "aetherius_os", "project": "Aetherius OS",
     "min_workers": 1, "roles": ["architecture", "implementation"],
     "priority": "HIGH", "stale_threshold_s": DEFAULT_STALENESS_S},
    {"id": "genesis", "project": "Genesis",
     "min_workers": 1, "roles": ["research", "implementation"],
     "priority": "HIGH", "stale_threshold_s": DEFAULT_STALENESS_S},
    {"id": "ide_workspace", "project": "IDE Workspace",
     "min_workers": 2, "roles": ["implementation", "ui_ux"],
     "priority": "HIGH", "stale_threshold_s": DEFAULT_STALENESS_S},
    {"id": "mat", "project": "MAT",
     "min_workers": 1, "roles": ["implementation"],
     "priority": "MEDIUM", "stale_threshold_s": DEFAULT_STALENESS_S},
    {"id": "qa_security", "project": "cross-project",
     "min_workers": 1, "roles": ["qa", "security"],
     "priority": "HIGH", "stale_threshold_s": DEFAULT_STALENESS_S},
    {"id": "research_knowledge", "project": "Genesis",
     "min_workers": 2, "roles": ["research", "knowledge"],
     "priority": "MEDIUM", "stale_threshold_s": 1800.0},
    {"id": "devops_runtime", "project": "Agent-Bridge",
     "min_workers": 1, "roles": ["devops", "runtime"],
     "priority": "MEDIUM", "stale_threshold_s": DEFAULT_STALENESS_S},
]


@dataclass
class LaneSnapshot:
    """One project lane's observed state at a cycle."""
    lane_id: str
    project: str
    priority: str
    min_workers: int
    has_unblocked_work: bool
    active_workers: int
    last_progress_epoch: float
    stale_threshold_s: float
    roles: list[str] = field(default_factory=list)

    def is_starved(self, now: Optional[float] = None) -> bool:
        """UNBLOCKED work with NO progress for longer than the threshold."""
        now = now or time.time()
        if not self.has_unblocked_work:
            return False
        if self.active_workers >= self.min_workers:
            return False
        stale_for = now - self.last_progress_epoch
        return stale_for > self.stale_threshold_s


@dataclass
class StarvationReport:
    starved_lanes: list[dict] = field(default_factory=list)
    total_lanes: int = 0
    understaffed_lanes: int = 0       # has work but < min_workers even if not stale

    @property
    def has_starvation(self) -> bool:
        return len(self.starved_lanes) > 0


def compute_starvation(lanes: list[dict],
                       worker_project_progress: dict,
                       now: Optional[float] = None) -> StarvationReport:
    """Build the starvation report from live lane + worker data.

    ``worker_project_progress`` maps project_id -> {
        'active': int,                 # workers currently IMPLEMENTING/TESTING/...
        'has_unblocked_work': bool,
        'last_progress_epoch': float,
    }
    """
    now = now or time.time()
    report = StarvationReport(total_lanes=len(lanes))
    for lane in lanes:
        pid = lane["project"]
        wp = worker_project_progress.get(pid, {})
        has_work = bool(wp.get("has_unblocked_work", False))
        active = int(wp.get("active", 0))
        last_prog = float(wp.get("last_progress_epoch", 0.0))
        snap = LaneSnapshot(
            lane_id=lane["id"], project=pid,
            priority=lane.get("priority", "MEDIUM"),
            min_workers=lane.get("min_workers", 1),
            has_unblocked_work=has_work,
            active_workers=active,
            last_progress_epoch=last_prog,
            stale_threshold_s=lane.get("stale_threshold_s", DEFAULT_STALENESS_S),
            roles=lane.get("roles", []))
        if snap.has_unblocked_work and snap.active_workers < snap.min_workers:
            report.understaffed_lanes += 1
        if snap.is_starved(now):
            report.starved_lanes.append({
                "lane_id": snap.lane_id,
                "project": snap.project,
                "priority": snap.priority,
                "active_workers": snap.active_workers,
                "min_workers": snap.min_workers,
                "stale_for_s": round(now - snap.last_progress_epoch, 0),
                "stale_threshold_s": snap.stale_threshold_s,
                "roles_needed": snap.roles,
            })
    return report


def lane_assignments(report: StarvationReport,
                     free_worker_capacity: int) -> list[dict]:
    """Greedy assignment plan: give each starved CRITICAL/HIGH lane a worker
    first, then MEDIUM, until worker capacity is exhausted (§10 max useful
    throughput, not max process count)."""
    plan = []
    remaining = free_worker_capacity
    for lane in sorted(report.starved_lanes,
                       key=lambda l: (0 if l["priority"] == "CRITICAL" else
                                      1 if l["priority"] == "HIGH" else 2,
                                      l["lane_id"])):
        if remaining <= 0:
            break
        plan.append(lane)
        remaining -= 1
    return plan
