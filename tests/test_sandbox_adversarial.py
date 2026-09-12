"""MIGRATED from v0.2 tests/test_sandbox_adversarial.py — must pass in v0.3."""
import shutil
import tempfile
import unittest
from pathlib import Path

from executor import Executor, Sandbox, SandboxViolation


class TestAdversarial(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v02_adv_"))
        self.sb = Sandbox(self.tmp)
        self.ex = Executor(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dotdot_variants(self):
        for p in ["../x", "..\\x", "sub/../../x", "./../x", "a/b/../../../x"]:
            with self.assertRaises(SandboxViolation, msg=p):
                self.sb.resolve(p)

    def test_absolute_escapes(self):
        for p in ["C:\\Windows\\x", "D:/evil", "/etc/passwd", "/tmp/x"]:
            with self.assertRaises(SandboxViolation, msg=p):
                self.sb.resolve(p)

    def test_unc_paths(self):
        for p in ["\\\\server\\share\\x", "//server/share/x"]:
            with self.assertRaises(SandboxViolation, msg=p):
                self.sb.resolve(p)

    def test_encoded_traversal(self):
        for p in ["%2e%2e/x", "..%2fx", "%2E%2E%2Fy", "sub/%2e%2e/%2e%2e/evil"]:
            with self.assertRaises(SandboxViolation, msg=p):
                self.sb.resolve(p)

    def test_mixed_separators(self):
        with self.assertRaises(SandboxViolation):
            self.sb.resolve("sub\\..\\..\\evil")

    def test_symlink_escape(self):
        outside = Path(tempfile.mkdtemp(prefix="v02_out_"))
        try:
            link = self.tmp / "link_out"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(SandboxViolation):
                self.sb.resolve("link_out/secret.txt")
            r = self.ex.do_write("link_out/evil.txt", "x")
            self.assertFalse(r["ok"])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_shell_cwd_escape_denied(self):
        for cmd in ["python x.py; rm y", "python x.py && whoami",
                    "python x.py | cat", "python `whoami`",
                    "python $(whoami)", "cd .."]:
            r = self.ex.do_shell(cmd)
            self.assertFalse(r["ok"], cmd)

    def test_dispatch_delete_root_refused(self):
        r = self.ex.dispatch({"action": "delete", "path": "."})
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
