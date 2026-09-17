"""Vertical slice: AutonomousLoop -> RuntimeStateTracker -> /v1/runtime payload.

Proves the Bridge-to-IDE data path end to end with real components: a loop
run feeds the tracker, and build_runtime_snapshot produces exactly the shape
TaskCenter polls (runtime.tasks with mapped statuses).
"""
import tempfile
import unittest
from pathlib import Path

from autonomous_loop import (AutonomousLoop, ExecResult, LoopConfig,
                             VerifyResult)
from ide_bridge import (RuntimeStateTracker, build_runtime_snapshot,
                        feed_loop_record)
from task_dag import AdaptiveTaskGraph, TaskRecord, TaskStatus


class VerticalSliceTests(unittest.TestCase):
    def test_loop_to_ide_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = AdaptiveTaskGraph()
            g.tasks["slice-a"] = TaskRecord(task_id="slice-a", objective="first slice",
                                            priority=0, status=TaskStatus.PLANNED)
            g.tasks["slice-b"] = TaskRecord(task_id="slice-b", objective="second slice",
                                            priority=1, status=TaskStatus.PLANNED)

            def executor(task, attempt):
                ok = not (task.task_id == "slice-b" and attempt == 1)
                return ExecResult(ok=ok, approach="direct",
                                  error="" if ok else "first try fails")

            loop = AutonomousLoop(
                g, executor,
                lambda task, res: VerifyResult(
                    achieved=res.ok, failures=[] if res.ok else [res.error]),
                LoopConfig(max_iterations=10, max_attempts_per_task=3,
                           checkpoint_path=str(Path(tmp) / "ckpt.json")))
            tracker = RuntimeStateTracker(
                snapshot_path=str(Path(tmp) / "runtime_snapshot.json"))

            report = loop.run()
            for rec in report.records:
                feed_loop_record(tracker, rec,
                                 objective=g.tasks[rec.task_id].objective)
            path = tracker.save()
            self.assertTrue(Path(path).exists())

            # Fresh tracker reloads the persisted snapshot (IDE poll path).
            reloaded = RuntimeStateTracker(snapshot_path=path)
            self.assertTrue(reloaded.load())
            snap = build_runtime_snapshot(None, reloaded)
            by_id = {t["task_id"]: t for t in snap["tasks"]}
            self.assertEqual(by_id["slice-a"]["status"], "VERIFIED_COMPLETE")
            self.assertEqual(by_id["slice-b"]["status"], "VERIFIED_COMPLETE")
            self.assertEqual(snap["progress_pct"], 100.0)
            self.assertEqual(len(snap["results"]), 2)
            # TaskCenter-mapped fields present.
            self.assertEqual(by_id["slice-a"]["objective"], "first slice")

    def test_blocked_and_gate_surface(self):
        tracker = RuntimeStateTracker()
        from autonomous_loop import IterationRecord
        feed_loop_record(tracker,
                         IterationRecord(task_id="b1", blocked="no upstream",
                                         approach="v1"))
        feed_loop_record(tracker,
                         IterationRecord(task_id="g1", gate="PUBLIC_RELEASE"))
        snap = build_runtime_snapshot(None, tracker)
        by_id = {t["task_id"]: t for t in snap["tasks"]}
        self.assertEqual(by_id["b1"]["status"], "BLOCKED")
        self.assertEqual(by_id["g1"]["status"], "AWAITING_OWNER")
        self.assertTrue(any(a.get("gate") == "PUBLIC_RELEASE"
                            for a in snap["approvals_pending"]))
        self.assertTrue(snap["errors"])


if __name__ == "__main__":
    unittest.main()
