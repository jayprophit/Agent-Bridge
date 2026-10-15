"""Emergency stop, pause, recall and credential revocation (H02, AT-21).

Maps to V2 §14 H02: global kill switch, pause, recall and emergency
credential revocation; AT-21: emergency recall of nested teams.

Design principles:
- The safety/authority layer owns enforcement. Genesis cannot overrule it.
- Four distinct actions: PAUSE (resumable), CANCEL (task-level),
  REVOKE (authority/credentials), HALT (emergency — fail closed).
- Short-lived lease tokens: disconnected workers fail closed when leases expire.
- A revocation list blocks further side effects even if stale model output arrives.
- Import-safe: no side effects, zero third-party dependencies.

Integration:
  from compute.emergency_stop import EmergencyStop, EmergencyScope, EmergencyAction

  es = EmergencyStop()
  es.halt(scope=EmergencyScope.WORKER, target="openai/codex")
  # PolicyEngine.evaluate() should call es.is_halted("openai/codex") before "allow"
  # Worker leases call es.lease_token("worker-id", ttl_s=30) before each action.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EmergencyAction(Enum):
    PAUSE = "pause"           # Graceful pause — resume later
    CANCEL = "cancel"         # Task-level cancel — current task stops, worker continues
    REVOKE = "revoke"         # Revoke authority/credentials — blocks future actions
    HALT = "halt"             # Emergency halt — fail closed immediately


class EmergencyScope(Enum):
    GENESIS = "genesis"       # Stop Genesis itself
    TEAM = "team"             # Stop a team (lead + all workers)
    WORKER = "worker"         # Stop an individual worker
    TOOL = "tool"             # Block a single tool
    PROVIDER = "provider"     # Revoke a provider account
    USER = "user"             # Target a specific user/tenant
    ALL = "all"               # Nuclear option — everything stops


@dataclass
class EmergencyEntry:
    """One active emergency stop entry in the revocation/halt list."""
    scope: EmergencyScope
    action: EmergencyAction
    target: str = ""        # worker_id, team_id, tool_name, provider_id, user_id, "" for ALL
    issued_at: float = 0.0
    issued_by: str = ""     # principal who triggered it
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    # For PAUSE/REVOKE: when the stop expires (0 = permanent until manually cleared)
    expires_at: float = 0.0
    # For HALT: if True, fail closed even after expiry until manually cleared
    hard_clear_required: bool = False

    def is_expired(self, now: float | None = None) -> bool:
        now = now or time.time()
        return self.expires_at > 0 and now >= self.expires_at


@dataclass
class EmergencyLease:
    """Short-lived lease token for a worker/subagent.

    Workers present this token before taking actions. When an emergency
    stop is active for that worker, the lease is denied. Leases also
    expire, so a disconnected worker (that stops heartbeating) fails closed.
    """
    worker_id: str
    token: str
    issued_at: float
    expires_at: float
    scopes: list[EmergencyScope] = field(default_factory=list)


class EmergencyStop:
    """Central emergency stop manager.

    NOT thread-safe by default — wrap in a lock if accessed concurrently
    (the supervisor runtime does this via its single-threaded cycle).
    """

    def __init__(self) -> None:
        # Active emergency entries: keyed by (scope, target)
        self._entries: dict[tuple[EmergencyScope, str], EmergencyEntry] = {}
        # Issued lease tokens: keyed by token string
        self._leases: dict[str, EmergencyLease] = {}
        # Audit log of all emergency actions
        self._audit_log: list[dict[str, Any]] = []

    # ── Core actions ──────────────────────────────────────────────────

    def halt(self, scope: EmergencyScope, target: str = "", *,
             issued_by: str = "", reason: str = "",
             evidence: list[str] | None = None,
             ttl_s: float = 0.0, hard_clear: bool = True) -> EmergencyEntry:
        """Trigger an emergency halt. Immediate fail-closed.

        Args:
            scope: What to stop (GENESIS, TEAM, WORKER, TOOL, PROVIDER, USER, ALL)
            target: The target id (worker_id, team_id, etc.). "" for ALL.
            ttl_s: 0 = permanent until manually cleared; >0 = auto-expire
            hard_clear: If True, requires manual deactivation even after expiry
        """
        entry = EmergencyEntry(
            scope=scope, action=EmergencyAction.HALT, target=target,
            issued_at=time.time(), issued_by=issued_by, reason=reason,
            evidence=evidence or [],
            expires_at=time.time() + ttl_s if ttl_s > 0 else 0.0,
            hard_clear_required=hard_clear,
        )
        key = (scope, target)
        self._entries[key] = entry
        self._log(entry)
        # Revoke all existing leases for this scope/target
        self._revoke_leases(scope, target)
        return entry

    def pause(self, scope: EmergencyScope, target: str = "", *,
              issued_by: str = "", reason: str = "",
              evidence: list[str] | None = None,
              ttl_s: float = 3600.0) -> EmergencyEntry:
        """Pause a worker/team/provider. Resumable — does not revoke credentials."""
        entry = EmergencyEntry(
            scope=scope, action=EmergencyAction.PAUSE, target=target,
            issued_at=time.time(), issued_by=issued_by, reason=reason,
            evidence=evidence or [],
            expires_at=time.time() + ttl_s,
            hard_clear_required=False,
        )
        key = (scope, target)
        self._entries[key] = entry
        self._log(entry)
        return entry

    def cancel(self, scope: EmergencyScope, target: str = "", *,
               issued_by: str = "", reason: str = "",
               evidence: list[str] | None = None) -> EmergencyEntry:
        """Cancel a specific task. The worker can continue other tasks."""
        entry = EmergencyEntry(
            scope=scope, action=EmergencyAction.CANCEL, target=target,
            issued_at=time.time(), issued_by=issued_by, reason=reason,
            evidence=evidence or [],
            expires_at=0.0,
            hard_clear_required=False,
        )
        key = (scope, target)
        self._entries[key] = entry
        self._log(entry)
        return entry

    def revoke(self, scope: EmergencyScope, target: str = "", *,
               issued_by: str = "", reason: str = "",
               evidence: list[str] | None = None,
               ttl_s: float = 0.0) -> EmergencyEntry:
        """Revoke authority for a target. Blocks credentials and future actions."""
        entry = EmergencyEntry(
            scope=scope, action=EmergencyAction.REVOKE, target=target,
            issued_at=time.time(), issued_by=issued_by, reason=reason,
            evidence=evidence or [],
            expires_at=time.time() + ttl_s if ttl_s > 0 else 0.0,
            hard_clear_required=True,
        )
        key = (scope, target)
        self._entries[key] = entry
        self._log(entry)
        self._revoke_leases(scope, target)
        return entry

    def deactivate(self, scope: EmergencyScope, target: str = "") -> bool:
        """Manually clear an emergency stop entry (required for hard_clear entries)."""
        key = (scope, target)
        if key in self._entries:
            entry = self._entries.pop(key)
            entry.hard_clear_required = False
            self._log(entry, action="deactivated")
            return True
        return False

    # ── Query: is something blocked? ────────────────────────────────────

    def is_halted(self, scope: EmergencyScope, target: str = "") -> bool:
        """Check if a scope+target is under emergency halt or revocation."""
        now = time.time()
        for (s, t), entry in self._entries.items():
            if s == scope and (t == target or t == "" or target == ""):
                if entry.hard_clear_required or not entry.is_expired(now):
                    if entry.action in (EmergencyAction.HALT, EmergencyAction.REVOKE):
                        return True
                    if entry.action == EmergencyAction.PAUSE:
                        return True
        # Also check ALL scope
        for (s, t), entry in self._entries.items():
            if s == EmergencyScope.ALL:
                if entry.hard_clear_required or not entry.is_expired(now):
                    return True
        return False

    def is_blocked(self, worker_id: str = "", team_id: str = "",
                   tool_name: str = "", provider_id: str = "",
                   user_id: str = "") -> bool:
        """Multi-target query: returns True if ANY applicable emergency stop is active."""
        checks = [
            (EmergencyScope.WORKER, worker_id),
            (EmergencyScope.TEAM, team_id),
            (EmergencyScope.TOOL, tool_name),
            (EmergencyScope.PROVIDER, provider_id),
            (EmergencyScope.USER, user_id),
        ]
        for scope, target in checks:
            if target and self.is_halted(scope, target):
                return True
        return self.is_halted(EmergencyScope.ALL)

    def get_revoked_capabilities(self) -> list[EmergencyEntry]:
        """Return all active revocation/halt entries (for side-effect blocking)."""
        now = time.time()
        return [e for e in self._entries.values()
                if (e.hard_clear_required or not e.is_expired(now))
                and e.action in (EmergencyAction.HALT, EmergencyAction.REVOKE, EmergencyAction.PAUSE)]

    # ── Lease tokens for remote workers ─────────────────────────────────

    def lease_token(self, worker_id: str, *, ttl_s: float = 30.0,
                    scopes: list[EmergencyScope] | None = None) -> Optional[EmergencyLease]:
        """Issue a short-lived lease token. Returns None if worker is halted."""
        if self.is_halted(EmergencyScope.WORKER, worker_id):
            return None
        token = f"el-{uuid.uuid4().hex[:12]}"
        lease = EmergencyLease(
            worker_id=worker_id, token=token,
            issued_at=time.time(), expires_at=time.time() + ttl_s,
            scopes=scopes or [],
        )
        self._leases[token] = lease
        return lease

    def validate_lease(self, token: str) -> bool:
        """Check if a lease token is valid (not expired, worker not halted)."""
        if token not in self._leases:
            return False
        lease = self._leases[token]
        now = time.time()
        if now >= lease.expires_at:
            del self._leases[token]
            return False
        # Revalidate that the worker hasn't been halted since lease was issued
        if self.is_halted(EmergencyScope.WORKER, lease.worker_id):
            return False
        return True

    def _revoke_leases(self, scope: EmergencyScope, target: str) -> None:
        """Revoke all leases for a scope+target."""
        to_remove = []
        for token, lease in self._leases.items():
            if scope == EmergencyScope.WORKER and lease.worker_id == target:
                to_remove.append(token)
            elif scope == EmergencyScope.ALL:
                to_remove.append(token)
        for token in to_remove:
            del self._leases[token]

    # ── Audit ───────────────────────────────────────────────────────────

    def _log(self, entry: EmergencyEntry, action: str = "activated") -> None:
        self._audit_log.append({
            "action": action,
            "scope": entry.scope.value,
            "target": entry.target,
            "emergency_action": entry.action.value,
            "issued_at": entry.issued_at,
            "issued_by": entry.issued_by,
            "reason": entry.reason,
            "expires_at": entry.expires_at,
            "hard_clear_required": entry.hard_clear_required,
        })

    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def active_entries(self) -> list[EmergencyEntry]:
        now = time.time()
        return [e for e in self._entries.values()
                if e.hard_clear_required or not e.is_expired(now)]

    def clear_all(self) -> int:
        """Emergency deactivation of ALL entries. Returns count cleared."""
        count = len(self._entries)
        self._entries.clear()
        self._leases.clear()
        return count
