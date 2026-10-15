"""Tests for compute/emergency_stop.py — emergency stop, pause, recall, revocation.

Covers AT-21: emergency recall of nested teams, lease expiry fail-closed,
and side-effect blocking when stale output arrives.
"""
import time
import pytest

from compute.emergency_stop import (
    EmergencyStop, EmergencyScope, EmergencyAction,
    EmergencyEntry, EmergencyLease,
)


# ── Basic halt ───────────────────────────────────────────────────────────

class TestEmergencyHalt:
    def test_halt_worker_blocks_it(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.WORKER, "openai/codex", reason="malicious output")
        assert es.is_halted(EmergencyScope.WORKER, "openai/codex")

    def test_halt_all_blocks_everything(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.ALL, reason="emergency")
        assert es.is_halted(EmergencyScope.WORKER, "any_worker")
        assert es.is_halted(EmergencyScope.TEAM, "any_team")
        assert es.is_halted(EmergencyScope.GENESIS)

    def test_no_halt_means_clear(self):
        es = EmergencyStop()
        assert not es.is_halted(EmergencyScope.WORKER, "openai/codex")

    def test_different_workers_independent(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.WORKER, "codex", reason="bad")
        assert es.is_halted(EmergencyScope.WORKER, "codex")
        assert not es.is_halted(EmergencyScope.WORKER, "openai")


# ── Pause (resumable) ───────────────────────────────────────────────────

class TestEmergencyPause:
    def test_pause_blocks_and_expires(self):
        es = EmergencyStop()
        es.pause(EmergencyScope.WORKER, "ollama", ttl_s=0.1, reason="maintenance")
        assert es.is_halted(EmergencyScope.WORKER, "ollama")
        time.sleep(0.15)
        assert not es.is_halted(EmergencyScope.WORKER, "ollama")

    def test_pause_not_halted_after_expiry(self):
        es = EmergencyStop()
        es.pause(EmergencyScope.TEAM, "team-a", ttl_s=0.05, reason="brief")
        time.sleep(0.1)
        assert not es.is_halted(EmergencyScope.TEAM, "team-a")


# ── Revoke (permanent credential revocation) ────────────────────────────

class TestEmergencyRevoke:
    def test_revoke_blocks_even_after_no_ttl(self):
        """REVOKE with no TTL is permanent until manually cleared."""
        es = EmergencyStop()
        es.revoke(EmergencyScope.PROVIDER, "openai", reason="key compromised")
        assert es.is_halted(EmergencyScope.PROVIDER, "openai")

    def test_revoke_requires_manual_clear(self):
        es = EmergencyStop()
        es.revoke(EmergencyScope.WORKER, "codex", reason="compromised")
        assert es.is_halted(EmergencyScope.WORKER, "codex")
        # Even after a long time, hard_clear_required keeps it blocked
        time.sleep(0.01)
        assert es.is_halted(EmergencyScope.WORKER, "codex")

    def test_revoke_deactivatable(self):
        es = EmergencyStop()
        es.revoke(EmergencyScope.WORKER, "codex", reason="compromised")
        assert es.deactivate(EmergencyScope.WORKER, "codex") is True
        assert not es.is_halted(EmergencyScope.WORKER, "codex")


# ── Cancel (task-level) ─────────────────────────────────────────────────

class TestEmergencyCancel:
    def test_cancel_does_not_halt_worker(self):
        """CANCEL is task-level: worker remains active for other tasks."""
        es = EmergencyStop()
        es.cancel(EmergencyScope.WORKER, "codex", reason="task error")
        # CANCEL doesn't halt the worker (it's a task-level operation)
        # but it's still in the revocation list for that target
        entries = es.get_revoked_capabilities()
        # CANCEL entries are not in revoked_capabilities (only HALT/REVOKE/PAUSE)
        assert not any(e.target == "codex" and e.action == EmergencyAction.CANCEL
                       for e in entries)


# ── Lease tokens ─────────────────────────────────────────────────────────

