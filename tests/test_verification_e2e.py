"""v0.5 E2E: test-mapping/oracle calibration, multi-root, export (live files)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from runtime import AgentRuntime, RuntimeConfig
from tests.helpers import FakeProvider


class TestMappingOracleE2E(unittest.TestCase):
    def test_unrelated_pass_does_not_verify(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_mapor_"))
        try:
            (tmp / "core.py").write_text("def f():\n return 1\n")
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=10, non_interactive=True,
                               enable_reviewer=False)
            fake = FakeProvider([
                '{"action":"edit","path":"core.py","old":"return 1","new":"return 2"}',
                '{"action":"write","path":"test_other.py","content":"assert 1==1"}',
                '{"action":"test","command":"python test_other.py"}',
                '{"action":"finish","message":"ok"}'])
            out = run_bridge(cfg, "t", provider=fake)
            self.assertTrue(out.get("finished"), out)
            tr = out["task_result"]
            self.assertTrue(tr["tests"]["all_passed"])
            self.assertIn(tr["tests"]["quality"], ("WEAK", "SUSPICIOUS"))
            self.assertFalse(tr["tests"]["verified"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_relevant_test_improves_verdict(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_mapor2_"))
        try:
            (tmp / "core.py").write_text("def f():\n return 1\n")
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=12, non_interactive=True,
                               enable_reviewer=False)
            fake = FakeProvider([
                '{"action":"edit","path":"core.py","old":"return 1","new":"return 2"}',
                '{"action":"edit","path":"core.py","old":"return 2","new":"return 1"}',
                '{"action":"write","path":"test_core.py","content":"import core\\nassert core.f()==1\\nassert core.f()!=2"}',
                '{"action":"test","command":"python test_core.py"}',
                '{"action":"finish","message":"ok"}'])
            out = run_bridge(cfg, "t", provider=fake)
            tr = out["task_result"]
            self.assertEqual(tr["tests"]["quality"], "GOOD")
            self.assertTrue(tr["tests"]["verified"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMultiRootE2E(unittest.TestCase):
    def test_explicit_two_roots(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_mre2e_"))
        try:
            a, b = tmp / "A", tmp / "B"
            a.mkdir()
            b.mkdir()
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(a), str(b)],
                root_rules={str(b): {"allowed_modes": ["plan"]}}))
            sa = rt.create_session(str(a), mode="build")
            self.assertEqual(sa.mode, "build")
            with self.assertRaises(PermissionError):
                rt.create_session(str(b), mode="build")
            # global policy still enforced too: unknown root refused
            with self.assertRaises(PermissionError):
                rt.create_session(str(tmp), mode="plan")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestExportLive(unittest.TestCase):
    def test_export_files(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_exp_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = AgentRuntime(
                RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                provider_factory=lambda role: FakeProvider(
                    ['{"action":"write","path":"e.txt","content":"v"}',
                     '{"action":"finish","message":"ok"}']))
            s = rt.create_session(str(ws), mode="build")
            res = s.run_task("t", timeout=120)
            self.assertEqual(res.get("status"), "COMPLETED")
            js = json.loads(rt.export_result(s.session_id, fmt="json"))
            self.assertIn("scorecard", js)
            self.assertTrue(js["timeline"])
            md = rt.export_result(s.session_id, fmt="markdown")
            self.assertIn("Scorecard", md)
            jl = rt.export_result(s.session_id, fmt="jsonl")
            self.assertIn("task_result", jl)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
