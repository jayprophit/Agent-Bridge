"""H04 service objectives + H06 conflict resolution tests (AT-24, AT-26)."""
from __future__ import annotations

import time

import pytest

from compute.service_objectives import (
    AssuranceLevel,
    ObjectiveCategory,
    RecoveryEvent,
    RecoveryObjectivesMeasurer,
    ServiceObjective,
    TaskState,
    default_service_objectives,
    is_valid_task_transition,
    task_transition_reason,
)
from compute.conflict_resolution import (
    Claim,
    ClaimRegistry,
    ClaimType,
    Confidence,
    ConflictRecord,
    ResolutionStatus,
)


# --- H04: service objectives tests (AT-24) -------------------------------------

class TestServiceObjectives:
    def test_default_objectives_are_best_effort(self):
        """§5: default targets are BEST_EFFORT, not contractual (§5)."""
        objectives = default_service_objectives()
        for o in objectives:
            # Free tier: no contractual guarantees
            assert o.assurance in (
                AssuranceLevel.BEST_EFFORT,
                AssuranceLevel.BLOCKED_FREE_TIER,
                AssuranceLevel.NOT_MEASURED,
            )

    def test_provider_failover_is_blocked_on_free_tier(self):
        """§5: free plans generally don't provide failover SLAs."""
        objectives = {o.category: o for o in default_service_objectives()}
        failover = objectives[ObjectiveCategory.PROVIDER_FAILOVER_TIME]
        assert failover.assurance == AssuranceLevel.BLOCKED_FREE_TIER
        assert "no failover SLA" in failover.evidence

    def test_measured_vs_target(self):
        """meets_target returns None when not measured (honest)."""
        o = ServiceObjective(
            category=ObjectiveCategory.RECOVERY_TIME_RTO,
            target_value=600.0,
            assurance=AssuranceLevel.BEST_EFFORT)
        assert o.meets_target is None  # not measured yet
        o.measured_value = 300.0
        assert o.meets_target is True   # 300 <= 600: meets target
        o.measured_value = 900.0
        assert o.meets_target is False  # 900 > 600: exceeds target

    def test_retry_budget_higher_is_better(self):
        """Retry budget: higher headroom is better."""
        o = ServiceObjective(
            category=ObjectiveCategory.RETRY_BUDGET,
            target_value=3,
            assurance=AssuranceLevel.BEST_EFFORT)
        o.measured_value = 5
        assert o.meets_target is True  # 5 >= 3: enough budget
        o.measured_value = 2
        assert o.meets_target is False  # 2 < 3: not enough


# --- H04: task state machine tests (§6) ------------------------------------------

class TestTaskStateMachine:
    def test_running_to_waiting_approval(self):
        assert is_valid_task_transition(
            TaskState.RUNNING_REMOTE, TaskState.WAITING_APPROVAL)

    def test_running_to_waiting_quota(self):
        assert is_valid_task_transition(
            TaskState.RUNNING_REMOTE, TaskState.WAITING_QUOTA)

    def test_checkpointed_to_recovering(self):
        """Crash from CHECKPOINTED goes to RECOVERING."""
        assert is_valid_task_transition(
            TaskState.CHECKPOINTED, TaskState.RECOVERING)

    def test_recovering_to_failed(self):
        """Recovery failure is possible (§7)."""
        assert is_valid_task_transition(
            TaskState.RECOVERING, TaskState.FAILED)

    def test_completed_verified_transition(self):
        assert is_valid_task_transition(
            TaskState.RUNNING_REMOTE, TaskState.COMPLETED_VERIFIED)

    def test_illegal_transition(self):
        """WAITING_APPROVAL -> CHECKPOINTED directly is illegal."""
        assert not is_valid_task_transition(
            TaskState.WAITING_APPROVAL, TaskState.CHECKPOINTED)

    def test_transition_reasons_documented(self):
        """Every valid transition has a documented reason (§6)."""
        reason = task_transition_reason(
            TaskState.RUNNING_REMOTE, TaskState.WAITING_APPROVAL)
        assert reason is not None
        assert "gate" in reason.lower() or "approval" in reason.lower()


# --- H04: RTO/RPO measurement tests (AT-24) ---------------------------------------

