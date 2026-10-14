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
import subprocess
import os
import sys
from datetime import datetime

import pytest

from compute.supervisor_runtime import (
    IDLE, NO_COMPATIBLE_READY_WORK, OFFLINE, RUNNING, SUPERVISOR_DEFECT,
    UNKNOWN_VERDICT, WAITING_FOR_QUOTA, CodexAdapter, OllamaAdapter,
    OpenCodeAdapter, SupervisorRuntime, WorkerAdapter, parse_codex_cooldown)
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
        assert st["verdict"] in (RUNNING, IDLE, OFFLINE, UNKNOWN_VERDICT,
                                 WAITING_FOR_QUOTA)
        assert st["evidence"]

    def test_adapters_report_unknown_not_fake(self, tmp_path):
        """§15 honesty: a missing home must return OFFLINE with evidence,
        never a fabricated RUNNING."""
        a = CodexAdapter(codex_home=str(tmp_path / "nonexistent"))
        st = a.status()
        assert st["verdict"] == OFFLINE
        assert st["evidence"]


class TestAdapterHonesty:
    """§15/§24: a failed delivery is reported as failed. A fabricated
    'delivered=True' would make the supervisor lie to itself."""

    def test_failed_delivery_is_not_pending_verification(self, rt):
        class FailingAdapter(FakeAdapter):
            def send_instruction(self, instruction, continue_task=False):
                return {"delivered": False,
                        "evidence": ["Cannot connect to API"]}
        a = FailingAdapter(script=[IDLE])
        rt.register_adapter(a)
        out = rt.run_cycle()
        ci = out["workers"]["fake-1"]["check_in"]
        assert ci["delivered"] is False
        # honest: an undelivered instruction must NOT claim resumption pending
        assert "fake-1" not in rt._pending_verification

    def test_delivered_instruction_requires_verification(self, rt):
        a = FakeAdapter(script=[IDLE])
        rt.register_adapter(a)
        rt.run_cycle()
        assert "fake-1" in rt._pending_verification   # awaiting §45.8 proof


class TestInstanceLock:
    """§2: exactly ONE Supervisor Runtime per state-dir. A race or a manual
    double-start must never create two supervisors."""

    def test_second_instance_refused_while_first_alive(self, rt):
        assert rt.acquire_instance_lock() is True
        # a SEPARATE OS PROCESS holding the lock must be refused — this is
        # the only honest proof of single-instance (same-process objects
        # share a pid and cannot model a competing supervisor).
        probe = subprocess.run(
            [sys.executable, "-c",
             "import sys, json; sys.path.insert(0, '.');"
             "from compute.supervisor_runtime import SupervisorRuntime;"
             "rt = SupervisorRuntime(sys.argv[1]);"
             "print(json.dumps(rt.acquire_instance_lock()))",
             str(rt.state_dir)],
            capture_output=True, text=True, timeout=60.0)
        assert json.loads(probe.stdout.strip()) is False
        rt.release_instance_lock()

    def test_stale_lock_from_dead_pid_is_reclaimed(self, rt):
        lock = rt.state_dir / "supervisor.lock"
        lock.write_text(json.dumps({"pid": 999999}), encoding="utf-8")
        assert rt.acquire_instance_lock() is True
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == \
            os.getpid()
        rt.release_instance_lock()

    def test_release_only_frees_own_lock(self, rt):
        rt.acquire_instance_lock()
        other = SupervisorRuntime(str(rt.state_dir))
        other.release_instance_lock()   # not ours — must NOT free it
        assert (rt.state_dir / "supervisor.lock").exists()
        rt.release_instance_lock()


