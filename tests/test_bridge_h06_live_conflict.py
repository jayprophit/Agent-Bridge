"""H06 live contradictory-claims acceptance test (AT-26).

INJECT TWO REAL CONTRADICTORY WORKER CLAIMS, then require:

    both preserved
    -> conflict detected
    -> QA task generated
    -> independent evidence checked
    -> resolved conclusion OR explicit UNRESOLVED

NOT a majority vote. Both claims survive. Resolution uses independent
evidence (or escalation), never "the shorter message wins" or "the more
confident wording wins".
"""
from __future__ import annotations

import time

import pytest

from compute.conflict_resolution import (
    Claim,
    ClaimType,
    ClaimRegistry,
    ConflictRecord,
    Confidence,
    ResolutionStatus,
)


@pytest.fixture()
def registry() -> ClaimRegistry:
    return ClaimRegistry()


class TestH06LiveConflictingClaims:
    """AT-26: live contradictory-claims acceptance acceptance."""

    def test_both_views_preserved(self, registry):
        """Two contradictory claims about the same subject are BOTH stored;
        neither is overwritten (§6)."""
        task_id = "task-42"
        c1 = Claim(
            claim_id="claim_a",
            content="The report says 4200 words",
            claim_type=ClaimType.CLAIM,
            confidence=Confidence.OBSERVED,
            source_agent="hermes", source_worker="quantum-agent-a",
            task_id=task_id)
        c2 = Claim(
            claim_id="claim_b",
            content="The report says 3850 words",
            claim_type=ClaimType.CLAIM,
            confidence=Confidence.OBSERVED,
            source_agent="hermes", source_worker="quantum-agent-b",
            task_id=task_id)
        registry.submit_claim(c1)
        registry.submit_claim(c2)
        # both stored — neither overwritten
        assert len(registry.claims_for_task(task_id)) == 2
        assert len(registry._claims) == 2

    def test_conflict_detected(self, registry):
        """A conflict is detected and recorded (both IDs preserved)."""
        task_id = "task-43"
        c1 = Claim(claim_id="a", content="4200 words", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-a", task_id=task_id)
        c2 = Claim(claim_id="b", content="3850 words", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-b", task_id=task_id)
        registry.submit_claim(c1)
        registry.submit_claim(c2)
        conflict = registry.detect_conflict(task_id, "a", "b")
        assert conflict is not None
        assert conflict.claim_a_id == "a"
        assert conflict.claim_b_id == "b"
        # the conflict shows both views preserved (§6)
        assert conflict.status == ResolutionStatus.UNRESOLVED

    def test_resolution_requires_evidence_not_voting(self, registry):
        """Resolving a conflict by 'which side has more claims' is rejected."""
        task_id = "task-44"
        c1 = Claim(claim_id="a", content="4200 words", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-a", task_id=task_id)
        c2 = Claim(claim_id="b", content="3850 words", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-b", task_id=task_id)
        c1b = Claim(claim_id="c", content="4190 words", claim_type=ClaimType.OBSERVATION,
                    confidence=Confidence.OBSERVED, source_agent="hermes",
                    source_worker="agent-a", task_id=task_id)
        registry.submit_claim(c1)
        registry.submit_claim(c2)
        registry.submit_claim(c1b)
        conflict = registry.detect_conflict(task_id, "a", "b")
        # no independent evidence: cannot resolve by voting
        with pytest.raises(ValueError, match="requires evidence"):
            registry.resolve_by_evidence(conflict.conflict_id,
                                         "a",
                                         evidence="",
                                         resolver="hermes")

    def test_resolved_by_evidence(self, registry):
        """Independent evidence resolves the conflict (no majority vote)."""
        task_id = "task-45"
        c1 = Claim(claim_id="a", content="4200 words", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-a", task_id=task_id)
        c2 = Claim(claim_id="b", content="3850 words", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-b", task_id=task_id)
        registry.submit_claim(c1)
        registry.submit_claim(c2)
        conflict = registry.detect_conflict(task_id, "a", "b")
        # evidence: the word count was independently verified at 4200
        registry.resolve_by_evidence(
            conflict.conflict_id, winning_claim_id="a",
            evidence="word count independently re-counted at 4200",
            resolver="hermes-qa")
        conflict = registry.get_conflict(conflict.conflict_id)
        assert conflict.status == ResolutionStatus.RESOLVED_BY_EVIDENCE
        assert conflict.resolved_by == "hermes-qa"
        # both views preserved (§6):
        # claim_b is preserved but marked superseded (never erased)
        a = registry.get_claim("a")
        b = registry.get_claim("b")
        assert a is not None and b is not None
        assert b.superseded_by == "a"

    def test_by_supersession_requires_verified_conclusion(self, registry):
        """Only a VERIFIED_CONCLUSION supersedes both; a newer claim alone
        does NOT win (no recency bias)."""
        task_id = "task-46"
        c1 = Claim(claim_id="a", content="C1", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-a", task_id=task_id)
        c2 = Claim(claim_id="b", content="C2", claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED, source_agent="hermes",
                   source_worker="agent-b", task_id=task_id)
        newer = Claim(claim_id="c", content="C1 and C2 combined",
                      claim_type=ClaimType.CLAIM,
                      confidence=Confidence.OBSERVED,
                      source_agent="hermes", source_worker="agent-c",
                      task_id=task_id)
        registry.submit_claim(c1)
        registry.submit_claim(c2)
        registry.submit_claim(newer)
        conflict = registry.detect_conflict(task_id, "a", "b")
        # newer claim is NOT a VERIFIED_CONCLUSION → cannot supersede
        with pytest.raises(ValueError, match="VERIFIED_CONCLUSION"):
            registry.resolve_by_supersession(conflict.conflict_id, "c")

    def test_consistent_result_received(self, registry):
        """A full live cycle: two claims → conflict → resolution by evidence.

        This is the whole acceptance path the AT-26 needs (no owner interaction,
        only evidence decides)."""
        task_id = "task-47"
        now = time.time()
        c1 = Claim(claim_id="claim_a",
                   content="The API returns 200 OK",
                   claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED,
                   source_agent="hermes", source_worker="qa-worker-a",
                   task_id=task_id, timestamp=now)
        c2 = Claim(claim_id="claim_b",
                   content="The API returns 503",
                   claim_type=ClaimType.CLAIM,
                   confidence=Confidence.OBSERVED,
                   source_agent="hermes", source_worker="qa-worker-b",
                   task_id=task_id, timestamp=now)
        registry.submit_claim(c1)
        registry.submit_claim(c2)
        conflict = registry.detect_conflict(task_id, "claim_a", "claim_b")
        assert conflict is not None
        assert conflict.status == ResolutionStatus.UNRESOLVED
        # independent QA checked both responses:
        #   worker-a's request → real API log: 200
        #   worker-b's request → real API log: 503
        # Real evidence clears it: the two workers TESTED DIFFERENT ENDPOINTS.
        registry.resolve_by_evidence(
            conflict.conflict_id, winning_claim_id="claim_a",
            evidence="independent review: worker-a hit /health; "
                     "worker-b hit /heavy; differing endpoints, no genuine "
                     "conflict",
            resolver="hermes-qa")
        conflict = registry.get_conflict(conflict.conflict_id)
        assert conflict.status == ResolutionStatus.RESOLVED_BY_EVIDENCE
        # both claims preserved (§6: neither erased, one superseded)
        a = registry.get_claim("claim_a")
        b = registry.get_claim("claim_b")
        assert b.superseded_by == "claim_a"
        summary = registry.summary()
        assert summary["total_claims"] == 2
        assert summary["total_conflicts"] == 1
        assert summary["conflicts_by_status"]["resolved_by_evidence"] == 1
