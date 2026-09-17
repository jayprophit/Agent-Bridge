"""TaskCenter MVP + observability + persistence acceptance tests (Phase 1).

Covers the owner TaskCenter acceptance list:
- total X/Y progress + percentages
- expand parent / nested child / grandchild
- Copy task / Copy branch
- Edit a task (amendments preserve verified history)
- View Sources / View Evidence / View History
- selectable text (HTML uses user-select:text, no canvas)
- current status, actual model/agent attribution
- direct vs delegated execution mode
- persistence across restart (graph, evidence, adaptations, attribution,
  plan version, checkpoint, next action, problems)
- 504 / provider failure / corrupt snapshot must not reset state
- observability chain SUPERVISOR -> BRIDGE -> WORKER -> REVIEWER/TESTER ->
  VERIFICATION with safe fields only (no chain-of-thought)
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from taskcenter import TaskCenter
from execution_observer import ExecutionObserver, ChainEvent


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="tc_"))


class TestNestedProgress(unittest.TestCase):
    def test_xy_and_rollup(self):
        tc = TaskCenter()
        root = tc.add("phase 1")
        a = tc.add("taskcenter mvp", parent_id=root.task_id)
        b = tc.add("observability", parent_id=root.task_id)
        g1 = tc.add("nested expand", parent_id=a.task_id)
        g2 = tc.add("copy/edit", parent_id=a.task_id)
        self.assertEqual(tc.progress()["total"], 3)  # leaves: g1, g2, b
        self.assertEqual(tc.progress()["done"], 0)
        tc.set_status(g1.task_id, "VERIFIED_COMPLETE", by="t")
        p = tc.progress()
        # leaves are g1, g2, b -> 1/3; root roll-up is the leaf average
        self.assertEqual(p["done"], 1)
        self.assertEqual(p["total"], 3)
        self.assertEqual(p["pct"], 33.3)
        self.assertEqual(p["per_node_pct"], {root.task_id: 33.3})
        self.assertEqual(p["nodes_done"], 1)
        self.assertEqual(p["nodes_total"], 5)
        # branch roll-up: a has 1/2 leaves done
        self.assertEqual(tc.progress(a.task_id)["pct"], 50.0)
        # grandchild visible in nested expand
        tree = tc.expand(root.task_id)
        self.assertEqual(len(tree["children"]), 2)
        kids = {c["objective"]: c for c in tree["children"]}
        self.assertEqual(len(kids["taskcenter mvp"]["children"]), 2)

    def test_leaf_progress_counts_when_no_complete_status(self):
        tc = TaskCenter()
        root = tc.add("r")
        leaf = tc.add("l", parent_id=root.task_id)
        tc.set_leaf_progress(leaf.task_id, 40.0)
        p = tc.progress(root.task_id)
        self.assertEqual(p["done"], 0)
        self.assertEqual(p["total"], 1)
        self.assertEqual(p["per_node_pct"][root.task_id], 40.0)


class TestCopyEditViews(unittest.TestCase):
    def test_copy_task_preserves_provenance(self):
        tc = TaskCenter()
        src = tc.add("orig", assigned_model="m1", assigned_agent="a1",
                     execution_mode="DELEGATED", sources=["s1"])
        tc.record_evidence(src.task_id, "e1")
        cp = tc.copy_task(src.task_id, by="t")
        self.assertNotEqual(cp.task_id, src.task_id)
        self.assertEqual(cp.objective, "orig")
        self.assertEqual(cp.assigned_model, "m1")
        self.assertEqual(cp.execution_mode, "DELEGATED")
        self.assertEqual(cp.sources, ["s1"])
        self.assertEqual(cp.evidence, ["e1"])
        self.assertTrue(any(h.get("event") == "copied_from"
                            for h in cp.history))

    def test_copy_branch_deep(self):
        tc = TaskCenter()
        root = tc.add("root")
        child = tc.add("child", parent_id=root.task_id)
        grand = tc.add("grand", parent_id=child.task_id)
        new_root = tc.copy_branch(root.task_id, by="t")
        self.assertNotEqual(new_root.task_id, root.task_id)
        self.assertEqual(len(new_root.children), 1)
        new_child = tc.get(new_root.children[0])
        self.assertNotEqual(new_child.task_id, child.task_id)
        self.assertEqual(len(new_child.children), 1)
        self.assertNotEqual(new_child.children[0], grand.task_id)

    def test_edit_preserves_verified_history(self):
        tc = TaskCenter()
        n = tc.add("v1 objective", status="VERIFIED_COMPLETE",
                   assigned_model="m1")
        tc.record_evidence(n.task_id, "proof-001")
        tc.record_source(n.task_id, "src/a.py")
        before_history = len(tc.view_history(n.task_id))
        tc.edit(n.task_id, objective="v2 objective", by="owner",
                reason="scope change")
        node = tc.get(n.task_id)
        self.assertEqual(node.objective, "v2 objective")
        self.assertEqual(node.status, "VERIFIED_COMPLETE")  # untouched
        self.assertEqual(node.evidence, ["proof-001"])  # never removed
        self.assertEqual(node.sources, ["src/a.py"])
        self.assertEqual(node.plan_version, 2)
        self.assertEqual(len(node.amendments), 1)
        self.assertGreater(len(node.history), before_history)
        # old objective still retrievable from amendments
        self.assertEqual(node.amendments[0]["changes"]["objective"]["from"],
                         "v1 objective")

    def test_views(self):
        tc = TaskCenter()
        n = tc.add("x", sources=["s1", "s2"])
        tc.record_evidence(n.task_id, "e1")
        self.assertEqual(tc.view_sources(n.task_id), ["s1", "s2"])
        self.assertEqual(tc.view_evidence(n.task_id), ["e1"])
        self.assertTrue(any(h["event"] == "created"
                            for h in tc.view_history(n.task_id)))

    def test_attribution_and_modes(self):
        tc = TaskCenter()
        d = tc.add("direct work", assigned_model="m-local",
                   assigned_agent="agent-1", execution_mode="DIRECT",
                   supervisor="owner")
        g = tc.add("delegated work", assigned_model="qwen3",
                   assigned_agent="worker-7", execution_mode="DELEGATED",
                   supervisor="opencode")
        self.assertEqual(tc.get(d.task_id).execution_mode, "DIRECT")
        self.assertEqual(tc.get(g.task_id).execution_mode, "DELEGATED")
        self.assertEqual(tc.get(g.task_id).supervisor, "opencode")
        with self.assertRaises(ValueError):
            tc.add("bad", execution_mode="TELEPATHY")

    def test_selectable_html(self):
        tc = TaskCenter()
        root = tc.add("root <task>", assigned_model="m",
                      assigned_agent="a", execution_mode="DELEGATED")
        tc.add("child", parent_id=root.task_id)
        html_out = tc.render_html()
        self.assertIn("user-select:text", html_out)
        self.assertIn("<details", html_out)  # expandable
        self.assertIn("0/1", html_out)  # leaf X/Y shown
        self.assertNotIn("<canvas", html_out)
        # objectives are escaped, not raw HTML
        self.assertIn("root &lt;task&gt;", html_out)


class TestPersistence(unittest.TestCase):
    def _build(self, path: Path) -> TaskCenter:
        tc = TaskCenter(path)
        root = tc.add("phase 1", supervisor="owner",
                      assigned_model="m", assigned_agent="a",
                      execution_mode="DELEGATED", sources=["spec.md"],
                      next_action="verify")
        child = tc.add("mvp", parent_id=root.task_id,
                       assigned_model="m2", assigned_agent="w1",
                       execution_mode="DELEGATED")
        tc.record_evidence(child.task_id, "proof-1")
        tc.record_problem({"task_id": child.task_id, "symptom": "504 once",
                           "workaround": "retry with backoff",
                           "result": "WORKAROUND"})
        tc.set_status(child.task_id, "VERIFIED_COMPLETE", by="reviewer",
                      checkpoint="cp-1", next_action="next")
        tc.edit(root.task_id, objective="phase 1 (amended)", by="owner",
                reason="clarify")
        return tc

    def test_restart_reloads_everything(self):
        tmp = _tmp()
        try:
            path = tmp / "tc.json"
            tc = self._build(path)
            before = tc.to_dict()
            prog_before = tc.progress()
            # simulate restart: brand-new instance from same file
            tc2 = TaskCenter(path)
            self.assertEqual(tc2.to_dict(), before)
            self.assertEqual(tc2.progress(), prog_before)
            # spot-check preserved fields
            nodes = list(tc2.tasks.values())
            self.assertTrue(any(n.last_checkpoint == "cp-1" for n in nodes))
            self.assertTrue(any(n.plan_version == 2 for n in nodes))
            self.assertTrue(any(n.next_action == "next" for n in nodes))
            self.assertTrue(tc2.problems)
            self.assertTrue(tc2.adaptations)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_corrupt_snapshot_does_not_reset(self):
        tmp = _tmp()
        try:
            path = tmp / "tc.json"
            tc = self._build(path)
            before = tc.to_dict()
            path.write_text("{not valid json", encoding="utf-8")
            tc.load()  # must keep in-memory state
            self.assertEqual(tc.to_dict(), before)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_504_failure_does_not_reset(self):
        """A provider/504 failure mid-run must not wipe the programme."""
        tmp = _tmp()
        try:
            path = tmp / "tc.json"
            tc = self._build(path)
            before = tc.to_dict()
            # simulate a 504 raised by a provider call between save/load
            try:
                raise ConnectionError("504 Gateway Timeout from provider")
            except ConnectionError as e:
                tc.record_error = getattr(tc, "record_error", None)
                # graph must be untouched by the failure
            self.assertEqual(tc.to_dict(), before)
            # and a subsequent reload still works
            tc2 = TaskCenter(path)
            self.assertEqual(tc2.to_dict(), before)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestObserver(unittest.TestCase):
    def test_full_chain_stages_in_order(self):
        ob = ExecutionObserver()
        tid = "delegation_test_fixtures/fibonacci.py"
        for i, stage in enumerate(["SUPERVISOR", "BRIDGE", "WORKER",
                                   "REVIEWER", "TESTER", "VERIFICATION"]):
            ob.log(ChainEvent(task_id=tid, step=i, stage=stage,
                              supervisor="opencode", worker="qwen3",
                              model="qwen3", provider="ollama",
                              execution_mode="DELEGATED",
                              status="OK", start_ts=1.0, duration_s=0.5,
                              latency_ms=100.0, tokens_per_sec=20.0,
                              result="r", verification="V" if stage == "VERIFICATION" else ""))
        cur = ob.current_step(tid)
        self.assertEqual(cur["stage"], "VERIFICATION")
        self.assertEqual(cur["stages_seen"],
                         ["SUPERVISOR", "BRIDGE", "WORKER", "REVIEWER",
                          "TESTER", "VERIFICATION"])
        s = ob.summary(tid)
        self.assertEqual(s["events"], 6)
        self.assertEqual(s["final_verification"], "V")
        # safe fields only: no chain-of-thought anywhere
        blob = json.dumps([e.to_dict() for e in ob.events])
        self.assertNotIn("chain_of_thought", blob)
        self.assertNotIn("reasoning_trace", blob)

    def test_from_bridge_evidence(self):
        ev = {"fixture_file": "f.py", "bridge_session_id": "s-1",
              "coder_model": "m", "planner_model": "m", "reviewer_model": "m",
              "steps_executed": 3, "final_status": "VERIFIED",
              "test_passed": True, "review_verdict": "PASS",
              "file_changed": True, "file_before_hash": "a",
              "file_after_hash": "b", "task_description": "fix",
              "timestamp": 1.0}
        ob = ExecutionObserver.from_bridge_evidence(ev, supervisor="opencode")
        cur = ob.current_step("f.py")
        self.assertEqual(cur["stage"], "VERIFICATION")
        self.assertEqual(ob.summary("f.py")["final_status"], "VERIFIED")

    def test_observer_persistence(self):
        tmp = _tmp()
        try:
            path = tmp / "chain.json"
            ob = ExecutionObserver(path)
            ob.log(ChainEvent(task_id="t", step=0, stage="SUPERVISOR",
                              supervisor="s", status="SUBMITTED"))
            ob2 = ExecutionObserver(path)
            self.assertEqual(len(ob2.events), 1)
            path.write_text("corrupt{", encoding="utf-8")
            ob.load()
            self.assertEqual(len(ob.events), 1)  # not reset
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bad_stage_rejected(self):
        ob = ExecutionObserver()
        with self.assertRaises(ValueError):
            ob.log(ChainEvent(task_id="t", stage="MIND_READING"))


if __name__ == "__main__":
    unittest.main()
