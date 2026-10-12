"""Supervision tests — the permanent active supervision loop (§1-§38).

The contracts that matter: no unread handoffs (§30), no idle worker while
ready work exists (§8), stall = investigate not kill (§4), ACCEPT requires
evidence (§2/§6 — no false completion), a handoff can create work (§7).
"""
from __future__ import annotations

import pytest

from compute.supervision import (
    ACCEPT, AWAITING_QA, AVAILABLE, BLOCKED_VERDICT, COMPLETE, CRITICAL,
    CORRECTION_REQUIRED, EXTEND_SCOPE, FIXING, HIGH, HUNG, INTERRUPTED,
    INTERVENTION_STATES, MEDIUM, OFFLINE, REASSIGN, Gap, Handoff, Supervisor,
    WorkerRecord,
)


@pytest.fixture
def sup():
    return Supervisor(stall_threshold_s=10.0)


def _handoff(task="t-1", worker="w-1", gaps=None, remaining=None):
    return Handoff(
        task_id=task, worker_id=worker, project="agent-bridge",
        objective="build X", completed_work=["did X"],
        files_changed=["src/x.py"], branch="unit/x",
        baseline_sha="aaa", current_sha="bbb",
        tests_run=["pytest"], test_results={"passed": 10},
        known_gaps=gaps or [], remaining_work=remaining or [],
        recommended_next_action="wire into dashboard")


