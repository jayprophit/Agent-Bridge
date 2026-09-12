"""MIGRATED from v0.2 tests/test_executor_v01.py — must keep passing in v0.3."""
import shutil
import tempfile
import unittest
from pathlib import Path

from executor import Executor, Sandbox, SandboxViolation


class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge_ws_"))
        self.sb = Sandbox(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_ok(self):
        p = self.sb.resolve("sub/file.txt")
        self.assertEqual(p, (self.tmp / "sub/file.txt").resolve())

    def test_dot_is_workspace(self):
        self.assertEqual(self.sb.resolve("."), self.tmp.resolve())

    def test_traversal_blocked(self):
        with self.assertRaises(SandboxViolation):
            self.sb.resolve("../escape.txt")
        with self.assertRaises(SandboxViolation):
            self.sb.resolve("sub/../../..//evil")

    def test_absolute_outside_blocked(self):
        with self.assertRaises(SandboxViolation):
            self.sb.resolve("C:\\Windows\\System32\\x.txt")
        with self.assertRaises(SandboxViolation):
            self.sb.resolve("/etc/passwd")

    def test_absolute_inside_allowed(self):
        inside = (self.tmp / "inner.txt").resolve()
        self.assertEqual(self.sb.resolve(str(inside)), inside)


class TestFileTools(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge_ex_"))
        self.ex = Executor(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_read_list(self):
        r = self.ex.do_write("hello.py", "print('hi')")
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.tmp / "hello.py").exists())
        r2 = self.ex.do_read("hello.py")
        self.assertTrue(r2["ok"], r2)
        self.assertIn("print('hi')", r2["content"])
        r3 = self.ex.do_list(".")
        self.assertTrue(r3["ok"], r3)
        self.assertIn("hello.py", r3["entries"])

    def test_edit_ok_and_missing(self):
        self.ex.do_write("f.txt", "aaa bbb")
        r = self.ex.do_edit("f.txt", "bbb", "ccc")
        self.assertTrue(r["ok"], r)
        self.assertIn("ccc", (self.tmp / "f.txt").read_text())
        bad = self.ex.do_edit("f.txt", "not-present-xyz", "q")
        self.assertFalse(bad["ok"])
        self.assertIn("not found", bad["error"])

    def test_write_escape_blocked(self):
        r = self.ex.do_write("../outside.txt", "x")
        self.assertFalse(r["ok"])
        self.assertIn("workspace", r["error"])

    def test_dispatch_unknown(self):
        r = self.ex.dispatch({"action": "nuke"})
        self.assertFalse(r["ok"])


class TestShell(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bridge_sh_"))
        self.ex = Executor(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_python_ok(self):
        (self.tmp / "t.py").write_text("print('SHELL_OK')", encoding="utf-8")
        r = self.ex.do_shell("python t.py")
        self.assertEqual(r["exit_code"], 0, r)
        self.assertTrue(r["ok"], r)
        self.assertIn("SHELL_OK", r["stdout"])

    def test_blocked_binary(self):
        r = self.ex.do_shell("rm -rf /")
        self.assertFalse(r["ok"])
        self.assertIsNone(r.get("exit_code"))

    def test_blocked_chaining(self):
        r = self.ex.do_shell("python t.py && whoami")
        self.assertFalse(r["ok"])

    def test_failing_command_reports_real_code(self):
        (self.tmp / "fail.py").write_text("import sys; sys.exit(3)", encoding="utf-8")
        r = self.ex.do_shell("python fail.py")
        self.assertFalse(r["ok"])
        self.assertEqual(r["exit_code"], 3)


if __name__ == "__main__":
    unittest.main()