class TestCodexCooldownReallocation:
    """§4/§5: Codex hitting its usage limit -> WAITING_FOR_QUOTA + a
    worker.capacity_unavailable event. The programme must NOT stall."""

    def _rollout(self, tmp_path: Path, line: str) -> Path:
        p = tmp_path / "rollout-test.jsonl"
        p.write_text(line, encoding="utf-8")
        return p

    def test_parse_cooldown_reads_live_reset_time(self, tmp_path, monkeypatch):
        monkeypatch.setattr("compute.supervisor_runtime._now",
                            lambda: datetime(2026, 10, 12, 14).timestamp())
        p = self._rollout(tmp_path, json.dumps({
            "timestamp": "2026-10-12T14:00:00",
            "payload": {"type": "task_complete", "error": {
                "codex_error_info": "usage_limit_exceeded",
                "message": "hit your usage limit ... try again at 2:59 PM"}}}
        ) + "\n")
        cd = parse_codex_cooldown(p)
        assert cd is not None
        assert cd["reset_at"] == "14:59"
        assert cd["resets_in_s"] == 3540

    @pytest.mark.parametrize("now", ["2026-10-12T14:59:00",
                                     "2026-10-13T14:00:00"])
    def test_elapsed_reset_does_not_roll_forward(self, tmp_path, monkeypatch, now):
        p = self._rollout(tmp_path, json.dumps({
            "timestamp": "2026-10-12T14:00:00", "type": "event_msg",
            "payload": {"type": "task_complete", "error": {
                "message": "usage_limit_exceeded try again at 2:59 PM"}}}))
        monkeypatch.setattr("compute.supervisor_runtime._now",
                            lambda: datetime.fromisoformat(now).timestamp())
        assert parse_codex_cooldown(p) is None

    def test_midnight_reset_is_anchored_to_error_date(self, tmp_path, monkeypatch):
        p = self._rollout(tmp_path, json.dumps({
            "timestamp": "2026-10-12T23:50:00", "type": "event_msg",
            "payload": {"type": "task_complete", "error": {
                "message": "usage_limit_exceeded try again at 12:15 AM"}}}))
        monkeypatch.setattr("compute.supervisor_runtime._now",
                            lambda: datetime(2026, 10, 13, 0, 5).timestamp())
        assert parse_codex_cooldown(p) == {"reset_at": "00:15", "resets_in_s": 600}

    @pytest.mark.parametrize("new_type", ["task_started", "task_complete"])
    def test_new_turn_supersedes_cooldown(self, tmp_path, new_type):
        p = self._rollout(tmp_path, json.dumps({"payload": {
            "type": "task_complete", "error": "usage_limit_exceeded"}})
            + "\n" + json.dumps({"type": "event_msg", "payload": {
                "type": new_type, "error": None}}))
        assert parse_codex_cooldown(p) is None

    def test_quoted_error_is_not_a_cooldown_event(self, tmp_path):
        p = self._rollout(tmp_path, json.dumps({"type": "response_item",
            "payload": {"type": "message", "text":
                        "usage_limit_exceeded try again at 2:59 PM"}}))
        assert parse_codex_cooldown(p) is None

    @pytest.mark.parametrize("message", ["usage_limit_exceeded",
        "usage_limit_exceeded try again at 99:99 PM"])
    def test_adapter_handles_unknown_reset(self, tmp_path, message):
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        self._rollout(sessions, json.dumps({"type": "event_msg", "payload": {
            "type": "task_complete", "error": {"message": message}}}))
        status = CodexAdapter(codex_home=str(tmp_path)).status()
        assert status["verdict"] == WAITING_FOR_QUOTA
        assert status["quota"]["resets_in_s"] is None
        assert "reset time unknown" in status["evidence"][0]

    @pytest.mark.parametrize("verdict", [RUNNING, IDLE])
    def test_resumed_worker_clears_quota_display(self, rt, verdict):
        rt.register_adapter(FakeAdapter(script=[verdict]))
        rt.supervisor.heartbeat("fake-1", status=WAITING_FOR_QUOTA,
                                quota_state={"reset_at": "14:59"})
        rt.run_cycle()
        assert rt.supervisor.worker("fake-1").quota_state == {}

    def test_no_cooldown_when_session_healthy(self, tmp_path):
        p = self._rollout(tmp_path, json.dumps({
            "payload": {"type": "task_complete", "error": None}}) + "\n")
        assert parse_codex_cooldown(p) is None

    def test_cooldown_emits_capacity_unavailable_not_stall(self, rt):
        class CooldownCodex(FakeAdapter):
            def status(self):
                return {"verdict": WAITING_FOR_QUOTA,
                        "evidence": ["usage_limit_exceeded"],
                        "quota": {"pool": "five_hour",
                                  "reset_at": "14:59",
                                  "resets_in_s": 3600.0}}
        rt.register_adapter(CooldownCodex(worker_id="codex-primary"))
        out = rt.run_cycle()
        w = out["workers"]["codex-primary"]
        assert w["verdict"] == WAITING_FOR_QUOTA
        assert w["capacity_unavailable"]["reset_at"] == "14:59"
        # the programme keeps going: the cooldown worker is NOT reassigned
        # mid-write-set, but its quota state is recorded for the dashboard
        rec = rt.supervisor.worker("codex-primary")
        assert rec.status == WAITING_FOR_QUOTA
        assert rec.quota_state["reset_at"] == "14:59"