class TestRecoveryObjectives:
    def test_no_crash_no_rto(self):
        """Honest: RTO is None if no recovery was observed."""
        measurer = RecoveryObjectivesMeasurer()
        assert measurer.measured_rto() is None

    def test_no_crash_no_rpo(self):
        """Honest: RPO is None if no crash was observed."""
        measurer = RecoveryObjectivesMeasurer()
        assert measurer.measured_rpo() is None

    def test_rpo_from_checkpoint_to_crash(self):
        """RPO = time between last checkpoint and crash."""
        measurer = RecoveryObjectivesMeasurer()
        base = time.time()
        measurer.record_checkpoint("task-1", timestamp=base)
        rpo = measurer.record_crash("task-1", crash_time=base + 120)
        assert rpo == 120.0  # 2 minutes of work lost
        assert measurer.measured_rpo() == 120.0

    def test_rto_from_crash_to_recovery(self):
        """RTO = time to recover after crash."""
        measurer = RecoveryObjectivesMeasurer()
        base = time.time()
        measurer.record_checkpoint("task-1", timestamp=base)
        measurer.record_crash("task-1", crash_time=base + 60)
        measurer.record_recovery("task-1", recovery_time=45.0,
                                  recovered_ts=base + 105)
        assert measurer.measured_rto() == 45.0

    def test_worst_case_measurement(self):
        """RTO/RPO report the WORST observed, not the best."""
        measurer = RecoveryObjectivesMeasurer()
        base = time.time()
        # Task 1: good recovery
        measurer.record_checkpoint("t1", timestamp=base)
        measurer.record_crash("t1", crash_time=base + 30)
        measurer.record_recovery("t1", recovery_time=10.0, recovered_ts=base + 40)
        # Task 2: worse recovery
        measurer.record_checkpoint("t2", timestamp=base)
        measurer.record_crash("t2", crash_time=base + 300)
        measurer.record_recovery("t2", recovery_time=120.0, recovered_ts=base + 420)
        assert measurer.measured_rpo() == 300.0  # worst RPO
        assert measurer.measured_rto() == 120.0   # worst RTO

    def test_summary_honest(self):
        """Summary reports what's measured and what's not."""
        measurer = RecoveryObjectivesMeasurer()
        base = time.time()
        measurer.record_checkpoint("t1", timestamp=base)
        measurer.record_crash("t1", crash_time=base + 60)
        measurer.record_recovery("t1", recovery_time=30.0, recovered_ts=base + 90)
        s = measurer.summary()
        assert s["checkpoints_recorded"] == 1
        assert s["crashes_observed"] == 1
        assert s["recoveries_observed"] == 1
        assert s["rpo_measured_s"] == 60.0
        assert s["rto_measured_s"] == 30.0
        assert "independent" in s["honest_note"].lower()

    def test_crash_without_checkpoint(self):
        """Crash with no prior checkpoint: RPO is infinite (honest)."""
        measurer = RecoveryObjectivesMeasurer()
        rpo = measurer.record_crash("task-x", crash_time=time.time())
        assert rpo == float("inf")
        assert measurer.measured_rpo() is None  # inf excluded from max


# --- H06: claim type tests (§21) ---------------------------------------------------

class TestClaimTypes:
    def _make_claim(self, claim_type=ClaimType.OBSERVATION,
                    content="test", agent="hermes"):
        return Claim(
            claim_id=f"c_{abs(hash(content))}",
            content=content,
            claim_type=claim_type,
            confidence=Confidence.OBSERVED,
            source_agent=agent,
            source_worker="w1",
        )

    def test_all_claim_types_distinct(self):
        """§21: 7 distinct claim types."""
        types = {ct.value for ct in ClaimType}
        assert len(types) == 7
        assert "OBSERVATION" in types
        assert "VERIFIED_CONCLUSION" in types

    def test_observation_is_not_verified(self):
        c = self._make_claim(ClaimType.OBSERVATION)
        assert c.claim_type == ClaimType.OBSERVATION
        assert c.confidence == Confidence.OBSERVED

    def test_verified_conclusion_has_verified_confidence(self):
        c = self._make_claim(ClaimType.VERIFIED_CONCLUSION)
        c.confidence = Confidence.VERIFIED
        assert c.claim_type == ClaimType.VERIFIED_CONCLUSION
        assert c.confidence == Confidence.VERIFIED


# --- H06: conflict preservation tests (§3, §6) ---------------------------------------

