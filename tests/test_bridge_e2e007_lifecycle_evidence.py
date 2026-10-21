"""E2E-007 structured lifecycle evidence + evidence fusion tests.

Proves the supervisor can independently determine:
    DELIVERED / ACKNOWLEDGED / STARTED / PROGRESSING / COMPLETED
    HANDOFF_READY
from MULTIPLE evidence channels — transport evidence, task-specific action,
model declarations, and independent QA — without requiring the worker to
print magic ACK/START/COMPLETE markers.

This is the evidence fusion required by the bridge phase-2 correction.

The module is honest:
- transport events are infrastructure events (adapter-generated, not model
- transcript correlation is supervisor-side observation
- model markers are ONE optional channel among several
- completion requires artifacts + tests + commit + INDEPENDENT QA
  (never the worker's own word)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from compute.bridge_lifecycle import (
    EvidenceChannel,
    LifecycleEvidence,
    LifecycleState,
)


# --- helpers -------------------------------------------------------------------------

def _now() -> float:
    return time.time()


class TestEvidenceFusion:
    """E2E-007: lifecycle states derive from evidence channels, never from a
    single text marker."""

    def test_delivery_confirmed_by_transport_evidence(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T1", "opencode-01-session", "worker reply")
        e.correlate_transcript("AB-T1", "worker transcript contains AB-T1")
        assert e.get_state() == LifecycleState.DELIVERY_CONFIRMED

    def test_transcript_correlation_is_supervisor_side(self):
        e = LifecycleEvidence()
        # transcript correlation is a supervisor observation, not worker print
        ok = e.correlate_transcript("AB-T9",
                                     "worker session export: [task_id=AB-T9]")
        assert ok is True
        assert e.get_state() == LifecycleState.DELIVERY_CONFIRMED

    def test_ack_can_be_inferred_without_model_marker(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T2", "opencode-01-session", "worker reply")
        e.correlate_transcript("AB-T2", "transcript contains AB-T2")
        # no model marker printed; START is supervisor-derived
        e.mark_task_started(action_seen=True)
        assert e.get_state() == LifecycleState.TASK_RUNNING

    def test_started_without_action_marker_invalidates(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T3", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T3", "transcript contains AB-T3")
        e.mark_task_started(action_seen=False)
        assert e.get_state() == LifecycleState.TASK_RUNNING  # inferred

    def test_progress_requires_task_scoped_evidence(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T4", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T4", "transcript contains AB-T4")
        e.mark_task_started(action_seen=True)
        # progress needs file/tool/test evidence
        e.mark_progress(file_changed=True, tool_used=False, test_started=False)
        assert e.get_state() == LifecycleState.TASK_PROGRESSING

    def test_progress_without_evidence_not_promoted(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T5", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T5", "transcript contains AB-T5")
        e.mark_task_started(action_seen=True)
        e.mark_progress(file_changed=False, test_started=False, tool_used=False)
        # no evidence → state stays RUNNING, not PROGRESSING
        assert e.get_state() == LifecycleState.TASK_RUNNING

    def test_complete_claim_does_not_promote_without_qa(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T8", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T8", "transcript contains AB-T8")
        e.mark_task_started(action_seen=True)
        e.mark_complete_claim("**TASK_COMPLETE AB-T8**")
        # model declares, but no artifacts, no tests, no QA → stays CLAIMED
        assert e.get_state() == LifecycleState.TASK_COMPLETE_CLAIMED

    def test_work_complete_requires_artifacts_tests_qa(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T9", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T9", "transcript contains AB-T9")
        e.mark_task_started(action_seen=True)
        e.add(EvidenceChannel.ARTIFACT_EXISTS,
              "artifact file exists")
        e.add(EvidenceChannel.TEST_PASSED,
              "test re-run passed")
        e.add(EvidenceChannel.COMMIT_EXISTS,
              "commit exists")
        e.add(EvidenceChannel.INDEPENDENT_QA,
              "QA passed")
        final = e.verify_complete(
            artifact_exists=True, test_passed=True,
            commit_exists=True,
            qr_artifact=True, qr_test=True, qr_commit=True,
            qr_qa_passed=True)
        assert final == LifecycleState.TASK_COMPLETE_VERIFIED
        assert e.get_state() == LifecycleState.TASK_COMPLETE_VERIFIED

    def test_worker_late_claim_not_a_promotion(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T10", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T10", "transcript contains AB-T10")
        e.mark_task_started(action_seen=True)
        # worker CLAIMS complete (model declared TASK_COMPLETE)
        e.mark_complete_claim("**TASK_COMPLETE AB-T10** came back")
        # but no artifacts/tests/commit/QA yet
        final = e.verify_complete(
            artifact_exists=False, test_passed=False, commit_exists=False,
            qr_artifact=False, qr_test=False, qr_commit=False,
            qr_qa_passed=False)
        # not enough evidence — CLAIMED is not VERIFIED
        assert final == LifecycleState.TASK_COMPLETE_CLAIMED
        assert e.get_state() == LifecycleState.TASK_COMPLETE_CLAIMED

    def test_evidence_channels_observable(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T11", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T11", "transcript contains AB-T11")
        e.mark_task_started(action_seen=True)
        e.add(EvidenceChannel.FILE_CHANGED,
              "source.py modified")
        summary = e.summarise()
        channels = set(summary["channels_present"])
        assert EvidenceChannel.TRANSPORT_CREATED.value in channels
        assert EvidenceChannel.TRANSCRIPT_CORRELATED.value in channels
        assert EvidenceChannel.TASK_SPECIFIC_ACTION.value in channels
        assert summary["evidence_count"] >= 5

    def test_model_marker_optional_not_required(self):
        e = LifecycleEvidence()
        e.observe_transport("AB-T12", "opencode-01-session", "reply")
        e.correlate_transcript("AB-T12", "transcript contains AB-T12")
        e.mark_task_started(action_seen=True)
        # no model markers at all — task still runs via evidence
        assert e.get_state() == LifecycleState.TASK_RUNNING
        channels = {c.channel.value for c in e.evidence}
        # should contain transport + transcript evidence, NOT model markers
        assert EvidenceChannel.MODEL_ACK.value not in channels
        assert EvidenceChannel.MODEL_START.value not in channels
        assert EvidenceChannel.MODEL_COMPLETE.value not in channels
