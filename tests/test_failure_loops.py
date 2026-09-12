"""MIGRATED from v0.2 tests/test_failure_loops.py — must pass in v0.3."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from errors import (APPROVAL_DENIED, MODEL_OUTPUT_ERROR, FailureTracker,
                    MAX_STEPS_REACHED)
from tests.helpers import FakeProvider


class TestFailureTracker(unittest.TestCase):
    def test_threshold(self):
        ft = FailureTracker(repeat_threshold=3)
        self.assertEqual(ft.note("a"), 1)
        self.assertEqual(ft.note("a"), 2)
        self.assertFalse(ft.exceeded())
        self.assertEqual(ft.note("a"), 3)
        self.assertTrue(ft.exceeded())
        ft.note_success()
        self.assertFalse(ft.exceeded())

    def test_distinct_resets(self):
        ft = FailureTracker(repeat_threshold=2)
        ft.note("a")
        ft.note("b")
        self.assertFalse(ft.exceeded())


class TestBridgeLoops(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v02_fail_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cfg(self, **kw):
        args = dict(workspace=self.tmp, mode="build", approval="AUTO_SAFE",
                    max_steps=8, non_interactive=True, enable_reviewer=False)
        args.update(kw)
        return BridgeConfig(**args)

    def test_repeated_garbage_terminates(self):
        cfg = self._cfg()
        fake = FakeProvider(["not json at all"] * 8)
        out = run_bridge(cfg, "t", provider=fake)
        self.assertFalse(out.get("finished", False))
        self.assertEqual(out.get("kind"), MODEL_OUTPUT_ERROR)
        self.assertLessEqual(fake.calls, 3)

    def test_max_steps(self):
        cfg = self._cfg(max_steps=3)
        fake = FakeProvider(['{"action":"list","path":"."}'] * 10)
        out = run_bridge(cfg, "t", provider=fake)
        self.assertEqual(out.get("kind"), MAX_STEPS_REACHED)
        self.assertEqual(out["steps"], 3)

    def test_alternating_failures_terminates(self):
        cfg = self._cfg(max_steps=20)
        (self.tmp / "f.txt").write_text("hello", encoding="utf-8")
        script = []
        for _ in range(10):
            script.append('{"action":"edit","path":"f.txt","old":"ZZZ","new":"Y"}')
            script.append('{"action":"patch","path":"f.txt","old":"ZZZ","new":"Y"}')
        fake = FakeProvider(script)
        out = run_bridge(cfg, "t", provider=fake)
        self.assertFalse(out.get("finished", False))
        self.assertLess(fake.calls, 20)


if __name__ == "__main__":
    unittest.main()
