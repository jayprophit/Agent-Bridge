"""Autonomous loop: bounded units, verify-or-adapt, blocked-switch, owner gates."""
import json
import tempfile
import unittest
from pathlib import Path

from autonomous_loop import (AutonomousLoop, ExecResult, LoopConfig,
                             VerifyResult)
from task_dag import AdaptiveTaskGraph, TaskRecord, TaskStatus


def make_graph(*specs):
    g = AdaptiveTaskGraph()
    for tid, prio, deps, gate in specs:
        g.tasks[tid] = TaskRecord(task_id=tid, objective=f"obj {tid}",
                                  priority=prio, dependencies=list(deps),
                                  owner_gate=gate, status=TaskStatus.PLANNED)
    return g


def cfg(tmp, **kw):
    args = dict(max_iterations=20, max_attempts_per_task=3,
                checkpoint_path=str(Path(tmp) / "ckpt.json"))
    args.update(kw)
    return LoopConfig(**args)


class LoopTests(unittest.TestCase):
    def test_success_path_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("t1", 1, [], ""))
            loop = AutonomousLoop(
                g,
                lambda task, attempt: ExecResult(ok=True, output="done"),
                lambda task, res: VerifyResult(achieved=True),
                cfg(tmp))
            rec = loop.step()
            self.assertEqual(rec.stage, "VERIFIED")
            self.assertTrue(rec.verified)
            self.assertEqual(g.tasks["t1"].status, TaskStatus.VERIFIED_COMPLETE)

    def test_fail_diagnose_change_retest_then_pass(self):
        seen = []

        def executor(task, attempt):
            seen.append(attempt)
            return ExecResult(ok=attempt >= 2, approach=f"attempt-{attempt}",
                              error="" if attempt >= 2 else "boom")

        def verifier(task, res):
            return VerifyResult(achieved=res.ok,
                                failures=[] if res.ok else ["boom"])

        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("t1", 1, [], ""))
            loop = AutonomousLoop(g, executor, verifier, cfg(tmp))
            r1 = loop.step()
            self.assertEqual(r1.stage, "ADAPT")   # not a blind repeat
            r2 = loop.step()
            self.assertEqual(r2.stage, "VERIFIED")
            self.assertTrue(r2.adapted)
            self.assertEqual(seen, [1, 2])        # approach changed, then passed

    def test_attempt_budget_blocks_and_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("bad", 0, [], ""), ("good", 5, [], ""))
            loop = AutonomousLoop(
                g,
                lambda task, attempt: ExecResult(ok=False, error="always fails"),
                lambda task, res: VerifyResult(achieved=False, failures=["always fails"]),
                cfg(tmp, max_attempts_per_task=2))
            loop.step()   # ADAPT
            r = loop.step()  # BLOCKED (budget exhausted)
            self.assertEqual(r.stage, "BLOCKED")
            self.assertIn("bad", loop.report.blocked)
            r2 = loop.step()  # switches to the unblocked task, never retries bad
            self.assertEqual(r2.task_id, "good")

    def test_owner_gate_stops_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("pay", 0, [], "PAYMENT"), ("work", 5, [], ""))
            loop = AutonomousLoop(
                g,
                lambda task, attempt: ExecResult(ok=True),
                lambda task, res: VerifyResult(achieved=True),
                cfg(tmp))
            report = loop.run()
            # Runnable work completes first; the gate stops the loop without
            # the gated task ever executing.
            self.assertEqual(report.stopped, "OWNER_GATE")
            self.assertEqual(report.gate, "PAYMENT")
            self.assertIn("work", report.verified)
            self.assertNotIn("pay", report.verified)  # gate never executed

    def test_gate_alone_stops_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("pay", 0, [], "PAYMENT"))
            seen = []
            loop = AutonomousLoop(
                g,
                lambda task, attempt: seen.append(task.task_id) or ExecResult(ok=True),
                lambda task, res: VerifyResult(achieved=True),
                cfg(tmp))
            report = loop.run()
            self.assertEqual(report.stopped, "OWNER_GATE")
            self.assertEqual(seen, [])  # executor never invoked for gated task

    def test_priority_and_dependencies(self):
        order = []

        def executor(task, attempt):
            order.append(task.task_id)
            return ExecResult(ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("low", 5, [], ""), ("high", 0, [], ""),
                            ("dep", 0, ["high"], ""))
            loop = AutonomousLoop(g, executor,
                                  lambda task, res: VerifyResult(achieved=True),
                                  cfg(tmp))
            report = loop.run()
            self.assertEqual(report.stopped, "NO_UNBLOCKED_WORK")
            self.assertEqual(order, ["high", "dep", "low"])
            self.assertEqual(len(report.verified), 3)

    def test_checkpoint_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            ckpt = str(Path(tmp) / "ckpt.json")
            g = make_graph(("t1", 1, [], ""), ("t2", 2, [], ""))
            loop = AutonomousLoop(g,
                                  lambda task, attempt: ExecResult(ok=True),
                                  lambda task, res: VerifyResult(achieved=True),
                                  LoopConfig(checkpoint_path=ckpt))
            loop.step()
            snap = json.loads(Path(ckpt).read_text(encoding="utf-8"))
            self.assertIn("t1", snap["verified"])
            # New loop over a fresh graph resumes verified state.
            g2 = make_graph(("t1", 1, [], ""), ("t2", 2, [], ""))
            loop2 = AutonomousLoop(g2,
                                   lambda task, attempt: ExecResult(ok=True),
                                   lambda task, res: VerifyResult(achieved=True),
                                   LoopConfig(checkpoint_path=ckpt))
            self.assertEqual(g2.tasks["t1"].status, TaskStatus.VERIFIED_COMPLETE)
            rec = loop2.step()
            self.assertEqual(rec.task_id, "t2")

    def test_no_infinite_repeat_on_harness_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = make_graph(("t1", 1, [], ""))

            def bad_executor(task, attempt):
                raise RuntimeError("executor exploded")

            loop = AutonomousLoop(g, bad_executor,
                                  lambda task, res: VerifyResult(achieved=True),
                                  cfg(tmp, max_attempts_per_task=2, max_iterations=10))
            report = loop.run()
            self.assertIn(report.stopped, ("NO_UNBLOCKED_WORK",))
            self.assertIn("t1", loop.report.blocked)


if __name__ == "__main__":
    unittest.main()