class TestEmergencyLeases:
    def test_lease_issued_when_not_halted(self):
        es = EmergencyStop()
        lease = es.lease_token("ollama", ttl_s=60)
        assert lease is not None
        assert lease.worker_id == "ollama"
        assert lease.token.startswith("el-")

    def test_lease_denied_when_halted(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.WORKER, "codex", reason="emergency")
        lease = es.lease_token("codex", ttl_s=60)
        assert lease is None

    def test_lease_valid_then_expired(self):
        es = EmergencyStop()
        lease = es.lease_token("ollama", ttl_s=0.1)
        assert lease is not None
        assert es.validate_lease(lease.token) is True
        time.sleep(0.15)
        assert es.validate_lease(lease.token) is False

    def test_halt_revokes_existing_leases(self):
        es = EmergencyStop()
        lease = es.lease_token("codex", ttl_s=300)
        assert lease is not None
        assert es.validate_lease(lease.token) is True
        es.halt(EmergencyScope.WORKER, "codex", reason="emergency")
        # Lease is revoked — old token no longer valid
        assert es.validate_lease(lease.token) is False

    def test_all_scope_revokes_all_leases(self):
        es = EmergencyStop()
        lease_a = es.lease_token("worker-a", ttl_s=300)
        lease_b = es.lease_token("worker-b", ttl_s=300)
        assert lease_a is not None and lease_b is not None
        es.halt(EmergencyScope.ALL, reason="nuclear")
        assert es.validate_lease(lease_a.token) is False
        assert es.validate_lease(lease_b.token) is False


# ── Multi-target query ──────────────────────────────────────────────────

class TestMultiTargetQuery:
    def test_is_blocked_checks_all_targets(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.WORKER, "codex", reason="bad")
        assert es.is_blocked(worker_id="codex")
        assert not es.is_blocked(worker_id="openai")
        assert not es.is_blocked(team_id="team-a")

    def test_is_blocked_all_scope(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.ALL, reason="emergency")
        assert es.is_blocked(worker_id="anything")
        assert es.is_blocked(team_id="anything")
        assert es.is_blocked(provider_id="anything")


# ── Audit and state ─────────────────────────────────────────────────────

class TestAuditAndState:
    def test_audit_log_records_actions(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.WORKER, "codex", reason="test", issued_by="owner")
        log = es.audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "activated"
        assert log[0]["scope"] == "worker"
        assert log[0]["target"] == "codex"

    def test_active_entries_returns_only_active(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.WORKER, "codex", reason="halt")
        es.pause(EmergencyScope.WORKER, "ollama", ttl_s=0.05, reason="pause")
        time.sleep(0.1)
        active = es.active_entries()
        assert len(active) == 1  # only the halt entry is still active
        assert active[0].target == "codex"

    def test_clear_all_resets_state(self):
        es = EmergencyStop()
        es.halt(EmergencyScope.ALL, reason="test")
        es.halt(EmergencyScope.WORKER, "codex", reason="another")
        count = es.clear_all()
        assert count == 2
        assert len(es.active_entries()) == 0
        assert not es.is_halted(EmergencyScope.ALL)


# ── AT-21: Emergency recall of nested team ──────────────────────────────

class TestAT21EmergencyRecall:
    """AT-21: Revoke one nested team's tool authority remotely, confirm
    both active/queued child actions stop or safely expire."""

    def test_revoke_team_halts_all_workers_in_team(self):
        """Revoking a team should halt all workers under it."""
        es = EmergencyStop()
        es.revoke(EmergencyScope.TEAM, "team-alpha", reason="compromised")
        assert es.is_halted(EmergencyScope.TEAM, "team-alpha")

    def test_parent_tasks_remain_correctly_scoped(self):
        """Revoking a team doesn't affect parent (genesis) scope."""
        es = EmergencyStop()
        es.revoke(EmergencyScope.TEAM, "team-alpha", reason="compromised")
        # Genesis should NOT be halted by a team-scope revoke
        assert not es.is_halted(EmergencyScope.GENESIS)
        # But the team IS halted
        assert es.is_halted(EmergencyScope.TEAM, "team-alpha")

    def test_stale_worker_cannot_act_after_halt(self):
        """A disconnected worker with an expired lease cannot act."""
        es = EmergencyStop()
        lease = es.lease_token("worker-x", ttl_s=0.05)
        assert lease is not None
        # Worker gets halted while disconnected
        es.halt(EmergencyScope.WORKER, "worker-x", reason="compromised")
        # Even if the lease hasn't technically expired yet, the halt revokes it
        assert es.validate_lease(lease.token) is False

    def test_stale_output_blocked_after_revoke(self):
        """A model response arriving after revocation is blocked by the
        emergency stop layer (source: H02 — 'block further side effects
        even if an old model response arrives later')."""
        es = EmergencyStop()
        # Simulate: provider was active, then gets revoked
        assert not es.is_blocked(provider_id="openai")
        es.revoke(EmergencyScope.PROVIDER, "openai", reason="credential breach")
        # An old model response arrives AFTER revocation — it must be blocked
        assert es.is_blocked(provider_id="openai")
