"""v0.3: memory compaction + context budgeting."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from context import ContextBudget, approx_size, truncate_middle
from memory import SessionMemory


class TestCompaction(unittest.TestCase):
    def test_preserves_critical_state(self):
        tmp = Path(tempfile.mkdtemp(prefix="v03_mem_"))
        try:
            m = SessionMemory(tmp / "s.json")
            m.set_task("build calculator", "fake")
            m.data["constraints"] = ["no network", "python only"]
            m.data["decisions"] = ["use subprocess-based tests"]
            for i in range(10):
                m.record("failed", {"step": i, "kind": "X", "error": "same boom"})
            for i in range(5):
                m.record("completed", {"step": i, "action": {"action": "list"},
                                       "files_touched": [f"f{i}.py"]})
            m.record("tests_run", {"command": "python -m pytest", "passed": True})
            m.record("review_findings", {"verdict": "revise", "issues": ["bug"]})
            rep = m.compact()
            self.assertLess(rep["after_chars"], rep["before_chars"])
            self.assertEqual(m.data["task"], "build calculator")
            self.assertEqual(m.data["constraints"], ["no network", "python only"])
            self.assertTrue(m.data["files_touched"])
            self.assertEqual(len(m.data["tests_run"]), 1)
            self.assertEqual(m.data["review_findings"][0]["verdict"], "revise")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBudget(unittest.TestCase):
    def test_measure_and_fit(self):
        b = ContextBudget(budget_chars=1000, keep_recent_results=2)
        parts = {"task": "t" * 100, "memory": {"x": "y" * 2000}}
        self.assertTrue(b.over(parts))
        self.assertIn("total", b.measure(parts))
        results = [{"content": "z" * 2000, "path": f"f{i}"} for i in range(5)]
        fitted = b.fit_results(results)
        self.assertEqual(len(fitted), 5)
        self.assertTrue(fitted[0].get("truncated_for_budget"))
        self.assertFalse(fitted[-1].get("truncated_for_budget", False))
        self.assertEqual(fitted[0]["path"], "f0")  # paths never mangled

    def test_truncate_middle(self):
        t = truncate_middle("a" * 1000, 100)
        self.assertLess(len(t), 200)
        self.assertIn("truncated", t)
        self.assertEqual(truncate_middle("short", 100), "short")


if __name__ == "__main__":
    unittest.main()
