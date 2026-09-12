"""v0.6: milestone tracking + premature-finish gate."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from milestones import KNOWN, check
from tests.helpers import FakeProvider


class TestMilestoneCheck(unittest.TestCase):
    def test_empty_required_ok(self):
        ok, missing, nxt = check([], [])
        self.assertTrue(ok and not missing)

    def test_detects_missing(self):
        ok, missing, nxt = check([], ["tests_passed", "files_created"])
        self.assertFalse(ok)
        self.assertEqual(missing, ["tests_passed", "files_created"])
        self.assertTrue(nxt)

    def test_evidence_based(self):
        hist = [
            {"executed": True, "action": {"action": "write", "path": "a.py"},
             "result": {"ok": True}},
            {"executed": True, "action": {"action": "test", "command": "pytest"},
             "result": {"ok": True, "passed": True}},
            {"executed": True, "action": {"action": "shell", "command": "python a.py"},
             "result": {"ok": True, "stdout": "hi"}},
            {"executed": True, "action": {"action": "status"},
             "result": {"ok": True}},
        ]
        ok, missing, _ = check(hist, list(KNOWN))
        self.assertTrue(ok, missing)

    def test_unknown_ignored(self):
        ok, _, _ = check([], ["teleport"])
        self.assertTrue(ok)


class TestMilestoneGate(unittest.TestCase):
    def _cfg(self, tmp):
        return BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                            max_steps=10, non_interactive=True,
                            enable_reviewer=False)

    def test_premature_finish_refused(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_ms_"))
        try:
            fake = FakeProvider([
                '{"action":"finish","message":"done already"}',
                '{"action":"write","path":"a.py","content":"print(1)"}',
                '{"action":"test","command":"python a.py"}',
                '{"action":"finish","message":"done for real"}',
            ])
            out = run_bridge(self._cfg(tmp), "t", provider=fake,
                             required_milestones=["files_created", "tests_run"])
            self.assertTrue(out.get("finished"), out)
            kinds = [h.get("kind") for h in out["history"]]
            self.assertIn("MILESTONE_INCOMPLETE", kinds)
            self.assertTrue((tmp / "a.py").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_milestones_no_gate(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_ms2_"))
        try:
            fake = FakeProvider(['{"action":"finish","message":"done"}'])
            out = run_bridge(self._cfg(tmp), "t", provider=fake)
            self.assertTrue(out.get("finished"), out)
            self.assertNotIn("MILESTONE_INCOMPLETE",
                             [h.get("kind") for h in out["history"]])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
