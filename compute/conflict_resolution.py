"""Semantic conflict handling and collective evidence quality (V2 H06, AT-26).

H06 requirement: Worker messages must distinguish observation, quoted source,
claim, inference, hypothesis, unresolved contradiction, and independently
verified conclusion; carry provenance and timestamps. When agents disagree,
preserve the competing views and evidence. Assign follow-up experiments or
independent reviewers; do not treat a majority vote, shortest message or most
confident wording as proof.

Key rules (§21 of the bridge spec):
- Never flatten disagreement — preserve both views.
- A shared hive blackboard publishes only typed claims under permission scopes.
- Memory updates require versioning and conflict-resolution rules.
- No majority vote, no shortest-message-wins, no most-confident-wins (§3).

This module implements:
- Typed claims with full provenance (ClaimType, confidence, source, timestamp)
- A claim registry that preserves competing views
- Conflict resolution via independent evidence, not voting
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from compute.agent_message import ClaimType


# --- confidence levels -----------------------------------------------------------------

class Confidence(str, Enum):
    """Confidence in a claim (mirrors hive/quota honesty rule)."""
    VERIFIED = "VERIFIED"      # independently verified conclusion
    OBSERVED = "OBSERVED"      # directly observed, not independently verified
    ESTIMATED = "ESTIMATED"    # heuristic, not confirmed
    UNKNOWN = "UNKNOWN"        # could not determine


# --- claim with provenance -----------------------------------------------------------------

@dataclass
class Claim:
    """One typed worker claim with full provenance (§4).

    Every claim carries:
    - claim_type (§21): OBSERVATION, SOURCE_QUOTE, CLAIM, INFERENCE,
      HYPOTHESIS, CONTRADICTION, VERIFIED_CONCLUSION
    - confidence: VERIFIED, OBSERVED, ESTIMATED, UNKNOWN
    - source: who made it, when, from what evidence
    - content: the actual claim text
    """
    claim_id: str
    content: str
    claim_type: ClaimType
    confidence: Confidence
    source_agent: str
    source_worker: str
    source_ref: str = ""         # e.g. commit SHA, file path, URL
    timestamp: float = field(default_factory=time.time)
    task_id: str = ""
    superseded_by: Optional[str] = None  # if later resolved

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "content": self.content,
            "claim_type": self.claim_type.value,
            "confidence": self.confidence.value,
            "source_agent": self.source_agent,
            "source_worker": self.source_worker,
            "source_ref": self.source_ref,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "superseded_by": self.superseded_by,
        }


# --- conflict resolution outcomes ------------------------------------------------------------

class ResolutionStatus(str, Enum):
    """How a conflict was (or wasn't) resolved."""
    UNRESOLVED = "unresolved"              # competing views preserved
    RESOLVED_BY_EVIDENCE = "resolved_by_evidence"  # independent evidence decided
    RESOLVED_BY_SUPERSESSION = "resolved_by_supersession"  # newer conclusion replaced old
    ESCALATED = "escalated"                # needs human/owner decision


@dataclass
class ConflictRecord:
    """A detected conflict between competing claims (§3, §6).

    Both views are preserved. Resolution requires evidence, not voting.
    """
    conflict_id: str
    task_id: str
    claim_a_id: str
    claim_b_id: str
    status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    resolution_evidence: str = ""
    resolved_by: str = ""
    detected_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "task_id": self.task_id,
            "claim_a_id": self.claim_a_id,
            "claim_b_id": self.claim_b_id,
            "status": self.status.value,
            "resolution_evidence": self.resolution_evidence,
            "resolved_by": self.resolved_by,
            "detected_at": self.detected_at,
            "resolved_at": self.resolved_at,
        }


# --- claim registry with conflict preservation (§6) ------------------------------------------------

