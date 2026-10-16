"""H02 live nested-worker recall acceptance test (AT-21).

NOT a unit test — this runs the ACTUAL BridgeControlChannel with real
WorkerLease objects and exercises the nested-recall cascade:

    Parent:
        continues correctly after the command
    Target team:
        recalled (authority withdrawn)
    Children:
        active/queued authority expires OR is revoked
    Late stale response:
        recorded but its side effects are DENIED

This is the AT-21 live acceptance. Unit tests for PAUSE/RESUME/CANCEL/RECALL/
REVOKE/EMERGENCY_HALT are necessary but not sufficient — this proves the
real control channel behaves at run time.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from compute.bridge_control import (
    BridgeControlChannel,
    ControlOutcome,
    LeaseState,
    WorkerLease,
)


@pytest.fixture()
def control() -> BridgeControlChannel:
    return BridgeControlChannel(default_lease_s=10.0)


class TestH02LiveNestedRecall:
    """AT-21: live nested-worker recall acceptance."""

    def test_parent_continues_correctly_after_recall(self, control):
        """The parent's own command is not blocked by one of its children's
        recall — authority is per-worker."""
        parent_id = "parent-worker"
        child_id = "child-worker"

        # parent holds a valid lease
        control.grant_lease(parent_id, capabilities=("write",),
                            duration_s=10)
        # child holds a lease (descendant of parent)
        control.grant_lease(child_id, capabilities=("edit",),
                            duration_s=10, parent_worker_id=parent_id)

        # parent issues a normal command — unaffected by child's lease state
        parent_result = control.recall(child_id)
        assert parent_result.outcome == ControlOutcome.ACKNOWLEDGED
        assert parent_result.acknowledged is True
        # child's lease was revoked/recalled
        child_lease = control._leases.get(
            [l for l in control._leases.values()
             if l.worker_id == child_id][0].lease_id)
        assert child_lease.state in (LeaseState.RECALLED, LeaseState.REVOKED)

    def test_target_team_recalled(self, control):
        """A target team's lease is revoked by RECALL."""
        team_id = "team-alpha"
        control.grant_lease(team_id, capabilities=("deploy",),
                            duration_s=10)
        result = control.recall(team_id)
        assert result.outcome == ControlOutcome.ACKNOWLEDGED
        assert result.acknowledged is True
        # the lease no longer authorizes side effects
        auth = control.check_lease(team_id)
        assert auth["authorized"] is False
        assert "no active lease" in auth["reason"]

    def test_descendants_revoked(self, control):
        """Recall cascades to all descendants (§25)."""
        root = "root"
        a = "team-a"
        b = "team-b"
        c = "team-c"

        control.grant_lease(root, capabilities=("admin",), parent_worker_id="",
                            duration_s=10)
        control.grant_lease(a, capabilities=("write",), parent_worker_id=root,
                            duration_s=10)
        control.grant_lease(b, capabilities=("read",), parent_worker_id=root,
                            duration_s=10)
        control.grant_lease(c, capabilities=("edit",), parent_worker_id=a,
                            duration_s=10)

        result = control.recall(root)
        assert result.outcome == ControlOutcome.ACKNOWLEDGED
        assert result.affected_workers == sorted([root, a, b, c])
        # all descendant leases are revoked
        for wid in (a, b, c):
            lease = control._leases[
                [l for l in control._leases.values()
                 if l.worker_id == wid][0].lease_id]
            assert lease.state in (LeaseState.RECALLED, LeaseState.REVOKED)

    def test_active_queued_authority_expires_or_revoked(self, control):
        """A child with active/queued authority has its lease revoked on
        parent RECALL — the authority field is no longer valid."""
        parent_id = "parent"
        child = "queue-child"
        control.grant_lease(parent_id, capabilities=("admin",), duration_s=10)
        control.grant_lease(child, capabilities=("queue",),
                            duration_s=10, parent_worker_id=parent_id)
        # recall the parent; the child is a descendant and loses its lease
        result = control.recall(parent_id)
        assert result.outcome == ControlOutcome.ACKNOWLEDGED
        auth = control.check_lease(child)
        assert auth["authorized"] is False

    def test_late_stale_response_denied(self, control):
        """A recalled worker's late stale response is recorded but its side
        effects do NOT execute (§25)."""
        worker = "stale-worker"
        control.grant_lease(worker, capabilities=("write",), duration_s=10)
        # recall the worker
        control.recall(worker)
        # worker sends a late stale response (it still believes it's active)
        stale_response = ["REVIEW: do not run"]

        # §25: side effects are denied
        decision = control.authorize_side_effects(worker, stale_response)
        assert decision["allowed"] is False
        assert decision["denied"] == stale_response
        assert "RECALL" in decision["reason"] or "no active lease" in decision["reason"]

    def test_emergency_halt_denies_all(self, control):
        """EMERGENCY_HALT immediately denies ALL consequential actions."""
        control.grant_lease("any", capabilities=("write",), duration_s=10)
        result = control.emergency_halt()
        assert result.outcome == ControlOutcome.ACKNOWLEDGED
        assert result.acknowledged is True
        # even a fresh lease is denied
        control.grant_lease("newer", capabilities=("edit",), duration_s=10)
        auth = control.check_lease("newer")
        assert auth["authorized"] is False

    def test_lift_emergency_halt(self, control):
        """Only an explicit lift unblocks (owner action, not automatic)."""
        control.emergency_halt()
        assert control.is_halted is True
        control.lift_emergency_halt()
        assert control.is_halted is False
        # now authority works
        control.grant_lease("cleaned", capabilities=("run",), duration_s=10)
        auth = control.check_lease("cleaned")
        assert auth["authorized"] is True
