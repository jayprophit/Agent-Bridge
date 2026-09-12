"""v0.5: quotas, multi-root policy, human gate, revision requests, inventory,
history, diagnostics/self-check, SSE, session evidence endpoints."""
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from runtime import AgentRuntime, RuntimeConfig
from service import serve
from tests.helpers import FakeProvider


def _factory(script, model="fake-m"):
    provs: dict[str, FakeProvider] = {}

    def make(role: str) -> FakeProvider:
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


def _rt(tmp: Path, **kw) -> AgentRuntime:
    args = dict(allowed_workspace_roots=[str(tmp)])
    args.update(kw)
    return AgentRuntime(RuntimeConfig(**args))


OK_SCRIPT = ['{"action":"write","path":"a.txt","content":"hi"}',
             '{"action":"finish","message":"done"}']


class TestQuotas(unittest.TestCase):
    def test_max_active_sessions(self):
        import time as _t

        class SlowProvider(FakeProvider):
            def chat(self, messages, temperature=0.1, num_predict=640):
                _t.sleep(30)
                return '{"action":"finish","message":"slow"}'

        tmp = Path(tempfile.mkdtemp(prefix="v05_q_"))
        try:
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)],
                quotas={"max_active_sessions": 1, "max_active_tasks": 8,
                        "max_actions_per_task": 32, "max_events_retained": 100,
                        "max_export_bytes": 100000}),
                provider_factory=lambda role: SlowProvider([]))
            ws = tmp / "w"
            ws.mkdir()
            s1 = rt.create_session(str(ws))
            t1 = s1.submit_task("long " + "x" * 10)
            _t.sleep(1.0)  # worker picked it up and is blocked in chat
            with self.assertRaises(ValueError):
                rt.create_session(str(ws))
            s1.cancel_task(t1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bad_quota_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_q2_"))
        try:
            with self.assertRaises(ValueError):
                _rt(tmp, quotas={"max_active_sessions": 0, "max_active_tasks": 1,
                                 "max_actions_per_task": 1, "max_events_retained": 1,
                                 "max_export_bytes": 1})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMultiRoot(unittest.TestCase):
    def test_plan_only_root_rejects_build(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_mr_"))
        try:
            a, b = tmp / "A", tmp / "B"
            a.mkdir()
            b.mkdir()
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)],
                root_rules={str(b): {"allowed_modes": ["plan"]}}))
            s = rt.create_session(str(a), mode="build")
            self.assertEqual(s.mode, "build")
            with self.assertRaises(PermissionError):
                rt.create_session(str(b), mode="build")
            sp = rt.create_session(str(b), mode="plan")
            self.assertEqual(sp.mode, "plan")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_root_cannot_weaken_global(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_mr2_"))
        try:
            with self.assertRaises(ValueError):
                AgentRuntime(RuntimeConfig(
                    allowed_workspace_roots=[str(tmp)],
                    default_approval="ASK_ALL_WRITES",
                    root_rules={str(tmp): {"allowed_approval": "AUTO_SAFE"}}))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_root_can_restrict(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_mr3_"))
        try:
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)],
                default_approval="AUTO_SAFE",
                root_rules={str(tmp): {"allowed_approval": "READ_ONLY"}}))
            with self.assertRaises(PermissionError):
                rt.create_session(str(tmp), mode="build", approval="AUTO_SAFE")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestHumanGate(unittest.TestCase):
    def _rt_gate(self, tmp: Path, gate: str, timeout: int = 20):
        return AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(tmp)], human_gate=gate,
                          gate_timeout_s=timeout),
            provider_factory=_factory(list(OK_SCRIPT)))

    def test_accept_completes(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_gate_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = self._rt_gate(tmp, "BEFORE_COMPLETE")
            s = rt.create_session(str(ws), mode="build")
            tid = s.submit_task("t")
            end = time.time() + 60
            while time.time() < end:
                if getattr(s, "_gate", None):
                    break
                time.sleep(0.5)
            self.assertIsNotNone(getattr(s, "_gate", None))
            out = s.resolve_final(tid, "accept")
            self.assertTrue(out["ok"])
            res = s.wait_task(tid, timeout=60)
            self.assertEqual(res.get("status"), "COMPLETED")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_timeout_never_auto_accepts(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_gate2_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = self._rt_gate(tmp, "ALWAYS", timeout=3)
            s = rt.create_session(str(ws), mode="build")
            res = s.run_task("t", timeout=60)
            self.assertEqual(res.get("status"), "FAILED")
            self.assertIn("never auto-accepted", res.get("finished_reason", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_revise_spawns_linked_child(self):
        import threading
        tmp = Path(tempfile.mkdtemp(prefix="v05_gate3_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = self._rt_gate(tmp, "BEFORE_COMPLETE", timeout=60)
            s = rt.create_session(str(ws), mode="build")
            tid = s.submit_task("t")
            end = time.time() + 60
            while time.time() < end:
                if getattr(s, "_gate", None):
                    break
                time.sleep(0.5)
            self.assertIsNotNone(getattr(s, "_gate", None))
            out = s.resolve_final(tid, "revise", "add more checks")
            self.assertTrue(out["ok"])
            res = s.wait_task(tid, timeout=60)
            self.assertEqual(res.get("status"), "CANCELLED")
            self.assertIn("revision", res.get("finished_reason", ""))
            children = [t for t, r in s.tasks.items()
                        if getattr(r, "parent_task_id", "") == tid]
            self.assertEqual(len(children), 1)
            cres = s.wait_task(children[0], timeout=120)
            self.assertIn(cres.get("status"), ("COMPLETED", "FAILED"))
            # original task text untouched by the revision
            self.assertEqual(s.tasks[tid].text, "t")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cancel_long_task(self):
        import time as _t

        class SlowProvider(FakeProvider):
            def chat(self, messages, temperature=0.1, num_predict=640):
                _t.sleep(60)
                return '{"action":"finish","message":"slow"}'

        tmp = Path(tempfile.mkdtemp(prefix="v05_cancel_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                              provider_factory=lambda role: SlowProvider([]))
            s = rt.create_session(str(ws), mode="build")
            tid = s.submit_task("long task")
            _t.sleep(1.0)
            out = s.cancel_task(tid)
            self.assertEqual(out["status"], "CANCELLED")
            # no new actions afterward: journal stays empty of task files
            _t.sleep(1.0)
            self.assertEqual([p.name for p in ws.iterdir()
                              if not p.name.startswith(".bridge")], [])
            evs = [e.get("event") for e in s.events_since(0)["events"]]
            self.assertIn("task.cancelled", evs)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_user_revision_links(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_rev_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                              provider_factory=_factory(list(OK_SCRIPT)))
            s = rt.create_session(str(ws), mode="build")
            res = s.run_task("t", timeout=120)
            tid = res.get("task_id", "")
            if not tid:
                tids = list(s.tasks)
                self.assertTrue(tids)
                tid = tids[0]
            child = s.request_revision(tid, "Add tests")
            self.assertNotEqual(child, tid)
            self.assertEqual(s.tasks[child].parent_task_id, tid)
            orig = s.tasks[tid].text
            s.wait_task(child, timeout=120)
            self.assertEqual(s.tasks[tid].text, orig)  # history untouched
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestInventoryHistoryDiag(unittest.TestCase):
    def test_inventory_shape(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_inv_"))
        try:
            rt = _rt(tmp)
            inv = rt.model_inventory()
            self.assertIn("models", inv)
            self.assertTrue(inv["models"])
            m = inv["models"][0]
            for k in ("name", "availability", "kind"):
                self.assertIn(k, m)
            self.assertNotIn("path", json.dumps(m).lower())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_history_filters(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_hist_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                              provider_factory=_factory(list(OK_SCRIPT)))
            s = rt.create_session(str(ws), mode="build")
            s.run_task("t", timeout=120)
            all_s = rt.list_sessions()
            self.assertEqual(len(all_s), 1)
            self.assertEqual(len(rt.list_sessions(status="COMPLETED")), 1)
            self.assertEqual(rt.list_sessions(status="FAILED"), [])
            by_ws = rt.list_sessions(workspace=str(ws))
            self.assertEqual(len(by_ws), 1)
            self.assertEqual(rt.list_sessions(workspace=str(tmp)), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_diagnostics_selfcheck(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_diag_"))
        try:
            rt = _rt(tmp)
            d = rt.diagnostics()
            self.assertIn("health", d)
            self.assertNotIn("secret", json.dumps(d).lower())
            checks = {c["check"]: c["status"] for c in rt.self_check()}
            for name in ("config", "storage", "allowed_roots", "ollama",
                         "models", "event_system", "sandbox", "persistence"):
                self.assertIn(name, checks)
            self.assertNotIn("FAIL", set(checks.values()),
                             f"self-check failed: {checks}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSessionEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v05_ev_"))
        self.ws = self.tmp / "w"
        self.ws.mkdir()
        self.rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(self.tmp)]),
                               provider_factory=_factory(list(OK_SCRIPT)))
        self.s = self.rt.create_session(str(self.ws), mode="build")
        res = self.s.run_task("t", timeout=120)
        assert res.get("status") == "COMPLETED", res

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_diff_manifest_scorecard_timeline(self):
        d = self.rt.session_diff(self.s.session_id)
        self.assertIn("a.txt", d.get("diff", ""))
        m = self.rt.session_manifest(self.s.session_id)
        self.assertTrue(any(c["path"] == "a.txt" for c in m["changes"]))
        self.assertFalse(any(c["path"].startswith(".bridge") for c in m["changes"]))
        sc = self.rt.session_scorecard(self.s.session_id)
        self.assertIn("FILES", sc["scorecard"]["categories"])
        tl = self.rt.session_timeline(self.s.session_id)
        self.assertTrue(len(tl["timeline"]) > 2)

    def test_export_redacted(self):
        js = self.rt.export_result(self.s.session_id, fmt="json")
        self.assertIn("a.txt", js)
        self.assertNotIn(".bridge/memory", js)
        md = self.rt.export_result(self.s.session_id, fmt="markdown")
        self.assertIn("Scorecard", md)


if __name__ == "__main__":
    unittest.main()
