"""D4: action ids are unique per task, and idempotency compares full effects.

Found by the expanded workflow: two different directed tasks in one session
shared action ids (a-<sid>-<step>-<seq> restarted per task run), so the
executor's completed-record aliased the second write for the first and
reported SUCCEEDED without effect.

Two fixes, both proven here:
  A. next_action_id embeds the task id (uniqueness at the source).
  B. dispatch compares the recorded fingerprint, not just the verb
     (correctness even when an id repeats).
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from executor import Executor
from state import BridgeSession


class ActionIdUniqueness(unittest.TestCase):
    def test_ids_differ_across_tasks(self):
        first = BridgeSession("t1", "build", "AUTO_SAFE", "/tmp",
                              {}, session_id="s-1", task_id="t-aaa")
        second = BridgeSession("t2", "build", "AUTO_SAFE", "/tmp",
                               {}, session_id="s-1", task_id="t-bbb")
        self.assertNotEqual(first.next_action_id(), second.next_action_id())
        self.assertTrue(first.next_action_id().startswith("a-"))

    def test_ids_differ_across_runs(self):
        one = BridgeSession("t", "build", "AUTO_SAFE", "/tmp",
                            {}, session_id="s-1", task_id="t-aaa")
        two = BridgeSession("t", "build", "AUTO_SAFE", "/tmp",
                            {}, session_id="s-1", task_id="t-aaa")
        # same task twice (retry): ids restart, and that is exactly what the
        # fingerprint check below is for
        self.assertEqual(one.next_action_id(), two.next_action_id())


class ExecutorIdempotency(unittest.TestCase):
    def setUp(self):
        from aether_policy_bridge import issue_session_workspace_grants
        self.tmp = Path(tempfile.mkdtemp(prefix="d4_"))
        self.sid = "s-d4-test"
        issue_session_workspace_grants(self.sid, str(self.tmp), "AUTO_SAFE")
        self.ex = Executor(self.tmp, session_id=self.sid)

    def tearDown(self):
        from aether_policy_bridge import reset_policy_engine
        reset_policy_engine()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_different_actions_same_id_both_execute(self):
        r1 = self.ex.dispatch({"action": "write", "path": "a.txt",
                               "content": "one"}, action_id="x-1")
        self.assertTrue(r1["ok"], r1)
        r2 = self.ex.dispatch({"action": "write", "path": "b.txt",
                               "content": "two"}, action_id="x-1")
        self.assertTrue(r2["ok"], r2)
        self.assertNotIn("dedup", r2)
        self.assertEqual((self.tmp / "a.txt").read_text(), "one")
        self.assertEqual((self.tmp / "b.txt").read_text(), "two")

    def test_same_action_same_id_returns_recorded(self):
        action = {"action": "write", "path": "a.txt", "content": "one"}
        r1 = self.ex.dispatch(dict(action), action_id="x-2")
        self.assertTrue(r1["ok"], r1)
        (self.tmp / "a.txt").write_text("external", encoding="utf-8")
        r2 = self.ex.dispatch(dict(action), action_id="x-2")
        self.assertTrue(r2.get("dedup"), r2)
        # not re-executed: the external change survives
        self.assertEqual((self.tmp / "a.txt").read_text(), "external")

    def test_legacy_entry_without_fingerprint_executes_fresh(self):
        # Entries recorded before fingerprints existed (or forged without one)
        # must never suppress an execution: unknown provenance fails safe.
        self.ex.completed["old-1"] = {"ok": True, "executed": True}
        r = self.ex.dispatch({"action": "write", "path": "n.txt",
                              "content": "new"}, action_id="old-1")
        self.assertTrue(r["ok"], r)
        self.assertNotIn("dedup", r)
        self.assertTrue((self.tmp / "n.txt").exists())

    def test_returned_record_leaks_no_private_keys(self):
        action = {"action": "write", "path": "a.txt", "content": "one"}
        self.ex.dispatch(dict(action), action_id="x-3")
        r2 = self.ex.dispatch(dict(action), action_id="x-3")
        self.assertTrue(r2.get("dedup"))
        self.assertNotIn("_action_fingerprint", r2)
        stored = self.ex.completed["x-3"]
        self.assertIn("_action_fingerprint", stored)


class CrossTaskExecution(unittest.TestCase):
    """The exact D4 repro at runtime level: two different tasks, one session."""

    def test_two_tasks_in_one_session_both_take_effect(self):
        from runtime import AgentRuntime, RuntimeConfig
        from tests.helpers import FakeProvider

        tmp = Path(tempfile.mkdtemp(prefix="d4_rt_"))
        try:
            ws = tmp / "proj"
            ws.mkdir()

            def factory(script):
                def make(role: str) -> FakeProvider:
                    return FakeProvider(list(script), "fake-m")
                return make

            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                              provider_factory=factory(
                                  ['{"action":"write","path":"PLACEHOLDER","content":"x"}',
                                   '{"action":"finish","message":"done"}']))
            s = rt.create_session(str(ws), mode="build", approval="AUTO_SAFE")

            def run(name: str, content: str) -> dict:
                script = [f'{{"action":"write","path":"{name}","content":"{content}"}}',
                          '{"action":"finish","message":"done"}']
                s.provider_factory = factory(script)
                tid = s.submit_task(f"write {name}")
                return s.wait_task(tid, timeout=120)

            r1 = run("f1.txt", "one")
            r2 = run("f2.txt", "two")
            self.assertEqual(r1.get("status"), "COMPLETED", r1)
            self.assertEqual(r2.get("status"), "COMPLETED", r2)
            # Before the fix, the second task reported COMPLETED with no file.
            self.assertTrue(r2.get("effect_achieved"),
                            "second task must take real effect")
            self.assertEqual((ws / "f1.txt").read_text(), "one")
            self.assertEqual((ws / "f2.txt").read_text(), "two")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
