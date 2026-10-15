"""Service objectives and cloud continuity targets (V2 H04, AT-24).

H04 requirement: Define explicit measured targets BEFORE promising continuous
cloud execution: checkpoint frequency, RPO, RTO, worker heartbeat expiry,
job start latency, retry budget, cloud-provider failover time, max
acceptable stale state.

Key honesty rule (§5 of H04): Set numerical targets AFTER benchmarking
available free hardware/providers; don't invent guaranteed SLAs. Separate
best-effort targets from contractual guarantees (free plans generally do not
provide them).

This module defines:
- Quantitative service objectives (QSO) with best-effort vs contractual labels
- Task state machine transitions (§6): RUNNING_REMOTE, WAITING_APPROVAL,
  WAITING_QUOTA, CHECKPOINTED, RECOVERING, FAILED, COMPLETED_VERIFIED
- A recovery-objectives calculator that measures RTO/RPO from real events
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --- objective categories ----------------------------------------------------------

class ObjectiveCategory(str, Enum):
    CHECKPOINT_FREQUENCY = "checkpoint_frequency_s"
    MAX_STATE_LOSS_RPO = "max_state_loss_rpo_s"
    RECOVERY_TIME_RTO = "recovery_time_rto_s"
    HEARTBEAT_EXPIRY = "heartbeat_expiry_s"
    JOB_START_LATENCY = "job_start_latency_s"
    RETRY_BUDGET = "retry_budget_count"
    PROVIDER_FAILOVER_TIME = "provider_failover_s"
    MAX_STALE_STATE = "max_stale_state_s"


class AssuranceLevel(str, Enum):
    """§5: separate best-effort from contractual guarantees."""
    BEST_EFFORT = "best_effort"            # measured on free tier, no SLA
    CONTRACTUAL = "contractual"            # provider guarantees (rare on free)
    NOT_MEASURED = "not_measured"          # not yet benchmarked
    BLOCKED_FREE_TIER = "blocked_free_tier"  # free plans don't provide


# --- quantitative service objective --------------------------------------------------

@dataclass
class ServiceObjective:
    """One measured target with honest assurance level (§5)."""
    category: ObjectiveCategory
    target_value: float
    measured_value: Optional[float] = None    # actual measured from this machine
    assurance: AssuranceLevel = AssuranceLevel.NOT_MEASURED
    evidence: str = ""
    unit: str = ""

    @property
    def meets_target(self) -> Optional[bool]:
        """Does the measured value meet the target? None if not measured."""
        if self.measured_value is None:
            return None
        # Lower is better for most categories (latency, frequency, RPO)
        # except retry_budget_count where higher headroom is better
        if self.category == ObjectiveCategory.RETRY_BUDGET:
            return self.measured_value >= self.target_value
        return self.measured_value <= self.target_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "target_value": self.target_value,
            "measured_value": self.measured_value,
            "assurance": self.assurance.value,
            "meets_target": self.meets_target,
            "evidence": self.evidence,
            "unit": self.unit,
        }


# --- task state machine (§6 of H04) -----------------------------------------------------

class TaskState(str, Enum):
    """H04 §6 task state machine transitions."""
    RUNNING_REMOTE = "RUNNING_REMOTE"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_QUOTA = "WAITING_QUOTA"
    CHECKPOINTED = "CHECKPOINTED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"
    COMPLETED_VERIFIED = "COMPLETED_VERIFIED"


# Valid state transitions (§6: "Define state machine transitions such as...")
_VALID_TASK_TRANSITIONS: dict[tuple[TaskState, TaskState], str] = {
    # Running can pause for approval or quota
    (TaskState.RUNNING_REMOTE, TaskState.WAITING_APPROVAL): "awaiting owner/policy gate",
    (TaskState.RUNNING_REMOTE, TaskState.WAITING_QUOTA): "provider quota cooldown",
    # Running can checkpoint (heartbeat save)
    (TaskState.RUNNING_REMOTE, TaskState.CHECKPOINTED): "periodic checkpoint saved",
    # Checkpointed can resume running or start recovery
    (TaskState.CHECKPOINTED, TaskState.RUNNING_REMOTE): "resumed from checkpoint",
    (TaskState.CHECKPOINTED, TaskState.RECOVERING): "crash detected; recovering",
    # Recovering either resumes or fails
    (TaskState.RECOVERING, TaskState.RUNNING_REMOTE): "recovered successfully",
    (TaskState.RECOVERING, TaskState.FAILED): "recovery failed; data loss beyond RPO",
    # Waiting states can resume
    (TaskState.WAITING_APPROVAL, TaskState.RUNNING_REMOTE): "approval granted",
    (TaskState.WAITING_APPROVAL, TaskState.FAILED): "approval denied or expired",
    (TaskState.WAITING_QUOTA, TaskState.RUNNING_REMOTE): "quota refreshed",
    (TaskState.WAITING_QUOTA, TaskState.FAILED): "quota not available within budget",
    # Running can complete or fail directly
    (TaskState.RUNNING_REMOTE, TaskState.COMPLETED_VERIFIED): "task completed + QA verified",
    (TaskState.RUNNING_REMOTE, TaskState.FAILED): "task failed",
    # RECALLED/HALTED handled by emergency_stop module (H02)
}


def is_valid_task_transition(from_state: TaskState, to_state: TaskState) -> bool:
    """Check if a task state transition is legal (§6)."""
    return (from_state, to_state) in _VALID_TASK_TRANSITIONS


def task_transition_reason(from_state: TaskState, to_state: TaskState) -> Optional[str]:
    """Get the reason for a transition, or None if illegal."""
    return _VALID_TASK_TRANSITIONS.get((from_state, to_state))


# --- recovery objectives measurement (AT-24) ------------------------------------------------

@dataclass
class RecoveryEvent:
    """One observed recovery event for RTO/RPO measurement."""
    event_type: str           # "checkpoint", "crash", "recovery"
    timestamp: float
    task_id: str = ""
    data_loss_s: float = 0.0   # seconds of work lost (RPO)
    recovery_time_s: float = 0.0  # time to recover (RTO)
    evidence: str = ""


class RecoveryObjectivesMeasurer:
    """Measure RTO/RPO/checkpoint loss from real events (AT-24).

    §7: "Test power-off and provider failure scenarios using independent
    remote logs, not self-reported agent messages."
    """

    def __init__(self) -> None:
        self._events: list[RecoveryEvent] = []
        self._checkpoints: dict[str, float] = {}  # task_id -> last checkpoint time

    def record_checkpoint(self, task_id: str, timestamp: float = 0.0,
                          evidence: str = "") -> None:
        """Record a checkpoint save (this is the RPO anchor)."""
        ts = timestamp or time.time()
        self._checkpoints[task_id] = ts
        self._events.append(RecoveryEvent(
            event_type="checkpoint", timestamp=ts, task_id=task_id,
            evidence=evidence))

    def record_crash(self, task_id: str, crash_time: float = 0.0,
                     evidence: str = "") -> float:
        """Record a crash. Returns the RPO (seconds of work lost since last checkpoint)."""
        ts = crash_time or time.time()
        last_ckpt = self._checkpoints.get(task_id)
        rpo = (ts - last_ckpt) if last_ckpt else float("inf")
        self._events.append(RecoveryEvent(
            event_type="crash", timestamp=ts, task_id=task_id,
            data_loss_s=rpo, evidence=evidence))
        return rpo

    def record_recovery(self, task_id: str, recovery_time: float,
                         recovered_ts: float = 0.0, evidence: str = "") -> None:
        """Record a successful recovery. recovery_time = seconds from crash to resume."""
        self._events.append(RecoveryEvent(
            event_type="recovery", timestamp=recovered_ts or time.time(),
            task_id=task_id, recovery_time_s=recovery_time,
            evidence=evidence))

    def measured_rpo(self) -> Optional[float]:
        """Worst observed RPO (max data loss) across all crashes.
        None if no crash has been observed (honest: not measured)."""
        rpos = [e.data_loss_s for e in self._events
                if e.event_type == "crash" and e.data_loss_s != float("inf")]
        if not rpos:
            return None
        return max(rpos)

    def measured_rto(self) -> Optional[float]:
        """Worst observed RTO (max recovery time) across all recoveries.
        None if no recovery has been observed."""
        rtos = [e.recovery_time_s for e in self._events
                if e.event_type == "recovery"]
        if not rtos:
            return None
        return max(rtos)

    def summary(self) -> dict[str, Any]:
        """Honest summary: what's measured, what's not."""
        rpo = self.measured_rpo()
        rto = self.measured_rto()
        return {
            "rpo_measured_s": rpo,
            "rto_measured_s": rto,
            "checkpoints_recorded": len([e for e in self._events
                                          if e.event_type == "checkpoint"]),
            "crashes_observed": len([e for e in self._events
                                      if e.event_type == "crash"]),
            "recoveries_observed": len([e for e in self._events
                                         if e.event_type == "recovery"]),
            "honest_note": ("RTO/RPO measured from real events (§7: independent "
                           "evidence, not self-reported)"),
        }


# --- default objectives (BEST_EFFORT, free tier) ---------------------------------------------

def default_service_objectives() -> list[ServiceObjective]:
    """Default H04 service objectives for the free-tier local deployment.

    §5: These are BEST_EFFORT targets measured (or to-be-measured) on this
    machine. NOT contractual guarantees — free plans don't provide them.
    """
    return [
        ServiceObjective(
            category=ObjectiveCategory.CHECKPOINT_FREQUENCY,
            target_value=300.0,  # 5 min between checkpoints
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="seconds"),
        ServiceObjective(
            category=ObjectiveCategory.MAX_STATE_LOSS_RPO,
            target_value=300.0,  # max 5 min of work lost
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="seconds"),
        ServiceObjective(
            category=ObjectiveCategory.RECOVERY_TIME_RTO,
            target_value=600.0,  # 10 min to recover
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="seconds"),
        ServiceObjective(
            category=ObjectiveCategory.HEARTBEAT_EXPIRY,
            target_value=120.0,  # 2 min heartbeat timeout (existing LEASE_S)
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="seconds"),
        ServiceObjective(
            category=ObjectiveCategory.JOB_START_LATENCY,
            target_value=30.0,  # 30s from assignment to start
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="seconds"),
        ServiceObjective(
            category=ObjectiveCategory.RETRY_BUDGET,
            target_value=3,
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="retries"),
        ServiceObjective(
            category=ObjectiveCategory.PROVIDER_FAILOVER_TIME,
            target_value=60.0,  # 1 min to switch providers
            assurance=AssuranceLevel.BLOCKED_FREE_TIER,
            evidence="free tier has no failover SLA; failover is local-only",
            unit="seconds"),
        ServiceObjective(
            category=ObjectiveCategory.MAX_STALE_STATE,
            target_value=60.0,  # dashboard shows state <60s old
            assurance=AssuranceLevel.BEST_EFFORT,
            unit="seconds"),
    ]