class TestConflictPreservation:
    def _make_claims(self, registry, task_id="task-1"):
        a = Claim(
            claim_id="claim-a", content="X is true",
            claim_type=ClaimType.CLAIM, confidence=Confidence.OBSERVED,
            source_agent="opencode", source_worker="oc-1", task_id=task_id)
        b = Claim(
            claim_id="claim-b", content="X is false",
            claim_type=ClaimType.CLAIM, confidence=Confidence.OBSERVED,
            source_agent="codex", source_worker="cx-1", task_id=task_id)
        registry.submit_claim(a)
        registry.submit_claim(b)
        return a, b

    def test_competing_claims_both_preserved(self):
        """§6: when agents disagree, BOTH views are preserved."""
        reg = ClaimRegistry()
        a, b = self._make_claims(reg)
        claims = reg.claims_for_task("task-1")
        assert len(claims) == 2
        contents = {c.content for c in claims}
        assert "X is true" in contents
        assert "X is false" in contents

    def test_conflict_detected(self):
        """Conflicts are detected and recorded with both claim IDs."""
        reg = ClaimRegistry()
        self._make_claims(reg)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        assert conflict is not None
        assert conflict.claim_a_id == "claim-a"
        assert conflict.claim_b_id == "claim-b"
        assert conflict.status == ResolutionStatus.UNRESOLVED

    def test_resolution_requires_evidence(self):
        """§6: resolution requires evidence — no voting."""
        reg = ClaimRegistry()
        self._make_claims(reg)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        with pytest.raises(ValueError, match="evidence"):
            reg.resolve_by_evidence(conflict.conflict_id,
                                     winning_claim_id="claim-a",
                                     evidence="", resolver="hermes")

    def test_resolution_by_evidence_preserves_loser(self):
        """§6: loser is superseded, NOT erased."""
        reg = ClaimRegistry()
        self._make_claims(reg)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        reg.resolve_by_evidence(
            conflict.conflict_id, winning_claim_id="claim-a",
            evidence="verified by test T-001", resolver="hermes")
        loser = reg.get_claim("claim-b")
        assert loser is not None  # STILL EXISTS (§6: no erasing)
        assert loser.superseded_by == "claim-a"
        assert conflict.status == ResolutionStatus.RESOLVED_BY_EVIDENCE

    def test_no_recency_bias(self):
        """§6: a NEWER claim does NOT win without being a VERIFIED_CONCLUSION."""
        reg = ClaimRegistry()
        self._make_claims(reg)
        # Add a newer claim
        newer = Claim(
            claim_id="claim-c", content="Maybe X is uncertain",
            claim_type=ClaimType.HYPOTHESIS, confidence=Confidence.ESTIMATED,
            source_agent="hermes", source_worker="sup", task_id="task-1")
        reg.submit_claim(newer)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        # Trying to supersede with a HYPOTHESIS must fail (§6)
        with pytest.raises(ValueError, match="VERIFIED_CONCLUSION"):
            reg.resolve_by_supersession(conflict.conflict_id,
                                         newer_claim_id="claim-c")

    def test_supersession_with_verified_conclusion(self):
        """A VERIFIED_CONCLUSION CAN supersede older claims (§6)."""
        reg = ClaimRegistry()
        self._make_claims(reg)
        verified = Claim(
            claim_id="claim-v",
            content="X is true (independently verified)",
            claim_type=ClaimType.VERIFIED_CONCLUSION,
            confidence=Confidence.VERIFIED,
            source_agent="hermes", source_worker="qa",
            task_id="task-1")
        reg.submit_claim(verified)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        reg.resolve_by_supersession(conflict.conflict_id,
                                     newer_claim_id="claim-v")
        assert conflict.status == ResolutionStatus.RESOLVED_BY_SUPERSESSION
        # Both old claims superseded
        assert reg.get_claim("claim-a").superseded_by == "claim-v"
        assert reg.get_claim("claim-b").superseded_by == "claim-v"

    def test_escalation(self):
        """§6: unresolved conflicts can be escalated."""
        reg = ClaimRegistry()
        self._make_claims(reg)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        reg.escalate(conflict.conflict_id, "needs owner decision")
        assert conflict.status == ResolutionStatus.ESCALATED

    def test_unresolved_conflicts_listed(self):
        reg = ClaimRegistry()
        self._make_claims(reg)
        conflict = reg.detect_conflict("task-1", "claim-a", "claim-b")
        unresolved = reg.unresolved_conflicts("task-1")
        assert len(unresolved) == 1
        assert unresolved[0].conflict_id == conflict.conflict_id

    def test_summary_reports_claims_by_type(self):
        reg = ClaimRegistry()
        self._make_claims(reg)
        s = reg.summary()
        assert s["total_claims"] == 2
        assert "CLAIM" in s["claims_by_type"]
        assert "preserved" in s["honest_note"].lower()
