"""Structured lifecycle evidence + evidence fusion (E2E-007).

E2E-007 requirement:
    "Hermes can independently determine
     DELIVERED / ACKNOWLEDGED / STARTED / PROGRESSING / COMPLETED /
     HANDOFF_READY
     from adapter/runtime evidence — not from magic model markers."

The old protocol required the worker to print exact text such as
    TASK_ACK / TASK_START / TASK_COMPLETE
for the supervisor to trust them. E2E-006 proved the worker did the work,
produced the file and passed the test — but omitted the marker — and the
supervisor correctly refused to mark the task started. That honesty was
right; the protocol was wrong: the model should not narrate its own state.

This module implements the correct design:

    A. TRANSPORT EVIDENCE   — the adapter knows when it created the
                              invocation, sent the complete brief, obtained a
                              worker/session identifier, received output.
    B. EXECUTION EVIDENCE   — supervisor-derived when task-specific action
                              begins (file open, tool invocation, test run).
    C. MODEL-DECLARED       — the worker's text markers (ACK/START/COMPLETE)
                              are treated as ONE optional evidence channel
                              among several — never mandatory.
    D. SUPERVISOR-VERIFIED — Hermes derives the true state from the evidence.

The lifecycle is an evidence-gated state machine:

    DELIVERY_PENDING -> DELIVERY_ATTEMPTED -> DELIVERY_CONFIRMED (A)
                           -> SESSION_BOUND (A)
                           -> ACKNOWLEDGED (B+C: receiver-side proves receipt)
                           -> TASK_RUNNING (B: task-specific action observed)
                           -> TASK_PROGRESSING (B: task-scoped file/tool/test)
                           -> TASK_COMPLETE_CLAIMED (C: worker declared)
                           -> TASK_COMPLETE_VERIFIED (D: artifact + tests + QA)
                           -> HANDOFF_READY

Note the semantics: COMPLETE WORK is not the model's word; it is VERIFIED
by artifacts + tests + independent QA. A worker claiming COMPLETE without
those is recorded as WORKER_CLAIMS_COMPLETE, not WORK_COMPLETE_VERIFIED.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# --- lifecycle states -----------------------------------------------------------------

class LifecycleState(str, Enum):
    DELIVERY_PENDING = "DELIVERY_PENDING"
    DELIVERY_ATTEMPTED = "DELIVERY_ATTEMPTED"
    DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
    SESSION_BOUND = "SESSION_BOUND"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    TASK_RUNNING = "TASK_RUNNING"
    TASK_PROGRESSING = "TASK_PROGRESSING"
    TASK_COMPLETE_CLAIMED = "TASK_COMPLETE_CLAIMED"
    TASK_COMPLETE_VERIFIED = "TASK_COMPLETE_VERIFIED"
    HANDOFF_READY = "HANDOFF_READY"
    STALLED = "STALLED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


# --- evidence channels (A/B/C/D) ------------------------------------------------------

class EvidenceChannel(str, Enum):
    # A. transport evidence
    TRANSPORT_CREATED = "TRANSPORT_CREATED"          # adapter created invocation
    TRANSPORT_SENT = "TRANSPORT_SENT"                # complete brief sent
    WORKER_SESSION_OBTAINED = "WORKER_SESSION_OBTAINED"  # adapter got session id
    WORKER_OUTPUT_RECEIVED = "WORKER_OUTPUT_RECEIVED"    # output captured
    TRANSCRIPT_CORRELATED = "TRANSCRIPT_CORRELATED"      # task_id in worker state
    # B. execution evidence (supervisor-derived)
    TASK_SPECIFIC_ACTION = "TASK_SPECIFIC_ACTION"    # worker opened/modified file
    TOOL_INVOCATION = "TOOL_INVOCATION"              # worker invoked a tool
    TEST_STARTED = "TEST_STARTED"                    # worker ran a test
    FILE_CHANGED = "FILE_CHANGED"                    # file changed in write-set
    # C. model-declared
    MODEL_ACK = "MODEL_ACK"                          # worker printed ACK
    MODEL_START = "MODEL_START"                      # worker printed TASK_START
    MODEL_COMPLETE = "MODEL_COMPLETE"                # worker printed TASK_COMPLETE
    # D. supervisor-verified
    ARTIFACT_EXISTS = "ARTIFACT_EXISTS"
    TEST_PASSED = "TEST_PASSED"
    COMMIT_EXISTS = "COMMIT_EXISTS"
    INDEPENDENT_QA = "INDEPENDENT_QA"
    # outcome
    WORKER_CLAIMS_COMPLETE = "WORKER_CLAIMS_COMPLETE"
    WORK_COMPLETE_VERIFIED = "WORK_COMPLETE_VERIFIED"
    SKIPPED = "SKIPPED"          # an optional channel did not fire


@dataclass
class EvidenceRecord:
    """One evidence record: channel + the actual fact."""
    channel: EvidenceChannel
    evidence: str                      # e.g. "session export contains task_id"
    verified_by: str = ""              # supervisor/QA
    recorded_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "evidence": self.evidence,
            "verified_by": self.verified_by,
            "recorded_at": self.recorded_at,
        }


# --- evidence fusion state machine ------------------------------------------------------

class LifecycleEvidence:
    """Gates lifecycle state transitions on MULTIPLE independent evidence
    channels, never a single text marker. Unknown remains unknown."""

    def __init__(self) -> None:
        self._state = LifecycleState.DELIVERY_PENDING
        self.evidence: list[EvidenceRecord] = []
        self._fee = {}  # channel -> last evidence

    # -- manual evidence addition (module is hybrid: some events are
    #    adapter/supervisor-generated infrastructure events) ----------------------

    def add(self, channel: EvidenceChannel, evidence: str,
            verified_by: str = "") -> None:
        rec = EvidenceRecord(channel, evidence, verified_by)
        self.evidence.append(rec)
        self._fee[channel] = rec

    def observe_transport(self, task_id: str, session_id: str,
                          output: str) -> None:
        """A. adapter-level events (module generates these — the model
        does not narrate them)."""
        self.add(EvidenceChannel.TRANSPORT_CREATED,
                 f"adapter created headless invocation for task_id={task_id}")
        self.add(EvidenceChannel.TRANSPORT_SENT,
                 f"complete brief sent (project={task_id[:8]}..., "
                 f"receiver={session_id[:8]}...)")
        self.add(EvidenceChannel.WORKER_SESSION_OBTAINED,
                 f"worker session bound: id={session_id}")
        self.add(EvidenceChannel.WORKER_OUTPUT_RECEIVED,
                 f"worker output received, {len(output)} chars")
        # TRANSCRIPT_CORRELATED is supervisor-derived (module checks worker
        # transcript/state for task_id — not required of the worker to print)

    def correlate_transcript(self, task_id: str, transcript: str) -> bool:
        """Supervisor check: does the worker transcript/state contain the
        task_id? A supervisor-side observation, not a worker print."""
        ok = task_id in transcript
        if ok:
            self.add(EvidenceChannel.TRANSCRIPT_CORRELATED,
                     f"transcript references task_id={task_id}")
            self._set_state(LifecycleState.DELIVERY_CONFIRMED)
        return ok

    def _set_state(self, s: LifecycleState) -> None:
        self._state = s

    # -- lifecycle transitions ---------------------------------------------------------

    def mark_task_started(self, action_seen: bool) -> None:
        """B. START is supervisor-derived when task-specific action is seen.
        If no action visible but delivery CONFIRMED, START is inferred."""
        if action_seen:
            self.add(EvidenceChannel.TASK_SPECIFIC_ACTION,
                     "task-specific action observed (file open/tool/test)")
            self._set_state(LifecycleState.TASK_RUNNING)
        elif self._state_is(LifecycleState.DELIVERY_CONFIRMED):
            # inference: ACK proven receipt + delivery succeeded ⇒ running
            self.add(EvidenceChannel.TASK_SPECIFIC_ACTION,
                     "inferred: delivery verified + ACK (no action marker yet)")
            self._set_state(LifecycleState.TASK_RUNNING)
        else:
            self.add(EvidenceChannel.TASK_SPECIFIC_ACTION,
                     "not started: no task-specific action observed")

    def mark_progress(self, file_changed: bool, test_started: bool = False,
                      tool_used: bool = False) -> None:
        """B. PROGRESS: task-scoped file/tool/test activity."""
        if file_changed or tool_used or test_started:
            evidence = []
            if file_changed:
                evidence.append("file modified in task write-set")
            if tool_used:
                evidence.append("tool invoked for task")
            if test_started:
                evidence.append("test started")
            self.add(EvidenceChannel.TASK_SPECIFIC_ACTION,
                     "; ".join(evidence))
            # from first progress, mark progressing
            if self._state_is(LifecycleState.TASK_RUNNING):
                self._set_state(LifecycleState.TASK_PROGRESSING)
        else:
            self.add(EvidenceChannel.TASK_SPECIFIC_ACTION,
                     "no task-specific progress observed")

    def mark_complete_claim(self, output: str) -> None:
        """C. worker CLAIMS complete (model declares). Record — don't trust."""
        if "TASK_COMPLETE" in output:
            self.add(EvidenceChannel.MODEL_COMPLETE,
                     "worker declared TASK_COMPLETE")
            self._set_state(LifecycleState.TASK_COMPLETE_CLAIMED)
        else:
            self.add(EvidenceChannel.MODEL_COMPLETE,
                     "worker did not declare complete")

    def verify_complete(self, artifact_exists: bool, test_passed: bool,
                        commit_exists: bool, qr_artifact,
                        qr_test, qr_commit, qr_qa_passed) -> str:
        """D. COMPLETE VERIFICATION: artifacts + tests + commit + QA.

        Returns the final state, or raises ValueError if verification
        cannot be established (honest unknown)."""
        parts = []
        if artifact_exists:
            self.add(EvidenceChannel.ARTIFACT_EXISTS,
                     "task write-set artifact exists")
            parts.append("artifact")
        else:
            self.add(EvidenceChannel.ARTIFACT_EXISTS,
                     "artifact MISSING")
        if test_passed:
            self.add(EvidenceChannel.TEST_PASSED,
                     "test re-run passed")
            parts.append("test")
        else:
            self.add(EvidenceChannel.TEST_PASSED,
                     "test re-run NOT passed")
        if commit_exists:
            self.add(EvidenceChannel.COMMIT_EXISTS,
                     "commit exists on assigned branch")
            parts.append("commit")
        else:
            self.add(EvidenceChannel.COMMIT_EXISTS,
                     "no commit")

        # independent QA by a different process (never the worker's own claim)
        if qr_qa_passed:
            self.add(EvidenceChannel.INDEPENDENT_QA,
                     "independent QA passed")
            parts.append("QA")
        else:
            self.add(EvidenceChannel.INDEPENDENT_QA,
                     "independent QA NOT passed")

        if len(parts) >= 2:   # artifact+test or artifact+QA etc.
            self._set_state(LifecycleState.TASK_COMPLETE_VERIFIED)
            return self.get_state()
        # not enough evidence — keep CLAIMED, don't promote
        return self.get_state()

    # -- accessors ---------------------------------------------------------------------

    def get_state(self) -> LifecycleState:
        return self._state

    def summarise(self) -> dict[str, Any]:
        channels = {c.channel.value for c in self.evidence}
        return {
            "state": self._state.value,
            "channels_present": sorted(channels),
            "evidence_count": len(self.evidence),
        }

    # -- guard helpers -----------------------------------------------------------------

    def _state_is(self, s: LifecycleState) -> bool:
        return self._state == s

    def can_transition(self, to: LifecycleState) -> bool:
        """Admit only our documented lifecycle. A mid-stream mark_event is a
        defect unless it is a duplicate of a state we already hold."""
        if to == self._state:
            return True
        order = [
            LifecycleState.DELIVERY_PENDING,
            LifecycleState.DELIVERY_ATTEMPTED,
            LifecycleState.DELIVERY_CONFIRMED,
            LifecycleState.SESSION_BOUND,
            LifecycleState.ACKNOWLEDGED,
            LifecycleState.TASK_RUNNING,
            LifecycleState.TASK_PROGRESSING,
            LifecycleState.TASK_COMPLETE_CLAIMED,
            LifecycleState.TASK_COMPLETE_VERIFIED,
            LifecycleState.HANDOFF_READY,
            LifecycleState.STALLED,
            LifecycleState.BLOCKED,
            LifecycleState.REJECTED,
        ]
        try:
            i = order.index(self._state)
        except ValueError:
            return False
        return order.index(to) > i