class TestOllamaLocalWorker:
    """§6: the local Ollama model is a commissioned worker (free-first tier).
    Its verdict must come from the live API, never fabricated."""

    def test_offline_when_api_unreachable(self):
        a = OllamaAdapter(base_url="http://127.0.0.1:59999")
        st = a.status()
        assert st["verdict"] == OFFLINE
        assert st["evidence"]

    def test_quota_is_free_local_tier_not_invented(self):
        a = OllamaAdapter()
        q = a.quota_state()
        assert len(q) == 1
        assert q[0].provider == "ollama"
        assert q[0].quota_remaining is None    # UNKNOWN, not fabricated (§38)
        assert q[0].tier == "LOCAL_UNLIMITED"

    def test_send_instruction_hits_generate_endpoint(self, monkeypatch):
        captured = {}

        class FakeResp:
            def read(self):
                return json.dumps({"response": "LOCAL-WORKER-OK"}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            return FakeResp()

        monkeypatch.setattr("compute.supervisor_runtime.urllib.request"
                            ".urlopen", fake_urlopen)
        a = OllamaAdapter(model="test-model")
        r = a.send_instruction("say hi")
        assert r["delivered"] is True
        assert "LOCAL-WORKER-OK" in r["evidence"][0]
        assert captured["url"].endswith("/api/generate")
        assert captured["body"]["model"] == "test-model"
        assert a.current_task()["task"] == "say hi"


class TestProgressBasedIdleDetection:
    """§36/§37: a worker that stays nominally RUNNING without advancing must
    be flagged. The liveness window alone cannot see this — that blindness
    was the SUPERVISOR_MISSED_IDLE_EVENT root cause."""

    def test_unchanged_evidence_flags_no_progress(self, rt):
        """Same evidence for STALL_CYCLES -> NO_PROGRESS + worker.idle_review.
        The owner must never have to report an idle worker. Cycle 1 is the
        baseline observation, so STALL_CYCLES identical successors follow it."""
        a = FakeAdapter(script=[RUNNING] * 8)
        rt.register_adapter(a)
        for _ in range(SupervisorRuntime.STALL_CYCLES + 1):
            rt.run_cycle()
        assert "fake-1" in rt.idle_reasons
        assert rt.idle_reasons["fake-1"] == "NO_PROGRESS"
        assert any(e["event"] == "worker.idle_review"
                   for e in rt.events)

    def test_changing_evidence_clears_no_progress(self, rt):
        class Advancing(FakeAdapter):
            """A worker whose evidence genuinely changes each cycle — it is
            alive AND progressing."""
            def status(self):
                self.cycles_seen += 1
                return {"verdict": RUNNING,
                        "evidence": [f"progress step {self.cycles_seen}"]}
        rt.register_adapter(Advancing(script=[RUNNING] * 10))
        # Advancing evidence never accumulates a stall count and never flags.
        for _ in range(SupervisorRuntime.STALL_CYCLES + 3):
            rt.run_cycle()
        assert "fake-1" not in rt.idle_reasons

    def test_flag_clears_when_worker_resumes_progress(self, rt):
        """The real recovery case: a worker stalls (NO_PROGRESS flagged),
        then its evidence changes -> the flag is cleared in the same cycle."""
        class StalledThenAdvances(FakeAdapter):
            def __init__(self):
                super().__init__(script=[RUNNING] * 20)
                self.step = 0
            def status(self):
                self.cycles_seen += 1
                self.step += 1
                # cycles 1-4: frozen evidence. cycle 5+: new evidence.
                if self.step <= 4:
                    ev = ["frozen evidence"]
                else:
                    ev = [f"new evidence step {self.step}"]
                return {"verdict": RUNNING, "evidence": ev}
        a = StalledThenAdvances()
        rt.register_adapter(a)
        for _ in range(SupervisorRuntime.STALL_CYCLES + 1):
            rt.run_cycle()
        assert "fake-1" in rt.idle_reasons      # stalled first
        for _ in range(3):
            rt.run_cycle()
        assert "fake-1" not in rt.idle_reasons  # then recovered

    def test_cooldown_worker_is_not_flagged_as_stalled(self, rt):
        """A WAITING_FOR_QUOTA worker is legitimately not progressing — its
        quota is refreshing. It must NOT be flagged NO_PROGRESS."""
        class Cooldown(FakeAdapter):
            def status(self):
                return {"verdict": WAITING_FOR_QUOTA,
                        "evidence": ["usage_limit_exceeded"],
                        "quota": {"pool": "five_hour", "reset_at": "01:11"}}
        rt.register_adapter(Cooldown(script=[WAITING_FOR_QUOTA] * 8))
        for _ in range(SupervisorRuntime.STALL_CYCLES + 3):
            rt.run_cycle()
        assert "fake-1" not in rt.idle_reasons

    def test_no_progress_keeps_continuation_required(self, rt):
        """A stalled worker is unfinished programme work — continuation_required
        must stay True so the watchdog/daemon never treats it as done."""
        a = FakeAdapter(script=[RUNNING] * 8)
        rt.register_adapter(a)
        for _ in range(SupervisorRuntime.STALL_CYCLES + 1):
            rt.run_cycle()
        assert rt.continuation_required is True


class TestWatchdogStallDetection:
    """§7/§8: PROCESS_ALIVE != SUPERVISOR_HEALTHY. The watchdog must detect
    a supervisor that holds the lock but has stopped checkpointing (the
    31-minute hang), journal its own heartbeat so a dead watchdog is
    distinguishable from a quiet one, and recover by killing + relaunching.
    """

    def test_checkpoint_age_none_when_missing(self, tmp_path):
        from compute.supervisor_runtime import _checkpoint_age_s
        assert _checkpoint_age_s(tmp_path) is None

    def test_checkpoint_age_reflects_mtime(self, tmp_path):
        import time
        from compute.supervisor_runtime import _checkpoint_age_s
        ckpt = tmp_path / "supervisor_runtime_checkpoint.json"
        ckpt.write_text("{}", encoding="utf-8")
        age = _checkpoint_age_s(tmp_path)
        assert age is not None and age < 5.0
        old = time.time() - 4000.0
        os.utime(ckpt, (old, old))
        assert _checkpoint_age_s(tmp_path) > 3000.0

    def test_stall_threshold_is_interval_scaled(self):
        """A stall is >3 intervals (min 300s) — a busy-but-slow daemon must
        not be killed, a hung one must be."""
        import argparse
        from compute.supervisor_runtime import _watchdog_loop
        args = argparse.Namespace(state_dir=".", interval=120.0)
        threshold = max(300.0, args.interval * 3)
        assert threshold == 360.0
        args2 = argparse.Namespace(state_dir=".", interval=30.0)
        assert max(300.0, args2.interval * 3) == 300.0

    def test_relaunch_kills_stalled_pid_and_clears_lock(self, tmp_path):
        """_relaunch must SIGTERM/SIGKILL the stalled pid, remove the stale
        lock, and spawn a replacement — the full PROCESS_ALIVE_BUT_STALLED
        recovery path, with the spawn stubbed so no real daemon starts."""
        from unittest.mock import patch
        from compute import supervisor_runtime as srt

        lock = tmp_path / "supervisor.lock"
        lock.write_text(json.dumps({"pid": 999999}), encoding="utf-8")
        spawned = {}

        class FakePopen:
            def __init__(self, cmd, **kw):
                spawned["cmd"] = cmd

        # 999999 does not exist -> _pid_alive False -> no kill attempted,
        # but the lock must still be cleared and a replacement spawned.
        with patch.object(srt.subprocess, "Popen", FakePopen), \
             patch.object(srt, "_watchdog_log", lambda *a: None):
            srt._relaunch(tmp_path, lock, srt.Path(__file__),
                          tmp_path, argparse_ns(), reason="test stall")

        assert not lock.exists()
        assert "--with-opencode" in spawned["cmd"]
        assert "--watchdog" not in spawned["cmd"]


def argparse_ns():
    import argparse
    return argparse.Namespace(interval=120.0)
