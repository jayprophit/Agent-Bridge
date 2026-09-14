"""v0.9.0 task DAG tests (mocked; no I/O outside tmp)."""
import tempfile
import unittest
from pathlib import Path

from task_dag import (
    CheckpointManager,
    DurableTaskGraph,
    Evidence,
    EvidenceKind,
    EvidenceLedger,
    RecoveryManager,
    RetryPolicy,
    TaskBudget,
    TaskRecord,
    TaskStatus,
    WorkQueue,
    WorkerInfo,
    WorkerRegistry,
    make_handoff,
    make_handoff_result,
)


def _t(tid, deps=(), status="QUEUED"):
    return TaskRecord(task_id=tid, objective=tid, dependencies=list(deps),
                      status=TaskStatus(status))


class TestGraph(unittest.TestCase):
    def test_order_and_ready(self):
        g = DurableTaskGraph()
        g.add(_t("c", ["a", "b"]))
        g.add(_t("b", ["a"]))
        g.add(_t("a"))
        self.assertEqual([t.task_id for t in g.ordered()], ["a", "b", "c"])
        self.assertEqual([t.task_id for t in g.ready()], ["a"])
        g.get("a").status = TaskStatus.VERIFIED_COMPLETE
        self.assertEqual([t.task_id for t in g.ready()], ["b"])

    def test_cycle_rejected(self):
        g = DurableTaskGraph()
        g.add(_t("a", ["b"]))
        g.add(_t("b", ["a"]))
        with self.assertRaises(ValueError):
            g.ordered()

    def test_resume_state_skips_planned(self):
        g = DurableTaskGraph()
        g.add(_t("a", status="PLANNED"))
        b = _t("b", status="RUNNING")
        b.checkpoint = "ckpt-1"
        g.add(b)
        rs = g.resume_state()
        self.assertNotIn("a", rs)
        self.assertEqual(rs["b"]["checkpoint"], "ckpt-1")


class TestCheckpointRecovery(unittest.TestCase):
    def test_save_load_roundtrip(self):
        tmp = Path(tempfile.mkdtemp(prefix="v090_dag_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        g = DurableTaskGraph()
        t = _t("a", status="VERIFYING")
        t.checkpoint = "c1"
        g.add(t)
        ledger = EvidenceLedger()
        eid = ledger.add(Evidence(kind=EvidenceKind.FACT, producer="w",
                                  task_id="a", payload={"x": 1}))
        ledger.mark_verified(eid)
        mgr = CheckpointManager(tmp / "ckpt.json")
        saved = mgr.save(g, ledger)
        self.assertTrue(saved["ok"])
        g2, l2 = mgr.load()
        self.assertEqual(g2.get("a").checkpoint, "c1")
        self.assertTrue(l2.get(eid).verified)

    def test_recovery_plan(self):
        g = DurableTaskGraph()
        g.add(_t("done", status="VERIFIED_COMPLETE"))
        r = _t("run", status="RUNNING")
        r.checkpoint = "c9"
        g.add(r)
        g.add(_t("fail", status="FAILED"))
        plan = {p["task_id"]: p["action"] for p in RecoveryManager.plan_recovery(g)}
        self.assertNotIn("done", plan)
        self.assertIn("c9", plan["run"])
        self.assertIn("fail", plan)


class TestRetryBudget(unittest.TestCase):
    def test_retry_policy(self):
        p = RetryPolicy(max_retries=2, backoff_s=5.0)
        self.assertTrue(p.should_retry(1, "TIMEOUT"))
        self.assertFalse(p.should_retry(3, "TIMEOUT"))
        self.assertFalse(p.should_retry(1, "FATAL"))
        self.assertEqual(p.delay_for(2), 10.0)

    def test_budget_defaults(self):
        b = TaskBudget()
        self.assertEqual(b.retries, 2)


class TestLedgerQueueWorkers(unittest.TestCase):
    def test_confidence_is_not_verification(self):
        ledger = EvidenceLedger()
        eid = ledger.add(Evidence(kind=EvidenceKind.PROPOSAL, producer="m",
                                  task_id="t", confidence=0.99))
        self.assertEqual(ledger.verified_results("t"), [])
        self.assertTrue(ledger.mark_verified(eid))
        # proposals are never verified results even when marked
        self.assertEqual(ledger.verified_results("t"), [])
        eid2 = ledger.add(Evidence(kind=EvidenceKind.VERIFIED_RESULT,
                                   producer="v", task_id="t"))
        ledger.mark_verified(eid2)
        self.assertEqual(len(ledger.verified_results("t")), 1)

    def test_queue_lease(self):
        q = WorkQueue()
        q.push("a")
        q.push("b")
        self.assertEqual(q.claim(lease_s=100), "a")
        self.assertEqual(q.claim(lease_s=100), "b")
        self.assertIsNone(q.claim(lease_s=100))
        q.release("a")
        self.assertEqual(q.claim(lease_s=100), "a")

    def test_workers_available(self):
        reg = WorkerRegistry()
        reg.register(WorkerInfo(worker_id="w1", kind="native",
                                capabilities=["code"], state="IDLE"))
        reg.register(WorkerInfo(worker_id="w2", kind="native",
                                capabilities=["code"], state="BUSY"))
        self.assertEqual([w.worker_id for w in reg.available("code")], ["w1"])
        self.assertEqual(len(reg.available()), 1)


class TestHandoff(unittest.TestCase):
    def test_contracts(self):
        t = _t("t1")
        h = make_handoff(t)
        for key in ("task_id", "objective", "requirements", "dependencies",
                    "expected_outputs", "verification", "budget"):
            self.assertIn(key, h)
        r = make_handoff_result("t1", "COMPLETE", outputs={"a": 1})
        self.assertEqual(r["status"], "COMPLETE")
        self.assertIn("evidence", r)
        self.assertIn("handoff", r)


if __name__ == "__main__":
    unittest.main()
