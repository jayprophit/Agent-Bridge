"""v0.5: progress tracker, error signatures, test mapping."""
import shutil
import tempfile
import unittest
from pathlib import Path

from progress import (ErrorSignatureTracker, ProgressTracker, file_hash,
                      normalize_error)
from testmap import map_tests


class TestErrorSignatures(unittest.TestCase):
    def test_normalizes(self):
        a = normalize_error('File "C:\\ws\\app.py", line 42, in <module>\nNameError: x')
        b = normalize_error('File "D:\\other\\app.py", line 1042, in <module>\nNameError: y')
        self.assertEqual(a.split(":")[0], b.split(":")[0])
        self.assertNotIn("C:\\\\", a)

    def test_recurrence_counted(self):
        t = ErrorSignatureTracker()
        _, n1 = t.note("SyntaxError: bad")
        _, n2 = t.note("SyntaxError: bad")
        self.assertEqual((n1, n2), (1, 2))
        self.assertTrue(t.recurring("SyntaxError: bad"))


class TestProgressTracker(unittest.TestCase):
    def test_file_advancement(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_prog_"))
        try:
            (tmp / "a.txt").write_text("v1")
            p = ProgressTracker(no_progress_limit=3)
            self.assertTrue(p.note_file(tmp, "a.txt"))
            self.assertFalse(p.note_file(tmp, "a.txt"))
            (tmp / "a.txt").write_text("v2")
            self.assertTrue(p.note_file(tmp, "a.txt"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ab_oscillation_no_progress(self):
        p = ProgressTracker(no_progress_limit=3)
        self.assertIsNone(p.priced_check(False))
        self.assertIsNone(p.priced_check(False))
        r = p.priced_check(False)
        self.assertIsNotNone(r)
        self.assertIn("NO_PROGRESS_DETECTED", r)

    def test_test_fix_counts_as_progress(self):
        p = ProgressTracker(no_progress_limit=2)
        self.assertTrue(p.note_test("pytest", True))
        self.assertFalse(p.note_test("pytest", True))
        self.assertIsNone(p.priced_check(True))

    def test_issue_resolution(self):
        p = ProgressTracker()
        p.issues_open.add("missing guard")
        p.note_issue_resolved("missing guard")
        self.assertEqual(p.issues_open, set())


class TestMapping(unittest.TestCase):
    def test_import_mapping(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_map_"))
        try:
            (tmp / "calc.py").write_text("def add(a,b):\n return a+b\n")
            (tmp / "test_calc.py").write_text("import calc\nassert calc.add(1,2)==3\n")
            (tmp / "unrelated.py").write_text("X=1\n")
            m = map_tests(["calc.py", "unrelated.py"], ["test_calc.py"], tmp)
            self.assertIn("calc.py", m["mapping"])
            self.assertGreaterEqual(m["mapping"]["calc.py"][0]["confidence"], 0.6)
            self.assertIn("unrelated.py", m["weak_sources"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unrelated_passing_test_is_weak(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_map2_"))
        try:
            (tmp / "core.py").write_text("def f():\n return 1\n")
            (tmp / "test_other.py").write_text("assert 1==1\nassert 2==2\n")
            m = map_tests(["core.py"], ["test_other.py"], tmp)
            self.assertIn("core.py", m["weak_sources"])
            self.assertNotIn("core.py", m["mapping"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
