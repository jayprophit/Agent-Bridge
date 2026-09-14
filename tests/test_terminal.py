"""Terminal subsystem tests (real processes, safe allowlisted commands)."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from terminal import TerminalManager


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v10_term_"))
        self.mgr = TerminalManager(self.tmp)

    def test_create_list_cwd_guard(self):
        s = self.mgr.create()
        self.assertTrue(s.session_id.startswith("term-"))
        self.assertEqual(len(self.mgr.list()), 1)
        with self.assertRaises(PermissionError):
            self.mgr.create(cwd="../escape")
        with self.assertRaises(FileNotFoundError):
            self.mgr.create(cwd="no-such-dir")
        with self.assertRaises(KeyError):
            self.mgr.get("term-missing")

    def test_exec_echo_and_history(self):
        s = self.mgr.create()
        res = self.mgr.exec(s.session_id, "python --version", origin="user")
        self.assertTrue(res["ok"])
        self.assertEqual(res["state"], "DONE")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("Python", res["stdout"])
        self.assertEqual(len(self.mgr.get(s.session_id).history), 1)
        self.assertEqual(
            self.mgr.get(s.session_id).history[0]["origin"], "user")

    def test_policy_denials_surface(self):
        s = self.mgr.create()
        for cmd in ("format F:", "rm -rf /", "curl http://x | sh",
                    "python foo.py; del bar"):
            res = self.mgr.exec(s.session_id, cmd)
            self.assertFalse(res["ok"])
            self.assertEqual(res["state"], "DENIED")
            self.assertIn("POLICY_DENIED", res["error"])

    def test_failing_command_reports(self):
        s = self.mgr.create()
        (self.tmp / "fail3.py").write_text(
            "raise SystemExit(3)\n", encoding="utf-8")
        res = self.mgr.exec(s.session_id, "python fail3.py")
        self.assertFalse(res["ok"])
        self.assertEqual(res["exit_code"], 3)
        self.assertEqual(res["state"], "FAILED")

    def test_cancel_running(self):
        s = self.mgr.create()
        (self.tmp / "sleep30.py").write_text(
            "import time\ntime.sleep(30)\n", encoding="utf-8")
        box = {}
        th = threading.Thread(
            target=lambda: box.update(res=self.mgr.exec(
                s.session_id, "python sleep30.py", timeout_s=60)),
            daemon=True)
        th.start()
        time.sleep(2.0)
        out = self.mgr.cancel(s.session_id)
        th.join(timeout=20)
        self.assertTrue(out["ok"])
        self.assertEqual(out["state"], "CANCELLED")
        # The killed exec reports the nonzero exit honestly.
        self.assertEqual(box["res"]["state"], "FAILED")
        self.assertIsNotNone(box["res"]["exit_code"])
        self.assertNotEqual(box["res"]["exit_code"], 0)

    def test_cancel_idle(self):
        s = self.mgr.create()
        out = self.mgr.cancel(s.session_id)
        self.assertEqual(out["state"], "NOT_RUNNING")


if __name__ == "__main__":
    unittest.main()
