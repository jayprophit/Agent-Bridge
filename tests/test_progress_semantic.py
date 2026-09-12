"""v0.6: semantic progress (hash oscillation) + error recurrence via bridge."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from progress import ErrorSignatureTracker, ProgressTracker, normalize_error
from tests.helpers import FakeProvider


class TestProgressTracker(unittest.TestCase):
    def test_ab_content_oscillation(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_sem_"))
        try:
            f = tmp / "a.txt"
            f.write_text("A")
            p = ProgressTracker(no_progress_limit=3)
            self.assertTrue(p.note_file(tmp, "a.txt"))   # first sighting
            f.write_text("B")
            self.assertTrue(p.note_file(tmp, "a.txt"))   # advanced
            f.write_text("A")
            self.assertTrue(p.note_file(tmp, "a.txt"))   # advanced (hash differs)
            f.write_text("B")
            p.note_file(tmp, "a.txt")
            f.write_text("A")
            p.note_file(tmp, "a.txt")
            self.assertTrue(p.file_oscillating("a.txt"))  # A->B->A->B
            # oscillation is stagnation even though hashes change
            self.assertIsNone(p.priced_check(False))
            self.assertIsNone(p.priced_check(False))
            r = p.priced_check(False)
            self.assertIsNotNone(r)
            self.assertIn("NO_PROGRESS_DETECTED", r)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_error_recurrence(self):
        t = ErrorSignatureTracker()
        sig, n = t.note("NameError: foo at app.py:10")
        self.assertEqual(n, 1)
        self.assertTrue(t.recurring("NameError: foo at app.py:11"))
        self.assertFalse(t.recurring("TypeError: bar", threshold=5))

    def test_normalize_stable(self):
        a = normalize_error('File "C:\\w\\a.py", line 42, in <module>\nValueError: bad 12345')
        b = normalize_error('File "D:\\o\\a.py", line 1042, in <module>\nValueError: bad 7')
        self.assertEqual(a, b)


class TestSemanticLoopE2E(unittest.TestCase):
    def test_identical_rewrites_stop(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_sem2_"))
        try:
            (tmp / "a.txt").write_text("v0\n")
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=30, non_interactive=True,
                               enable_reviewer=False, collision="OVERWRITE")
            script = []
            for i in range(15):
                script.append('{"action":"write","path":"a.txt","content":"v%d"}' % (i % 2))
            fake = FakeProvider(script)
            out = run_bridge(cfg, "t", provider=fake)
            self.assertFalse(out.get("finished", False))
            self.assertIn(out.get("kind"), ("NO_PROGRESS_DETECTED", "LOOP_DETECTED",
                                            "MAX_STEPS_REACHED"))
            self.assertLess(fake.calls, 30)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
