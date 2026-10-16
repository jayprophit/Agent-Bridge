"""Bridge autonomous loop tests (§30).

Proves the loop's evidence gates: it never fabricates progress, stops on the
first missing-evidence step, auto-continues after a verified task, and
detects the missing-ACK case (SENT != ACKNOWLEDGED).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from compute.agent_message import Intent
from compute.bridge_loop import BridgeAutonomousLoop, TaskRunRecord
from compute.worker_bridge_adapters import WorkerAdapterInterface


# --- mock adapter ------------------------------------------------------------------

class MockAdapter(WorkerAdapterInterface):
    """Replays a scripted worker output for deterministic loop tests."""

    def __init__(self, outputs: dict[str, str], model: str = "mock-model"):
        super().__init__("mock-01", "mock-agent")
        self.outputs = outputs          # task_id -> scripted output
        self.current_model = model
        self.sent: list[str] = []

    def discover(self):
        return {"status": "AVAILABLE"}

    def connect(self):
        return True

    def send_message(self, msg):
        self.sent.append(msg.task_id)
        out = self.outputs.get(msg.task_id, "")
        return {"delivered": True, "channel": "mock", "output": out,
                "evidence": ["mock"]}

    def read_messages(self, limit=50):
        return []

    def acknowledge(self, msg):
        return f"ACK TASK_ID={msg.task_id}" in self.outputs.get(msg.task_id, "")

    def status(self):
        return {"status": "AVAILABLE"}

    def cancel(self):
        return True

    def pause(self):
        return True

    def resume(self):
        return True


def _good_output(task_id: str) -> str:
    return (
        f"**ACK TASK_ID={task_id}**\n"
        f"**TASK_START TASK_ID={task_id}**\n"
        f"created the file\n"
        f"**TASK_COMPLETE TASK_ID={task_id}**\n"
    )


def _qa_ok(repo: Path):
    return True, "mock QA passed"


# --- loop tests ---------------------------------------------------------------------

class TestAutonomousLoop:
    def test_full_task_verifies(self):
        adapter = MockAdapter({"T-1": _good_output("T-1")})
        loop = BridgeAutonomousLoop(adapter)
        rec = loop.run_task("T-1", "do the thing")
        assert rec.ok is True
        assert rec.outcome == "verified"
        steps = {s.step for s in rec.steps}
        assert "ack_received" in steps
        assert "task_start" in steps
        assert "task_complete" in steps

    def test_missing_ack_stops_loop(self):
        """SENT != ACKNOWLEDGED: no ACK marker → task fails, nothing fabricated."""
        adapter = MockAdapter({"T-1": "worker said hello, no marker"})
        loop = BridgeAutonomousLoop(adapter)
        rec = loop.run_task("T-1", "do the thing")
        assert rec.ok is False
        assert rec.outcome == "failed_before_ack"

    def test_missing_start_inferred_from_ack_delivery(self):
        """START can be inferred from ACK + successful delivery (no explicit marker needed)."""
        adapter = MockAdapter({"T-1": f"**ACK TASK_ID=T-1**\n(no start marker)"})
        loop = BridgeAutonomousLoop(adapter)
        rec = loop.run_task("T-1", "do the thing")
        # START is inferred from ACK + delivery, but COMPLETE fails (no marker)
        # The task fails at COMPLETE step, not START
        assert rec.outcome == "qa_or_evidence_failed"
        start_step = next(s for s in rec.steps if s.step == "task_start")
        assert start_step.passed is True
        assert "inferred" in start_step.evidence.lower()

    def test_missing_complete_defers_to_write_set_qa(self):
        """COMPLETE missing doesn't fail immediately — defers to write-set + QA."""
        adapter = MockAdapter({
            "T-1": "**ACK TASK_ID=T-1**\n**TASK_START TASK_ID=T-1**\n(no complete)"})
        loop = BridgeAutonomousLoop(adapter)
        rec = loop.run_task("T-1", "do the thing")
        # COMPLETE step fails (no marker) but doesn't stop the loop
        # Final outcome depends on write-set + QA (both pass here since none declared)
        assert rec.outcome == "qa_or_evidence_failed"
        complete_step = next(s for s in rec.steps if s.step == "task_complete")
        assert complete_step.passed is False
        assert "inferred" in complete_step.evidence.lower()

    def test_queue_auto_continues(self):
        """§30: after a verified task, the loop auto-assigns the next one."""
        adapter = MockAdapter({
            "T-1": _good_output("T-1"),
            "T-2": _good_output("T-2"),
        })
        loop = BridgeAutonomousLoop(adapter)
        result = loop.run_queue([
            {"task_id": "T-1", "objective": "first"},
            {"task_id": "T-2", "objective": "second"},
        ])
        assert result["all_verified"] is True
        assert result["completed"] == 2
        assert adapter.sent == ["T-1", "T-2"]   # both assigned, no owner relay

    def test_queue_stops_at_first_failure(self):
        """The loop never fabricates progress to keep going."""
        adapter = MockAdapter({
            "T-1": _good_output("T-1"),
            "T-2": "no marker at all",
        })
        loop = BridgeAutonomousLoop(adapter)
        result = loop.run_queue([
            {"task_id": "T-1", "objective": "first"},
            {"task_id": "T-2", "objective": "second"},
        ])
        assert result["all_verified"] is False
        assert result["stopped_at"] == "T-2"
        assert result["completed"] == 1

    def test_qa_failure_recorded(self):
        """Independent QA failure marks the task unverified."""
        adapter = MockAdapter({"T-1": _good_output("T-1")})
        loop = BridgeAutonomousLoop(adapter)
        rec = loop.run_task(
            "T-1", "objective",
            qa_fn=lambda repo: (False, "QA re-run failed"))
        assert rec.ok is False
        assert rec.qa_passed is False

    def test_write_set_evidence(self, tmp_path):
        """Real file evidence: the declared write-set files must exist."""
        (tmp_path / "out.txt").write_text("done")
        adapter = MockAdapter({"T-1": _good_output("T-1")})
        loop = BridgeAutonomousLoop(adapter, repo=str(tmp_path))
        rec = loop.run_task("T-1", "objective", write_set=("out.txt",))
        assert rec.files_found == ("out.txt",)
        assert rec.ok is True

    def test_missing_write_set_file_detected(self, tmp_path):
        adapter = MockAdapter({"T-1": _good_output("T-1")})
        loop = BridgeAutonomousLoop(adapter, repo=str(tmp_path))
        rec = loop.run_task("T-1", "objective", write_set=("missing.txt",))
        assert rec.ok is False
        assert rec.files_found == ()

    def test_record_serialisable(self):
        adapter = MockAdapter({"T-1": _good_output("T-1")})
        loop = BridgeAutonomousLoop(adapter)
        loop.run_task("T-1", "objective")
        d = loop.records[0].to_dict()
        assert d["task_id"] == "T-1"
        assert isinstance(d["steps"], list)
        assert all("step" in s and "passed" in s for s in d["steps"])