class ClaimRegistry:
    """The hive's evidence-quality registry (§6, §21).

    Rules:
    - Every claim is stored with its type and provenance.
    - Competing claims are NEVER overwritten — both preserved (§6).
    - Resolution requires independent evidence, not voting (§6).
    - Resolution options: evidence-based, newer verified conclusion, escalation.
    - Memory updates require versioning (superseded_by chain), not overwriting.
    """

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._conflicts: dict[str, ConflictRecord] = {}
        self._task_claims: dict[str, list[str]] = {}  # task_id -> [claim_id]

    # -- claim submission -----------------------------------------------------------

    def submit_claim(self, claim: Claim) -> Claim:
        """Submit a typed claim to the registry."""
        self._claims[claim.claim_id] = claim
        self._task_claims.setdefault(claim.task_id, []).append(claim.claim_id)
        return claim

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        return self._claims.get(claim_id)

    def claims_for_task(self, task_id: str) -> list[Claim]:
        """All claims for a task (including superseded ones — never erased)."""
        return [self._claims[cid] for cid in self._task_claims.get(task_id, [])
                if cid in self._claims]

    # -- conflict detection (§6) ---------------------------------------------------------

    def detect_conflict(self, task_id: str, claim_a_id: str,
                         claim_b_id: str) -> Optional[ConflictRecord]:
        """Detect and record a conflict between two claims.

        Both claims must exist. Neither is overwritten — the conflict is
        recorded with both IDs preserved.
        """
        a = self._claims.get(claim_a_id)
        b = self._claims.get(claim_b_id)
        if not a or not b:
            return None

        # Detect: claims about the same subject with different content
        # (simple heuristic: same task, different content)
        conflict_id = f"conflict_{task_id}_{claim_a_id[:8]}_{claim_b_id[:8]}"
        if conflict_id in self._conflicts:
            return self._conflicts[conflict_id]

        conflict = ConflictRecord(
            conflict_id=conflict_id,
            task_id=task_id,
            claim_a_id=claim_a_id,
            claim_b_id=claim_b_id,
        )
        self._conflicts[conflict_id] = conflict
        return conflict

    def get_conflict(self, conflict_id: str) -> Optional[ConflictRecord]:
        return self._conflicts.get(conflict_id)

    def unresolved_conflicts(self, task_id: str = "") -> list[ConflictRecord]:
        """All unresolved conflicts (optionally filtered by task)."""
        result = []
        for c in self._conflicts.values():
            if c.status == ResolutionStatus.UNRESOLVED:
                if not task_id or c.task_id == task_id:
                    result.append(c)
        return result

    # -- conflict resolution (§6) ---------------------------------------------------------

    def resolve_by_evidence(self, conflict_id: str, winning_claim_id: str,
                             evidence: str, resolver: str) -> ConflictRecord:
        """Resolve a conflict using independent evidence (§6).

        The winning claim must have the evidence cited. The losing claim is
        preserved but marked superseded (versioned, not erased §6).
        """
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            raise ValueError(f"unknown conflict: {conflict_id}")
        if not evidence:
            raise ValueError("resolution requires evidence (§6: no voting)")

        losing_id = (conflict.claim_b_id if winning_claim_id == conflict.claim_a_id
                     else conflict.claim_a_id)

        # Preserve both: mark losing claim superseded (never erase §6)
        losing = self._claims.get(losing_id)
        if losing:
            losing.superseded_by = winning_claim_id

        conflict.status = ResolutionStatus.RESOLVED_BY_EVIDENCE
        conflict.resolution_evidence = evidence
        conflict.resolved_by = resolver
        conflict.resolved_at = time.time()
        return conflict

    def resolve_by_supersession(self, conflict_id: str,
                                  newer_claim_id: str) -> ConflictRecord:
        """Resolve by a newer VERIFIED_CONCLUSION that supersedes both (§6).

        Only works if the newer claim is a VERIFIED_CONCLUSION — a mere
        newer claim does NOT win (§6: no recency bias).
        """
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            raise ValueError(f"unknown conflict: {conflict_id}")
        newer = self._claims.get(newer_claim_id)
        if not newer:
            raise ValueError(f"unknown claim: {newer_claim_id}")
        if newer.claim_type != ClaimType.VERIFIED_CONCLUSION:
            raise ValueError(
                "supersession requires a VERIFIED_CONCLUSION, not just a "
                "newer claim (§6: no recency bias)")

        for old_id in (conflict.claim_a_id, conflict.claim_b_id):
            old = self._claims.get(old_id)
            if old:
                old.superseded_by = newer_claim_id

        conflict.status = ResolutionStatus.RESOLVED_BY_SUPERSESSION
        conflict.resolution_evidence = (
            f"superseded by VERIFIED_CONCLUSION {newer_claim_id}")
        conflict.resolved_by = newer.source_worker
        conflict.resolved_at = time.time()
        return conflict

    def escalate(self, conflict_id: str, reason: str) -> ConflictRecord:
        """Escalate an unresolved conflict to the owner (§6)."""
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            raise ValueError(f"unknown conflict: {conflict_id}")
        conflict.status = ResolutionStatus.ESCALATED
        conflict.resolution_evidence = reason
        conflict.resolved_at = time.time()
        return conflict

    # -- introspection (§6) ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Honest summary of the registry state."""
        total_claims = len(self._claims)
        by_type = {}
        for c in self._claims.values():
            by_type[c.claim_type.value] = by_type.get(c.claim_type.value, 0) + 1

        total_conflicts = len(self._conflicts)
        by_status = {}
        for c in self._conflicts.values():
            by_status[c.status.value] = by_status.get(c.status.value, 0) + 1

        return {
            "total_claims": total_claims,
            "claims_by_type": by_type,
            "total_conflicts": total_conflicts,
            "conflicts_by_status": by_status,
            "honest_note": "Competing claims are preserved, never erased (§6)",
        }

    def preserve_competing_views(self, task_id: str) -> list[Claim]:
        """Get ALL claims for a task, including superseded ones (§6).

        This is the core invariant: NO claim is ever erased. Superseded
        claims remain accessible with their superseded_by pointer.
        """
        return self.claims_for_task(task_id)
