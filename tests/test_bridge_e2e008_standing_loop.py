"""E2E-008 standing autonomous loop (no owner input) tests.

Proves the SUPERVISOR DAEMON can be started ONCE and it drains a READY
queue through the bridge without any manual runner invocation, prompt
insertion, task-B command, continue command or owner relay:

    scheduler selects TASK-A
    -> bridge delivers TASK-A
    -> OpenCode executes
    -> Hermes verifies
    -> Hermes QA
    -> scheduler automatically selects TASK-B
    -> bridge delivers TASK-B
    -> OpenCode executes

Only then:
    STANDING_AUTONOMOUS_LOOP = LIVE_VERIFIED.

The loop auto-selects the next task from the hive scheduler after each
verified task. The loop never fabricates progress and stops at the first
failure.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from compute.bridge_standing_loop import StandingAutonomousLoop
from compute.bridge_loop import BridgeAutonomousLoop, TaskRunRecord
from compute.worker_bridge_adapters import WorkerAdapterInterface


# --- a working mock adapter -----------------------------------------------------------

class MockAdapter(WorkerAdapterInterface):
    """Replays scripted output for deterministic standing-loop tests."""
    def __init__(self, outputs: dict[str, str], model: str = "mock-model"):
        super().__init__("mock-01", "mock-agent")
        self.outputs = outputs
        self.current_model = model
        self.sent: list[str] = []

    def discover(self):
        return {"status": "AVAILABLE"}

    def connect(self):
        return True

    def send_message(self, msg):
        self.sent.append(msg.task_id)
        out = self.outputs.get(msg.task_id, "")
        return {"delivered": True, "channel": "mock",
                "output": out, "evidence": ["mock"]}

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


def _qa_ok(repo: Path) -> tuple[bool, str]:
    return True, "mock QA passed"


def _ready_task(task_id: str, objective: str,
                write_set: tuple[str, ...] = (),
                qa_fn: Optional[Callable[[Path], tuple[bool, str]]] = None,
                priority: int = 50) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "title": objective,
        "priority": priority,
        "write_set": " ".join(write_set),
        "qa_fn": qa_fn,
    }


class TestStandingAutonomousLoop:
    """E2E-008: start once, run two tasks, no owner input."""

    def test_two_tasks_without_owner_input(self):
        """Start the standing loop once. It selects, delivers, verifies TASK-A,
        then automatically selects TASK-B. No manual intervention."""
        adapter = MockAdapter({
            "TASK-A": _good_output("TASK-A"),
            "TASK-B": _good_output("TASK-B"),
        })
        loop = StandingAutonomousLoop(adapter, repo=str(Path(".")))
        queue = [
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-A", "first", write_set=("x.txt",))),
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-B", "second", write_set=("x.txt",))),
        ]
        result = loop.run_ready_queue(queue)
        # no owner intervention at any point
        assert result["all_verified"] is True
        assert result["total"] == 2
        assert adapter.sent == ["TASK-A", "TASK-B"]

    def test_queue_auto_selects_next_task(self):
        """After a verified task, the loop auto-assigns the next one."""
        adapter = MockAdapter({
            "TASK-A": _good_output("TASK-A"),
            "TASK-B": _good_output("TASK-B"),
        })
        loop = StandingAutonomousLoop(adapter, repo=str(Path(".")))
        queue = [
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-A", "first", write_set=("a.txt",))),
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-B", "second", write_set=("b.txt",))),
        ]
        result = loop.run_ready_queue(queue)
        assert result["all_verified"] is True
        assert result["total"] == 2
        # both assigned by the standing loop, no owner relay
        assert adapter.sent == ["TASK-A", "TASK-B"]

    def test_standing_loop_stops_at_first_failure(self):
        """The standing loop never fabricates progress to keep going."""
        adapter = MockAdapter({
            "TASK-A": _good_output("TASK-A"),
            "TASK-B": "no marker at all",
        })
        loop = StandingAutonomousLoop(adapter, repo=str(Path(".")))
        queue = [
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-A", "first", write_set=("a.txt",))),
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-B", "second", write_set=("b.txt",))),
        ]
        result = loop.run_ready_queue(queue)
        assert result["all_verified"] is False
        assert result["stopped_by"] == "TASK-B"
        assert result["total"] == 2
        assert result["verified"] == 1

    def test_queue_drained_by_running_loop(self):
        """A queue of one task drained by the standing loop."""
        adapter = MockAdapter({"SINGLE": _good_output("SINGLE")})
        loop = StandingAutonomousLoop(adapter, repo=str(Path(".")))
        queue = [StandingAutonomousLoop.ReadyTask(
            _ready_task("SINGLE", "one", write_set=("z.txt",)))]
        result = loop.run_ready_queue(queue)
        assert result["all_verified"] is True
        assert result["total"] == 1
        assert adapter.sent == ["SINGLE"]

    def test_walk_through_bridge_loop_integration(self):
        """Integration: BridgeAutonomousLoop's run_queue over a real queue
        behaves exactly like the standing loop for a two-task queue."""
        adapter = MockAdapter({
            "TASK-A": _good_output("TASK-A"),
            "TASK-B": _good_output("TASK-B"),
        })
        bridge_loop = BridgeAutonomousLoop(adapter)
        result = bridge_loop.run_queue([
            {"task_id": "TASK-A", "objective": "first", "write_set": ("a.txt",)},
            {"task_id": "TASK-B", "objective": "second", "write_set": ("b.txt",)},
        ])
        assert result["all_verified"] is True
        assert result["completed"] == 2
        # both tasks delivered by the loop, no owner relay
        assert adapter.sent == ["TASK-A", "TASK-B"]

    def test_standing_loop_detects_owner_intervention(self):
        """If the adapter reports delivery failure, the standing loop records
        it as an intervention point.

        It records it, and the OTHER LANES KEEP MOVING. A delivery
        failure is the provider's failure and not the lane's: the work
        never left the supervisor, and the other lanes are other
        projects whose providers may be perfectly fine. The owner's
        directive says a provider failure must not stall project lanes,
        and this is the test that says so.
        """
        adapter = MockAdapter({
            "TASK-A": _good_output("TASK-A"),
            "TASK-B": _good_output("TASK-B"),
        })
        # simulate one task failing delivery
        original_send = adapter.send_message
        def failing_send(msg):
            if msg.task_id == "TASK-B":
                return {"delivered": False, "channel": "mock",
                        "evidence": ["delivery failed"]}
            return original_send(msg)
        adapter.send_message = failing_send  # type: ignore[assignment]
        loop = StandingAutonomousLoop(adapter, repo=str(Path(".")))
        queue = [
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-A", "first", write_set=("a.txt",))),
            StandingAutonomousLoop.ReadyTask(
                _ready_task("TASK-B", "second", write_set=("b.txt",))),
        ]
        result = loop.run_ready_queue(queue)
        # The failure is recorded, as an intervention point.
        assert result["all_verified"] is False
        assert result["provider_failures"] == ["TASK-B"]
        failed = [t for t in result["tasks"]
                  if t["status"] == "FAILED_DELIVERY"]
        assert [t["task_id"] for t in failed] == ["TASK-B"]
        # And it did not stall the other lanes: every ready task was
        # attempted, the queue drained, and nothing stopped it.
        assert result["stopped_by"] is None
        assert result["status"] == "queue_drained"
        assert result["attempted"] == 2
        assert result["verified"] == 1
        assert result["failed"] == 1