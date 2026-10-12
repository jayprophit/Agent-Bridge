"""Supervisor Runtime tests — the persistent loop OUTSIDE the chat turn.

Acceptance criteria from the directive (§30-§32), all with fake adapters so
no live worker is disturbed:
- worker goes idle  -> runtime detects WITHOUT a chat message -> sends
  CONTINUE -> verifies delivery evidence (§30 B/D/E/F/G/I/J)
- handoff enters    -> review processes it -> follow-on assigned (§30 K-N)
- checkpoint persists -> state survives a runtime RESTART (§32)
- watchdog: idle worker with no idle_reason is a SUPERVISOR DEFECT (§12)
- continuation_required only clears when nothing remains (§27)
"""
from __future__ import annotations

import json

import pytest

from compute.supervisor_runtime import (
    IDLE, NO_COMPATIBLE_READY_WORK, OFFLINE, RUNNING, SUPERVISOR_DEFECT,
    UNKNOWN_VERDICT, CodexAdapter, OpenCodeAdapter, SupervisorRuntime,
    WorkerAdapter)
from compute.supervision import ACCEPT, Gap, Handoff


class FakeAdapter(WorkerAdapter):
    """A scriptable worker for the acceptance tests (§30)."""

    def __init__(self, worker_id="fake-1", script=None):
        super().__init__(worker_id=worker_id, application="fake",
                         role="tester")
        self.script = list(script or [RUNNING])
        self.instructions: list[tuple[str, bool]] = []
        self.cycles_seen = 0

    def status(self):
        self.cycles_seen += 1
        verdict = (self.script[self.cycles_seen - 1]
                   if self.cycles_seen <= len(self.script)
                   else self.script[-1])
        return {"verdict": verdict,
                "evidence": [f"scripted verdict {verdict}"]}

    def send_instruction(self, instruction, continue_task=False):
        self.instructions.append((instruction, continue_task))
        return {"delivered": True, "channel": "fake",
                "evidence": ["fake accepted"]}


@pytest.fixture
def rt(tmp_path):
    return SupervisorRuntime(tmp_path / "rt_state", cycle_interval_s=1.0)


class TestIdleDetectionAndContinuation:
    def test_idle_worker_triggers_automatic_checkin(self, rt):
        """§30 B/F/G: WITHOUT a chat message, idle -> detect -> CONTINUE."""
        a = FakeAdapter(script=[RUNNING, IDLE, IDLE])
        rt.register_adapter(a)
        rt.run_cycle()                       # running: just heartbeat
        out = rt.run_cycle()                 # idle: check-in fires
        worker = out["workers"]["fake-1"]
        assert worker["verdict"] == IDLE
        assert worker["check_in"]["action"] == "continue_current_task"
        assert worker["check_in"]["delivered"] is True
        # §36: the instruction says CONTINUE, not "please continue"
        assert a.instructions and "CONTINUE" in a.instructions[0][0]
        assert a.instructions[0][1] is True   # continue_task=True

    def test_running_worker_is_not_interrupted(self, rt):
        a = FakeAdapter(script=[RUNNING, RUNNING])
        rt.register_adapter(a)
        rt.run_cycle()
        rt.run_cycle()
        assert a.instructions == []          # §3 observe quietly when healthy
        assert rt.supervisor.worker("fake-1").status == "IMPLEMENTING"

    def test_offline_is_honest_not_fabricated(self, rt):
        a = FakeAdapter(script=[OFFLINE])
        rt.register_adapter(a)
        out = rt.run_cycle()
        assert out["workers"]["fake-1"]["verdict"] == OFFLINE
        # honest: marked as a supervisor defect to investigate, not "fine"
        assert rt.idle_reasons["fake-1"] == SUPERVISOR_DEFECT


class TestWatchdogs:
    def test_idle_without_reason_is_defect(self, rt):
        """§12: an AVAILABLE worker with no recorded idle_reason is a
        SUPERVISOR DEFECT — the watchdog must name it."""
        a = FakeAdapter(script=[RUNNING])
        rt.register_adapter(a)
        rt.run_cycle()
        # simulate a worker that finished its work and went AVAILABLE with
        # no idle_reason recorded (the defect condition §12 describes)
        rt.supervisor.worker("fake-1").status = "AVAILABLE"
        rt.adapters.pop("fake-1")     # no adapter verdict this cycle
        out = rt._watchdogs()
        assert out["idle_without_reason"] == ["fake-1"]
        assert rt.idle_reasons["fake-1"] == SUPERVISOR_DEFECT

    def test_idle_with_recorded_reason_is_not_defect(self, rt):
        a = FakeAdapter(script=[RUNNING])
        rt.register_adapter(a)
        rt.run_cycle()
        rt.supervisor.worker("fake-1").status = "AVAILABLE"
        rt.idle_reasons["fake-1"] = NO_COMPATIBLE_READY_WORK
        out = rt._watchdogs()
        assert "idle_without_reason" not in out

    def test_handoff_queue_watchdog(self, rt):
        rt.supervisor.submit_handoff(Handoff(task_id="t-1",
                                             worker_id="fake-1",
                                             project="p"))
        out = rt.run_cycle()
        assert out["watchdogs"]["handoffs_waiting"] == 1