class TestWorkerRegistry:
    def test_register_and_heartbeat(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        rec = sup.worker("w-1")
        assert rec.status == AVAILABLE
        sup.heartbeat("w-1", status="IMPLEMENTING")
        assert sup.worker("w-1").status == "IMPLEMENTING"

    def test_heartbeat_unknown_worker_raises(self, sup):
        with pytest.raises(KeyError):
            sup.heartbeat("nope")

    def test_invalid_state_rejected(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="qa")
        with pytest.raises(ValueError):
            sup.heartbeat("w-1", status="PARTYING")


class TestStallDetection:
    def test_stalled_active_worker_detected(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "codex",
                            role="mat-worker")
        sup.heartbeat("w-1", status="IMPLEMENTING")
        rec = sup.worker("w-1")
        rec.last_heartbeat -= 1000.0    # simulate 1000s of silence
        assert sup.stalled_workers() == [rec]

    def test_idle_worker_never_stalled(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="research")
        rec = sup.worker("w-1")
        rec.last_heartbeat -= 1000.0
        assert sup.stalled_workers() == []   # AVAILABLE workers rest

    def test_intervene_marks_interrupted_not_dead(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        sup.heartbeat("w-1", status="IMPLEMENTING")
        sup.worker("w-1").last_heartbeat -= 1000.0
        actions = sup.intervene_on_stalls()
        assert len(actions) == 1
        assert actions[0]["action"] == "checkpoint_and_investigate"
        assert sup.worker("w-1").status == INTERRUPTED   # investigate, not kill


class TestAssignment:
    def test_assign_idle_worker(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="qa")
        r = sup.assign("w-1", "t-1", "run tests")
        assert r["assigned"] is True
        assert sup.worker("w-1").status == "ASSIGNED"

    def test_cannot_double_assign(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="qa")
        sup.assign("w-1", "t-1", "run tests")
        r = sup.assign("w-1", "t-2", "run more tests")
        assert r["assigned"] is False
        assert "ASSIGNED" in r["reason"]

    def test_auto_assign_gives_idle_workers_ready_work(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="qa")
        sup.register_worker("w-2", "EXTERNAL_AI_AGENT", "codex",
                            role="mat-worker")
        tasks = [
            {"task_id": "t-qa", "description": "tests", "capabilities": ["qa"]},
            {"task_id": "t-mat", "description": "MAT impl",
             "capabilities": ["mat-worker"]},
            {"task_id": "t-ui", "description": "UI work",
             "capabilities": ["ui-worker"]},
        ]
        assigned = sup.auto_assign(tasks)
        assert {a["task_id"] for a in assigned} == {"t-qa", "t-mat"}
        # t-ui stays unassigned — no worker with that capability (§8 no fake work)
        assert sup.worker("w-1").task_id == "t-qa"
        assert sup.worker("w-2").task_id == "t-mat"

    def test_no_ready_work_means_worker_stays_available(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="qa")
        assert sup.auto_assign([]) == []
        assert sup.worker("w-1").status == AVAILABLE


class TestHandoffReview:
    def test_handoff_moves_worker_to_awaiting_qa(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        sup.assign("w-1", "t-1", "build it")
        sup.submit_handoff(_handoff())
        assert sup.worker("w-1").status == AWAITING_QA
        assert len(sup.unreviewed_handoffs()) == 1

    def test_accept_requires_evidence(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        sup.submit_handoff(_handoff())
        # verifier returning ACCEPT with NO evidence is refused (§2)
        r = sup.review_handoff("t-1", lambda h: (ACCEPT, []))
        assert r["reviewed"] is False
        assert "evidence" in r["reason"]
        # handoff stays in the queue — nothing silently dropped
        assert len(sup.unreviewed_handoffs()) == 1

    def test_accept_with_evidence_frees_worker(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        sup.submit_handoff(_handoff())
        r = sup.review_handoff(
            "t-1", lambda h: (ACCEPT, ["git log verified", "10 tests passed"]))
        assert r["reviewed"] is True and r["verdict"] == ACCEPT
        assert sup.worker("w-1").status == AVAILABLE
        assert sup.worker("w-1").next_action == "wire into dashboard"
        assert sup.unreviewed_handoffs() == []   # queue drained (§30)

    def test_correction_sends_worker_back_to_fixing(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "codex",
                            role="mat-worker")
        sup.submit_handoff(_handoff(task="t-1", worker="w-1"))
        r = sup.review_handoff(
            "t-1", lambda h: (CORRECTION_REQUIRED, ["test_a missing"]))
        assert sup.worker("w-1").status == FIXING

    def test_reassign_frees_worker_for_new_assignment(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "codex",
                            role="mat-worker")
        sup.register_worker("w-2", "HERMES_INTERNAL", "hermes", role="qa")
        sup.submit_handoff(_handoff(task="t-1", worker="w-1"))
        r = sup.review_handoff(
            "t-1", lambda h: (REASSIGN, ["worker unfit for integration"]))
        assert r["verdict"] == REASSIGN
        assert sup.worker("w-1").status == AVAILABLE

    def test_unknown_verdict_rejected(self, sup):
        sup.submit_handoff(_handoff())
        with pytest.raises(ValueError):
            sup.review_handoff("t-1", lambda h: ("YOLO", ["x"]))

    def test_review_unknown_task_is_reported(self, sup):
        r = sup.review_handoff("ghost", lambda h: (ACCEPT, ["x"]))
        assert r["reviewed"] is False


class TestGapAnalysis:
    def test_handoff_gap_creates_work(self, sup):
        g = Gap(gap_id="g-1", severity=HIGH, category="test",
                description="no tests for handoff path",
                evidence=["handoff tests_run empty"])
        r = sup.record_gap(g)
        assert r["gap_recorded"] is True
        assert sup.open_gaps() == [g]

    def test_gaps_sorted_by_severity(self, sup):
        sup.record_gap(Gap("g-low", MEDIUM, "docs", "typo"))
        sup.record_gap(Gap("g-crit", CRITICAL, "security", "open port"))
        assert [g.gap_id for g in sup.open_gaps()] == ["g-crit", "g-low"]

    def test_min_severity_filter(self, sup):
        sup.record_gap(Gap("g-low", MEDIUM, "docs", "typo"))
        sup.record_gap(Gap("g-crit", CRITICAL, "security", "open port"))
        assert [g.gap_id for g in sup.open_gaps(min_severity=CRITICAL)] == \
            ["g-crit"]

    def test_bad_severity_rejected(self, sup):
        with pytest.raises(ValueError):
            sup.record_gap(Gap("g", "MEH", "x", "y"))


class TestSuperviseCycle:
    def test_cycle_reports_everything(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "codex",
                            role="mat-worker")
        sup.assign("w-1", "t-1", "MAT work")
        sup.worker("w-1").last_heartbeat -= 1000.0    # will stall
        out = sup.supervise(ready_tasks=[
            {"task_id": "t-2", "description": "more",
             "capabilities": ["mat-worker"]}])
        assert out["cycle"] == 1
        assert len(out["interventions"]) == 1
        # after intervention the worker is INTERRUPTED, not re-assigned t-2
        assert sup.worker("w-1").status == INTERRUPTED

    def test_cycle_assigns_ready_work_to_freed_worker(self, sup):
        sup.register_worker("w-1", "HERMES_INTERNAL", "hermes", role="qa")
        out = sup.supervise(ready_tasks=[
            {"task_id": "t-1", "description": "tests",
             "capabilities": ["qa"]}])
        assert out["assigned"] and out["assigned"][0]["task_id"] == "t-1"

    def test_completion_directive_states_covered(self):
        # §2 vocabulary must include every state the directive names
        from compute.supervision import WORKER_STATES
        for s in ("AVAILABLE", "ASSIGNED", "ANALYSING", "PLANNING",
                  "IMPLEMENTING", "TESTING", "FIXING", "REVIEWING",
                  "DOCUMENTING", "COMMITTING", "PUSHING", "WAITING",
                  "WAITING_FOR_QUOTA", "BLOCKED", "INTERRUPTED", "HUNG",
                  "AWAITING_QA", "COMPLETE", "OFFLINE"):
            assert s in WORKER_STATES


class TestPersistence:
    def test_round_trip_preserves_queue(self, sup, tmp_path):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        sup.submit_handoff(_handoff())
        sup.record_gap(Gap("g-1", HIGH, "test", "missing coverage"))
        p = tmp_path / "sup.json"
        sup.save(p)
        sup2 = Supervisor.load(p)
        assert len(sup2.unreviewed_handoffs()) == 1   # §30 survives reload
        assert len(sup2.open_gaps()) == 1
        assert sup2.overview()["continuation_required"] is True

    def test_overview_is_dashboard_shaped(self, sup):
        sup.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                            role="ide-worker")
        sup.register_worker("w-2", "EXTERNAL_AI_AGENT", "codex",
                            role="mat-worker")
        ov = sup.overview()
        assert ov["workers_total"] == 2
        assert ov["workers_by_status"][AVAILABLE] == 2
        assert "handoffs_pending" in ov and "gaps_open" in ov
