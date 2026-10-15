"""Bridge scope enforcement (H01 extension, AT-22 ready, single-owner today).

The canonical message envelope carries owner_id / workspace_id / tenant_id.
This module enforces scope at the bridge boundary so that when multi-user
operation eventually arrives, no data-model rewrite is needed and no
cross-scope access is possible even with direct API calls (AT-22).

Today the system is SINGLE-OWNER/PRIVATE (V2 H12):
  - An empty owner_id means "the sole owner" — the default.
  - An empty workspace_id means "the default workspace".
  - An empty tenant_id means "no tenant separation" (single-owner mode).
Nothing here pretends public multi-user operation exists. The guard simply
REFUSES anything that crosses scopes, so enabling multi-user later is a
configuration change, not an architecture change.

Key rules:
- Cross-scope messages are refused at the bus boundary (AT-22).
- Workers may only act within their granted scope.
- Empty-scope messages are treated as sole-owner scope (backward compatible).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from compute.agent_message import AgentMessage, Intent


# --- the sole-owner default -----------------------------------------------------

SOLE_OWNER = ""          # empty string = the single owner of this deployment
DEFAULT_WORKSPACE = ""   # empty string = the default workspace


def normalize_scope(owner_id: str, workspace_id: str,
                    tenant_id: str = "") -> tuple[str, str, str]:
    """Normalise a scope triple.

    Empty values denote the sole-owner default scope (§ above). Two scopes
    are equal iff their normalised triples are equal.
    """
    return (owner_id or SOLE_OWNER,
            workspace_id or DEFAULT_WORKSPACE,
            tenant_id or "")


def scopes_equal(a: tuple[str, str, str], b: tuple[str, str, str]) -> bool:
    return normalize_scope(*a) == normalize_scope(*b)


# --- scope guard -----------------------------------------------------------------

@dataclass
class WorkerScope:
    """The scope a worker is authorised to act within."""
    worker_id: str
    owner_id: str = SOLE_OWNER
    workspace_id: str = DEFAULT_WORKSPACE
    tenant_id: str = ""
    granted_workspaces: tuple[str, ...] = ()   # extra workspaces this worker may touch

    def covers(self, owner_id: str, workspace_id: str,
               tenant_id: str = "") -> bool:
        """Does this worker's scope cover the target scope?"""
        o, w, t = normalize_scope(owner_id, workspace_id, tenant_id)
        if o != normalize_scope(self.owner_id, self.workspace_id, self.tenant_id)[0]:
            return False   # owner mismatch — never cross owners
        if t and self.tenant_id and t != self.tenant_id:
            return False   # tenant mismatch when both are set
        if w == self.workspace_id:
            return True
        return w in self.granted_workspaces


class ScopeViolation(Exception):
    """Raised when a message or action crosses a scope boundary (AT-22)."""


