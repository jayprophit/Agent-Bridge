"""MIGRATED from v0.2 tests/test_modes_approval.py — must pass in v0.3."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from tests.helpers import FakeProvider


def make_cfg(workspace: Path, mode: str = "build", approval: str = "AUTO_SAFE",
             **kw) -> BridgeConfig:
    args = dict(workspace=workspace, mode=mode, approval=approval,
                max_steps=8, non_interactive=True, enable_reviewer=False)
    args.update(kw)
    return BridgeConfig(**args)


class TestModes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v02_mode_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plan_cannot_mutate(self):
        cfg = make_cfg(self.tmp, mode="plan")
        fake = FakeProvider([
            '{"action":"write","path":"evil.txt","content":"x"}',
            '{"action":"list","path":"."}',
            '{"action":"finish","message":"planned"}',
        ])
        out = run_bridge(cfg, "plan test", provider=fake)
        self.assertTrue(out["finished"], out)
        self.assertFalse((self.tmp / "evil.txt").exists())
        self.assertTrue(any(h.get("note", "") == "NOT EXECUTED (plan mode)"
                            for h in out["history"]))

    def test_build_can_mutate(self):
        cfg = make_cfg(self.tmp, mode="build")
        fake = FakeProvider([
            '{"action":"write","path":"ok.txt","content":"hi"}',
            '{"action":"finish","message":"built"}',
        ])
        out = run_bridge(cfg, "build test", provider=fake)
        self.assertTrue(out["finished"], out)
        self.assertTrue((self.tmp / "ok.txt").exists())

    def test_hybrid_functions(self):
        cfg = make_cfg(self.tmp, mode="hybrid")
        fake = FakeProvider([
            '{"action":"list","path":"."}',
            '{"action":"write","path":"h.txt","content":"v"}',
            '{"action":"finish","message":"hybrid done"}',
        ])
        out = run_bridge(cfg, "hybrid test", provider=fake)
        self.assertTrue(out["finished"], out)
        self.assertTrue((self.tmp / "h.txt").exists())


class TestApprovals(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v02_appr_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_read_only_denies_writes(self):
        cfg = make_cfg(self.tmp, mode="build", approval="READ_ONLY")
        fake = FakeProvider([
            '{"action":"write","path":"x.txt","content":"x"}',
            '{"action":"write","path":"x.txt","content":"x"}',
            '{"action":"write","path":"x.txt","content":"x"}',
            '{"action":"finish","message":"should not reach"}',
        ])
        out = run_bridge(cfg, "t", provider=fake)
        self.assertFalse((self.tmp / "x.txt").exists())
        denied = [h for h in out["history"] if h.get("kind") == "APPROVAL_DENIED"]
        self.assertTrue(denied)

    def test_ask_all_writes_noninteractive_denies(self):
        cfg = make_cfg(self.tmp, mode="build", approval="ASK_ALL_WRITES")
        fake = FakeProvider([
            '{"action":"write","path":"y.txt","content":"y"}',
            '{"action":"write","path":"y.txt","content":"y"}',
            '{"action":"write","path":"y.txt","content":"y"}',
            '{"action":"finish","message":"x"}',
        ])
        out = run_bridge(cfg, "t", provider=fake)
        self.assertFalse((self.tmp / "y.txt").exists())

    def test_auto_safe_denies_delete_noninteractive(self):
        (self.tmp / "victim.txt").write_text("keep", encoding="utf-8")
        cfg = make_cfg(self.tmp, mode="build", approval="AUTO_SAFE")
        fake = FakeProvider([
            '{"action":"delete","path":"victim.txt"}',
            '{"action":"delete","path":"victim.txt"}',
            '{"action":"delete","path":"victim.txt"}',
            '{"action":"finish","message":"x"}',
        ])
        out = run_bridge(cfg, "t", provider=fake)
        self.assertTrue((self.tmp / "victim.txt").exists())


if __name__ == "__main__":
    unittest.main()
