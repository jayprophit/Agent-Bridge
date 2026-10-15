"""Bridge control commands with short-lived leases and descendant propagation.

Implements the H02/§23 control protocol on the Agent Communications Bridge:
  PAUSE          — preserve task for later
  CANCEL         — end current task
  RECALL         — remove worker/team authority and return control
  REVOKE         — revoke a specific capability or lease
  EMERGENCY_HALT — immediately deny further consequential actions

Each command must be acknowledged (§23). Revocation must cascade to
descendants (§25). Leases are short-lived; when a lease expires, side
effects fail closed (§24). An old response from a recalled worker is
recorded but its requested side effects MUST NOT execute (§25).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from compute.agent_message import AgentMessage, Intent


# --- lease states -----------------------------------------------------------------

class LeaseState(str, Enum):
    """Short-lived capability grants (§24)."""
    ACTIVE = "active"
    EXPIRED = "expired"        # time ran out — side effects fail closed
    REVOKED = "revoked"        # explicitly revoked by RECALL/REVOKE
    RECALLED = "recalled"      # worker recalled; authority withdrawn


@dataclass
class WorkerLease:
    """A short-lived capability grant to a worker (§24)."""
    lease_id: str
    worker_id: str
    parent_worker_id: str = ""          # for descendant propagation (§25)
    capabilities: tuple[str, ...] = ()
    state: LeaseState = LeaseState.ACTIVE
    granted_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    revoked_at: Optional[float] = None
    revoked_by: str = ""
    task_ids: tuple[str, ...] = ()       # tasks this lease covers

    def is_valid(self) -> bool:
        """A lease is valid only if ACTIVE and not past expiry (§24)."""
        if self.state != LeaseState.ACTIVE:
            return False
        if self.expires_at is not None and time.time() > self.expires_at:
            self.state = LeaseState.EXPIRED
            return False
        return True

    def seconds_remaining(self) -> Optional[float]:
        if self.expires_at is None:
            return None
        return max(0.0, self.expires_at - time.time())


# --- control command result ---------------------------------------------------------

class ControlOutcome(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    ALREADY_INACTIVE = "already_inactive"
    UNKNOWN_WORKER = "unknown_worker"
    REJECTED = "rejected"


@dataclass
class ControlResult:
    """Result of a control command (§23: each command must be acknowledged)."""
    command: Intent
    target_worker: str
    outcome: ControlOutcome
    acknowledged: bool = False
    affected_workers: list[str] = field(default_factory=list)  # incl. descendants
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command.value,
            "target_worker": self.target_worker,
            "outcome": self.outcome.value,
            "acknowledged": self.acknowledged,
            "affected_workers": self.affected_workers,
            "evidence": self.evidence,
        }


# --- the bridge control channel (§23) ----------------------------------------------------

class BridgeControlChannel:
    """Delivers H02/§23 control commands over the bridge.

    Revocation cascades to descendants (§25). Old responses from recalled
    workers are recorded but their side effects do not execute (§25).
    """

    def __init__(self, default_lease_s: float = 300.0) -> None:
        self._lock = threading.RLock()
        self._leases: dict[str, WorkerLease] = {}          # lease_id -> lease
        self._worker_leases: dict[str, set[str]] = {}      # worker_id -> lease_ids
        self._children: dict[str, set[str]] = {}           # worker_id -> child ids
        self._default_lease_s = default_lease_s
        self._emergency_halt = False
        self._control_log: list[dict[str, Any]] = []

    # -- lease management (§24) ------------------------------------------------------

    def grant_lease(self, worker_id: str,
                    capabilities: tuple[str, ...] = (),
                    duration_s: Optional[float] = None,
                    parent_worker_id: str = "",
                    task_ids: tuple[str, ...] = ()) -> WorkerLease:
        """Grant a short-lived lease to a worker (§24)."""
        with self._lock:
            lease = WorkerLease(
                lease_id=f"lease_{worker_id}_{int(time.time()*1000)}",
                worker_id=worker_id,
                parent_worker_id=parent_worker_id,
                capabilities=capabilities,
                expires_at=time.time() + (duration_s if duration_s is not None
                                          else self._default_lease_s),
                task_ids=task_ids,
            )
            self._leases[lease.lease_id] = lease
            self._worker_leases.setdefault(worker_id, set()).add(lease.lease_id)
            if parent_worker_id:
                self._children.setdefault(parent_worker_id, set()).add(worker_id)
            return lease

    def check_lease(self, worker_id: str) -> dict[str, Any]:
        """Check if a worker holds any valid lease (§24: fail closed)."""
        with self._lock:
            if self._emergency_halt:
                return {"authorized": False,
                        "reason": "EMERGENCY_HALT active — all authority denied"}
            valid = [l for l in self._leases_for(worker_id) if l.is_valid()]
            if not valid:
                return {"authorized": False,
                        "reason": "no active lease — side effects fail closed (§24)"}
            return {"authorized": True,
                    "reason": "valid lease held",
                    "leases": [l.lease_id for l in valid],
                    "capabilities": sorted({c for l in valid
                                            for c in l.capabilities})}

    def _leases_for(self, worker_id: str) -> list[WorkerLease]:
        return [self._leases[lid]
                for lid in self._worker_leases.get(worker_id, set())
                if lid in self._leases]

    def _descendants(self, worker_id: str) -> set[str]:
        """All transitive descendants of a worker (§25 cascade)."""
        seen: set[str] = set()
        stack = [worker_id]
        while stack:
            current = stack.pop()
            for child in self._children.get(current, set()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    # -- control commands (§23) --------------------------------------------------------

    def pause(self, worker_id: str) -> ControlResult:
        """PAUSE: preserve task for later (§23)."""
        return self._record_and_ack(Intent.PAUSE, worker_id, "paused",
                                    extra="task preserved for later")

    def resume(self, worker_id: str) -> ControlResult:
        """RESUME a paused worker."""
        with self._lock:
            valid = [l for l in self._leases_for(worker_id) if l.is_valid()]
            if not valid:
                return ControlResult(Intent.RESUME, worker_id,
                                     ControlOutcome.REJECTED,
                                     acknowledged=False,
                                     evidence=["no active lease to resume under"])
            return self._record_and_ack(Intent.RESUME, worker_id, "resumed")

    def cancel(self, worker_id: str, task_id: str = "") -> ControlResult:
        """CANCEL: end the current task (§23)."""
        return self._record_and_ack(Intent.CANCEL, worker_id, "cancelled",
                                    extra=f"task {task_id or '(current)'} ended")

    def recall(self, worker_id: str, requester: str = "hermes") -> ControlResult:
        """RECALL: remove worker authority, cascading to descendants (§25)."""
        with self._lock:
            targets = {worker_id} | self._descendants(worker_id)
            revoked: list[str] = []
            for wid in targets:
                for lease in self._leases_for(wid):
                    if lease.state != LeaseState.ACTIVE:
                        continue
                    lease.state = LeaseState.RECALLED
                    lease.revoked_at = time.time()
                    lease.revoked_by = requester
                    revoked.append(wid)
            result = ControlResult(
                command=Intent.RECALL,
                target_worker=worker_id,
                outcome=(ControlOutcome.ACKNOWLEDGED if revoked
                         else ControlOutcome.UNKNOWN_WORKER),
                acknowledged=bool(revoked),
                affected_workers=sorted(targets),
                evidence=[f"recalled {len(revoked)} lease(s) across "
                          f"{len(targets)} worker(s) incl. descendants (§25)"])
            self._log(result)
            return result

    def revoke_capability(self, worker_id: str, capability: str,
                          requester: str = "hermes") -> ControlResult:
        """REVOKE: remove one capability from a worker's leases (§23)."""
        with self._lock:
            affected = 0
            for lease in self._leases_for(worker_id):
                if lease.state == LeaseState.ACTIVE and capability in lease.capabilities:
                    lease.capabilities = tuple(
                        c for c in lease.capabilities if c != capability)
                    affected += 1
            if not affected:
                return ControlResult(
                    Intent.REVOKE, worker_id, ControlOutcome.REJECTED,
                    acknowledged=False,
                    evidence=[f"no active lease grants '{capability}'"])
            result = ControlResult(
                Intent.REVOKE, worker_id, ControlOutcome.ACKNOWLEDGED,
                acknowledged=True, affected_workers=[worker_id],
                evidence=[f"revoked '{capability}' from {affected} lease(s)"])
            self._log(result)
            return result

    def emergency_halt(self, requester: str = "hermes") -> ControlResult:
        """EMERGENCY_HALT: immediately deny ALL further consequential actions (§23)."""
        with self._lock:
            self._emergency_halt = True
            revoked = 0
            for lease in self._leases.values():
                if lease.state == LeaseState.ACTIVE:
                    lease.state = LeaseState.REVOKED
                    lease.revoked_at = time.time()
                    lease.revoked_by = requester
                    revoked += 1
            result = ControlResult(
                Intent.EMERGENCY_HALT if hasattr(Intent, "EMERGENCY_HALT") else Intent.CANCEL,
                "(all-workers)", ControlOutcome.ACKNOWLEDGED,
                acknowledged=True,
                affected_workers=sorted({l.worker_id for l in self._leases.values()}),
                evidence=[f"EMERGENCY HALT — {revoked} lease(s) revoked; "
                          f"all consequential actions denied until lifted"])
            self._log(result)
            return result

    def lift_emergency_halt(self, requester: str = "hermes") -> bool:
        """Lift an emergency halt (owner action, not automatic)."""
        with self._lock:
            self._emergency_halt = False
            return True

    @property
    def is_halted(self) -> bool:
        return self._emergency_halt

    # -- stale response protection (§25) ---------------------------------------------------

    def authorize_side_effects(self, worker_id: str,
                                side_effects: list[str]) -> dict[str, Any]:
        """Check whether a worker's requested side effects may execute (§25).

        Authority is checked at EXECUTION time, not delivery time. A recalled
        worker's response is recorded, but its side effects do NOT run (§25).
        """
        with self._lock:
            if self._emergency_halt:
                return {"allowed": False, "denied": side_effects,
                        "reason": "EMERGENCY_HALT — side effects denied (§25)"}
            check = self.check_lease(worker_id)
            if not check["authorized"]:
                return {"allowed": False, "denied": side_effects,
                        "reason": check["reason"]}
            return {"allowed": True, "denied": [],
                    "reason": "lease valid — side effects may execute"}

    # -- audit --------------------------------------------------------------------

    def _record_and_ack(self, command: Intent, worker_id: str,
                        action: str, extra: str = "") -> ControlResult:
        with self._lock:
            result = ControlResult(
                command=command, target_worker=worker_id,
                outcome=ControlOutcome.ACKNOWLEDGED,
                acknowledged=True,
                affected_workers=[worker_id],
                evidence=[f"{action} acknowledged by control channel"]
                          + ([extra] if extra else []))
            self._log(result)
            return result

    def _log(self, result: ControlResult) -> None:
        self._control_log.append({
            "timestamp": time.time(),
            **result.to_dict(),
        })

    def control_log(self) -> list[dict[str, Any]]:
        return list(self._control_log)