class TestHandoffProcessing:
    def test_handoff_review_then_follow_on(self, rt):
        """§30 K-N: subagent completes -> handoff enters review -> processed
        -> follow-on work assigned."""
        a = FakeAdapter(script=[RUNNING])
        rt.register_adapter(a)
        rt.supervisor.submit_handoff(Handoff(
            task_id="t-1", worker_id="fake-1", project="p",
            completed_work=["unit done"]))
        assert len(rt.supervisor.unreviewed_handoffs()) == 1
        r = rt.supervisor.review_handoff(
            "t-1", lambda h: (ACCEPT, ["tests green", "git verified"]))
        assert r["verdict"] == ACCEPT
        assert rt.supervisor.unreviewed_handoffs() == []   # §30 M
        assert rt.supervisor.worker("fake-1").status == "AVAILABLE"
        # gap from the handoff becomes work (§7)
        rt.supervisor.record_gap(Gap("g-1", "HIGH", "test", "coverage gap"))
        assert rt.supervisor.open_gaps()


class TestPersistenceAndRecovery:
    def test_checkpoint_survives_runtime_restart(self, tmp_path):
        """§32 RESTART ACCEPTANCE TEST: state survives; continuation_required
        remains true; workers reconciled."""
        state_dir = tmp_path / "rt"
        rt1 = SupervisorRuntime(state_dir, cycle_interval_s=1.0)
        rt1.register_adapter(FakeAdapter(script=[RUNNING, IDLE]))
        rt1.run_cycle()
        rt1.run_cycle()
        rt1.supervisor.submit_handoff(Handoff(task_id="t-9",
                                              worker_id="fake-1",
                                              project="p"))
        rt1.persist()
        assert rt1.continuation_required is True

        # simulate runtime restart (not the PC — §32)
        rt2 = SupervisorRuntime(state_dir, cycle_interval_s=1.0)
        rt2.register_adapter(FakeAdapter(script=[RUNNING]))
        recovered = rt2.recover()
        assert recovered["loaded"] is True
        assert rt2.cycles == 2                 # cycle count survived
        assert "fake-1" in recovered["workers_reconciled"]

    def test_checkpoint_is_valid_json_on_disk(self, rt):
        a = FakeAdapter(script=[IDLE])   # an idle worker needs supervision
        rt.register_adapter(a)
        rt.run_cycle()
        data = json.loads(rt.checkpoint_path.read_text(encoding="utf-8"))
        assert "cycles" in data and "continuation_required" in data
        # §27: with an idle worker and no idle_reason yet, continuation is
        # honestly True; it may only be False when NOTHING remains
        assert data["continuation_required"] is True

    def test_continuation_false_is_truthful_when_nothing_remains(self, rt):
        # no workers, no handoffs, no gaps: continuation_required=False is
        # the HONEST value (§27 — never a lie in either direction)
        rt.run_cycle()
        data = json.loads(rt.checkpoint_path.read_text(encoding="utf-8"))
        assert data["continuation_required"] is False

    def test_resumption_must_be_verified_before_continuation_clears(self, rt):
        """§45.8: idle -> CONTINUE sent -> the worker is pending verification
        -> continuation stays True -> only when it verifiably RUNS again does
        the flag clear."""
        a = FakeAdapter(script=[IDLE, RUNNING])
        rt.register_adapter(a)
        rt.run_cycle()                       # check-in sent
        assert "fake-1" in rt._pending_verification
        assert rt.continuation_required is True
        out = rt.run_cycle()                 # worker resumed
        assert out["workers"]["fake-1"].get("resumption_verified") is True
        assert "fake-1" not in rt._pending_verification
        rt.persist()
        assert rt.continuation_required is False   # nothing left: honest

    def test_continuation_clears_only_when_nothing_remains(self, rt):
        a = FakeAdapter(script=[RUNNING])
        rt.register_adapter(a)
        rt.run_cycle()
        # no handoffs, no gaps, no defects -> continuation may clear
        rt.continuation_required = False
        out = rt.run_cycle()
        assert out["watchdogs"] == {}          # genuinely quiet


class TestRealAdapters:
    def test_opencode_adapter_returns_a_verdict(self):
        """§9: the REAL adapter runs against the real opencode db. Verdict
        must be one of the known values — no fabrication."""
        a = OpenCodeAdapter(liveness_window_s=600.0)
        st = a.status()
        assert st["verdict"] in (RUNNING, IDLE, OFFLINE, UNKNOWN_VERDICT)
        assert st["evidence"]

    def test_codex_adapter_returns_a_verdict(self):
        a = CodexAdapter(liveness_window_s=900.0)
        st = a.status()
        assert st["verdict"] in (RUNNING, IDLE, OFFLINE, UNKNOWN_VERDICT)
        assert st["evidence"]

    def test_adapters_report_unknown_not_fake(self, tmp_path):
        """§15 honesty: a missing home must return OFFLINE with evidence,
        never a fabricated RUNNING."""
        a = CodexAdapter(codex_home=str(tmp_path / "nonexistent"))
        st = a.status()
        assert st["verdict"] == OFFLINE
        assert st["evidence"]