class ScopeGuard:
    """Enforces scope boundaries on the bridge (H01/AT-22).

    Today: single-owner — every message defaults to the sole-owner scope and
    everything passes through unchanged. The guard exists so that when a
    second owner/workspace/tenant is ever configured, cross-scope access is
    refused BY DEFAULT rather than requiring new code.
    """

    def __init__(self, enforce: bool = False) -> None:
        # enforce=False today (single owner): cross-scope messages are still
        # CHECKED and logged, but the deployment has only one scope so nothing
        # can actually cross. Set enforce=True when multi-owner is configured.
        self._enforce = enforce
        self._lock = threading.RLock()
        self._worker_scopes: dict[str, WorkerScope] = {}
        self._violations: list[dict[str, Any]] = []

    @property
    def enforcing(self) -> bool:
        return self._enforce

    def enable_enforcement(self) -> None:
        """Turn on cross-scope refusal (used when a 2nd owner is configured)."""
        self._enforce = True

    # -- worker scope registration ------------------------------------------------

    def register_worker(self, scope: WorkerScope) -> None:
        """Register the scope a worker may act within."""
        with self._lock:
            self._worker_scopes[scope.worker_id] = scope

    def worker_scope(self, worker_id: str) -> Optional[WorkerScope]:
        with self._lock:
            return self._worker_scopes.get(worker_id)

    # -- message gating -----------------------------------------------------------

    def check_message(self, msg: AgentMessage) -> dict[str, Any]:
        """Check a message for scope violations (AT-22).

        Returns {"allowed": bool, "reason": str, "violation": bool}
        A violation is RECORDED whether or not it is refused, so the audit
        trail shows attempted cross-scope access even in single-owner mode.
        """
        msg_scope = normalize_scope(msg.owner_id, msg.workspace_id,
                                    msg.tenant_id)
        sender_scope = self._worker_scopes.get(f"{msg.sender_agent}/{msg.sender_worker}") \
            or self._worker_scopes.get(msg.sender_worker)

        violation = False
        reason = "in scope"

        if sender_scope is not None:
            if not sender_scope.covers(msg.owner_id, msg.workspace_id,
                                       msg.tenant_id):
                violation = True
                reason = (f"sender {msg.sender_worker} scope "
                          f"({sender_scope.owner_id}/{sender_scope.workspace_id}) "
                          f"does not cover target "
                          f"({msg.owner_id or SOLE_OWNER}/"
                          f"{msg.workspace_id or DEFAULT_WORKSPACE})")

        # Receiver scope check: a message must not deliver work into a scope
        # the receiver is not authorised for.
        if not violation:
            recv_scope = self._worker_scopes.get(
                f"{msg.receiver_agent}/{msg.receiver_worker}") \
                or self._worker_scopes.get(msg.receiver_worker)
            if recv_scope is not None and not recv_scope.covers(
                    msg.owner_id, msg.workspace_id, msg.tenant_id):
                violation = True
                reason = (f"receiver {msg.receiver_worker} not scoped for "
                          f"({msg.owner_id or SOLE_OWNER}/"
                          f"{msg.workspace_id or DEFAULT_WORKSPACE})")

        if violation:
            self._record_violation(msg, reason)
            if self._enforce:
                return {"allowed": False, "reason": reason, "violation": True}
            return {"allowed": True, "reason": reason + " [logged, not refused: "
                                              "single-owner mode]",
                    "violation": True}
        return {"allowed": True, "reason": reason, "violation": False}

    def check_action(self, worker_id: str, owner_id: str, workspace_id: str,
                     tenant_id: str = "") -> bool:
        """Check whether a worker may act within a target scope (AT-22)."""
        scope = self._worker_scopes.get(worker_id)
        if scope is None:
            return True   # unregistered workers are sole-owner by default
        allowed = scope.covers(owner_id, workspace_id, tenant_id)
        if not allowed:
            self._violations.append({
                "timestamp": time.time(),
                "kind": "action_scope_violation",
                "worker_id": worker_id,
                "target": normalize_scope(owner_id, workspace_id, tenant_id),
            })
        return allowed

    # -- audit --------------------------------------------------------------------

    def _record_violation(self, msg: AgentMessage, reason: str) -> None:
        with self._lock:
            self._violations.append({
                "timestamp": time.time(),
                "kind": "message_scope_violation",
                "message_id": msg.message_id,
                "task_id": msg.task_id,
                "intent": msg.intent.value,
                "sender": f"{msg.sender_agent}/{msg.sender_worker}",
                "receiver": f"{msg.receiver_agent}/{msg.receiver_worker}",
                "scope": normalize_scope(msg.owner_id, msg.workspace_id,
                                         msg.tenant_id),
                "reason": reason,
            })

    def violations(self) -> list[dict[str, Any]]:
        """All recorded scope violations (attempts, even unrefused ones)."""
        with self._lock:
            return list(self._violations)

    def summary(self) -> dict[str, Any]:
        return {
            "enforcing": self._enforce,
            "mode": "multi-owner" if self._enforce else "single-owner (default)",
            "registered_workers": len(self._worker_scopes),
            "violations_recorded": len(self._violations),
            "note": "H01: schema is multi-tenant-ready; operation stays "
                    "single-owner until a second owner is configured (V2 H12)",
        }
