"""v0.4: runtime API — sessions, roots, lifecycle, idempotency, persistence."""
import shutil
import tempfile
import unittest
from pathlib import Path

from runtime import AgentRuntime, RuntimeConfig
from state import INTERRUPTED
from tests.helpers import FakeProvider


def _rt(tmp: Path, **kw) -> AgentRuntime:
    args = dict(allowed_workspace_roots=[str(tmp)])
    args.update(kw)
    return AgentRuntime(RuntimeConfig(**args))


def _factory(script, model="fake-m"):
    provs: dict[str, FakeProvider] = {}

    def make(role: str) -> FakeProvider:
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


class TestRoots(unittest.TestCase):
    def test_outside_roots_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_rt_"))
        try:
            rt = _rt(tmp)
            outside = Path(tempfile.mkdtemp(prefix="v04_out_"))
            try:
                with self.assertRaises(PermissionError):
                    rt.create_session(str(outside))
            finally:
                shutil.rmtree(outside, ignore_errors=True)
            with self.assertRaises(PermissionError):
                rt.create_session(str(tmp / ".." / "nope-x"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_inside_roots_ok(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_rt_"))
        try:
            rt = _rt(tmp)
            ws = tmp / "proj"
            ws.mkdir()
            s = rt.create_session(str(ws))
            self.assertTrue(s.session_id.startswith("s-"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSessionLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v04_sess_"))
        self.ws = self.tmp / "proj"
        self.ws.mkdir()
        self.rt = AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(self.tmp)]),
            provider_factory=_factory(['{"action":"write","path":"a.txt","content":"hi"}',
                                       '{"action":"finish","message":"done"}']))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_task_evidence_result(self):
        s = self.rt.create_session(str(self.ws), mode="build")
        res = s.run_task("t", timeout=120)
        self.assertEqual(res.get("status"), "COMPLETED")
        tr = res.get("task_result") or res
        self.assertIn("a.txt", (tr.get("files_created") or []))
        self.assertTrue((self.ws / "a.txt").exists())
        self.assertIn("task_id", res)

    def test_idempotent_submit(self):
        s = self.rt.create_session(str(self.ws), mode="build")
        t1 = s.submit_task("same text", idempotency_key="k1")
        t2 = s.submit_task("same text", idempotency_key="k1")
        self.assertEqual(t1, t2)
        self.assertTrue(s.last_submit_deduped)
        r = s.wait_task(t1, timeout=120)
        self.assertEqual(r.get("status"), "COMPLETED")
        # one execution only: single write in journal terms
        self.assertEqual((self.ws / "a.txt").read_text(), "hi")

    def test_different_text_same_key_runs(self):
        s = self.rt.create_session(str(self.ws), mode="build")
        t1 = s.submit_task("text one", idempotency_key="k")
        t2 = s.submit_task("text two", idempotency_key="k")
        self.assertNotEqual(t1, t2)

    def test_events_observable(self):
        s = self.rt.create_session(str(self.ws), mode="build")
        tid = s.submit_task("t")
        s.wait_task(tid, timeout=120)
        ev = s.events_since(0)
        kinds = {e.get("event", "") for e in ev["events"]}
        self.assertIn("task.started", kinds)
        self.assertIn("task.completed", kinds)

    def test_delete_session(self):
        s = self.rt.create_session(str(self.ws), mode="build")
        out = self.rt.delete_session(s.session_id)
        self.assertTrue(out["ok"])
        with self.assertRaises(KeyError):
            self.rt.get_session(s.session_id)


class TestPersistenceRecovery(unittest.TestCase):
    def test_interrupted_recovery(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_persist_"))
        try:
            ws = tmp / "proj"
            ws.mkdir()
            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                              provider_factory=_factory(
                                  ['{"action":"write","path":"a.txt","content":"x"}',
                                   '{"action":"finish","message":"ok"}']))
            s = rt.create_session(str(ws), mode="build")
            res = s.run_task("t", timeout=120)
            self.assertEqual(res.get("status"), "COMPLETED")
            snap = ws / ".bridge" / "sessions" / s.session_id / "session.json"
            self.assertTrue(snap.exists())
            # simulate restart: new runtime, recover
            rt2 = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]))
            s2 = rt2.load_session(s.session_id, str(ws))
            self.assertEqual(s2.status, INTERRUPTED)
            # completed action not repeated: resend same action id via bridge
            from executor import Executor
            ex = Executor(ws)
            first = ex.dispatch({"action": "write", "path": "z.txt", "content": "1"},
                                action_id="dup-1")
            self.assertTrue(first["ok"])
            again = ex.dispatch({"action": "write", "path": "z.txt", "content": "2"},
                                action_id="dup-1")
            self.assertTrue(again.get("dedup"))
            self.assertEqual((ws / "z.txt").read_text(), "1")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
