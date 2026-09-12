"""MIGRATED from v0.2 tests/test_executor_v02.py — must keep passing in v0.3.

Note: delete now recycles by default (restorable); assertions on the
original path still hold.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from executor import Executor


class TestNewFileActions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v02_ex_"))
        self.ex = Executor(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mkdir(self):
        r = self.ex.do_mkdir("demo/sub")
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.tmp / "demo/sub").is_dir())

    def test_copy_move(self):
        self.ex.do_write("a.txt", "hello")
        r = self.ex.do_copy("a.txt", "b.txt")
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.tmp / "b.txt").exists())
        m = self.ex.do_move("b.txt", "sub/c.txt")
        self.assertTrue(m["ok"], m)
        self.assertFalse((self.tmp / "b.txt").exists())
        self.assertTrue((self.tmp / "sub/c.txt").exists())

    def test_delete_file_ok(self):
        self.ex.do_write("gone.txt", "x")
        r = self.ex.do_delete("gone.txt")
        self.assertTrue(r["ok"], r)
        self.assertFalse((self.tmp / "gone.txt").exists())

    def test_delete_protection(self):
        (self.tmp / "full").mkdir()
        (self.tmp / "full" / "x.txt").write_text("x")
        r = self.ex.do_delete("full")
        self.assertFalse(r["ok"])
        self.assertIn("not empty", r["error"])
        self.assertTrue((self.tmp / "full").exists())
        root = self.ex.do_delete(".")
        self.assertFalse(root["ok"])

    def test_patch_unique(self):
        self.ex.do_write("p.txt", "line1\nTARGET\nline3\n")
        r = self.ex.do_patch("p.txt", old="TARGET", new="REPLACED")
        self.assertTrue(r["ok"], r)
        self.assertIn("REPLACED", (self.tmp / "p.txt").read_text())
        self.ex.do_write("amb.txt", "X and X")
        r2 = self.ex.do_patch("amb.txt", old="X", new="Y")
        self.assertFalse(r2["ok"])
        self.assertIn("ambiguous", r2["error"])
        r3 = self.ex.do_patch("amb.txt", old="ZZZ", new="Y")
        self.assertFalse(r3["ok"])

    def test_search_exists_stat(self):
        self.ex.do_write("s.txt", "alpha\nGENESIS_AGENT_CORE_V02\nomega\n")
        s = self.ex.do_search("GENESIS_AGENT_CORE_V02")
        self.assertTrue(s["ok"], s)
        self.assertTrue(any(m["file"].endswith("s.txt") for m in s["matches"]))
        e = self.ex.do_exists("s.txt")
        self.assertTrue(e["exists"] and e["is_file"])
        st = self.ex.do_stat("s.txt")
        self.assertTrue(st["ok"] and st["size"] > 0)

    def test_run_test_action(self):
        (self.tmp / "t_pass.py").write_text("print('T_OK')", encoding="utf-8")
        r = self.ex.do_test("python t_pass.py")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["passed"])
        self.assertIn("duration_s", r)
        self.assertIn("T_OK", r["stdout"])
        (self.tmp / "t_fail.py").write_text("import sys; sys.exit(1)", encoding="utf-8")
        f = self.ex.do_test("python t_fail.py")
        self.assertFalse(f["ok"])
        self.assertFalse(f["passed"])
        self.assertEqual(f["exit_code"], 1)


if __name__ == "__main__":
    unittest.main()
