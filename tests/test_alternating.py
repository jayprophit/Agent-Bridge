"""v0.4: alternating-pattern loop detection (unit + live bridge E2E)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import AlternatingDetector, run_bridge
from config import BridgeConfig
from tests.helpers import FakeProvider


class TestAlternatingDetector(unittest.TestCase):
    def test_abab_detected(self):
        d = AlternatingDetector()
        a = {"action": "edit", "path": "f"}
        b = {"action": "test", "command": "python f"}
        self.assertIsNone(d.note(a, False))
        self.assertIsNone(d.note(b, False))
        self.assertIsNone(d.note(a, False))
        r = d.note(b, False)
        self.assertIsNone(r)  # first full cycle: strike 1
        d.note(a, False)
        d.note(b, False)
        d.note(a, False)
        r2 = d.note(b, False)
        self.assertIsNotNone(r2)
        self.assertIn("alternating", r2)

    def test_oscillation_detected(self):
        d = AlternatingDetector()
        acts = [{"action": "write", "path": f"f{i}"} for i in range(8)]
        oks = [True, False] * 4
        out = None
        for a, ok in zip(acts, oks):
            out = d.note(a, ok)
        self.assertIsNotNone(out)
        self.assertIn("oscillation", out)

    def test_progress_resets(self):
        d = AlternatingDetector()
        a = {"action": "edit", "path": "f"}
        b = {"action": "test", "command": "t"}
        for _ in range(2):
            d.note(a, False)
            d.note(b, False)
        d.reset_progress()
        self.assertIsNone(d.note(a, False))
        self.assertIsNone(d.note(b, False))


class TestAlternatingE2E(unittest.TestCase):
    def test_loop_stops_before_max_steps(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_alt_"))
        try:
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=30, non_interactive=True,
                               enable_reviewer=False, collision="OVERWRITE")
            # same two files rewritten forever: activity without progress
            script = []
            for i in range(15):
                script.append('{"action":"write","path":"f1.txt","content":"v%d"}' % i)
                script.append('{"action":"write","path":"f2.txt","content":"v%d"}' % i)
            fake = FakeProvider(script)
            out = run_bridge(cfg, "t", provider=fake)
            self.assertFalse(out.get("finished", False))
            self.assertEqual(out.get("kind"), "LOOP_DETECTED")
            self.assertLess(fake.calls, 30)
            # loop detector fired; unrelated files untouched
            self.assertEqual(sorted(p.name for p in tmp.iterdir()
                                    if not p.name.startswith(".bridge")),
                             ["f1.txt", "f2.txt"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
