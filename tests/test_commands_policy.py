"""v0.3: command classification, test profiles, permanent-delete policy."""
import unittest

from commands import (DESTRUCTIVE, INSTALL, NETWORK, READ_ONLY, SAFE_BUILD,
                      TEST, UNKNOWN, classify_command, matches_profile)
from policy import ApprovalManager, PreApprovedApproval, classify_risk


class TestClassification(unittest.TestCase):
    def test_read_only(self):
        cls, _ = classify_command("dir")
        self.assertEqual(cls, READ_ONLY)

    def test_safe_build(self):
        cls, _ = classify_command("python app.py")
        self.assertEqual(cls, SAFE_BUILD)

    def test_test_class(self):
        cls, _ = classify_command("python -m pytest tests")
        self.assertEqual(cls, TEST)

    def test_network(self):
        cls, _ = classify_command("curl http://example.com/x")
        self.assertEqual(cls, NETWORK)

    def test_install(self):
        cls, _ = classify_command("pip install requests")
        self.assertEqual(cls, INSTALL)

    def test_destructive(self):
        for cmd in ["rm -rf /", "git reset --hard", "del /s q"]:
            cls, _ = classify_command(cmd)
            self.assertEqual(cls, DESTRUCTIVE, cmd)

    def test_unknown_never_safe(self):
        cls, why = classify_command("frobnicate --all")
        self.assertEqual(cls, UNKNOWN)
        risk, _ = classify_risk({"action": "shell", "command": "frobnicate --all"})
        self.assertEqual(risk, "RISKY")


class TestProfiles(unittest.TestCase):
    def test_python_profile(self):
        self.assertTrue(matches_profile("python -m pytest tests", "python"))
        self.assertTrue(matches_profile("python -m unittest", "python"))
        # profile match is prefix-based; chaining is still refused by the
        # shell layer (defence in depth), tested in test_shell_cwd_escape.
        from executor import Executor
        import tempfile, shutil
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp(prefix="v03_prof_"))
        try:
            ex = Executor(tmp)
            r = ex.do_shell("pytest --evil-flag; rm x")
            self.assertFalse(r["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_node_profile(self):
        self.assertTrue(matches_profile("npm test", "node"))
        self.assertFalse(matches_profile("npm install evil", "node"))

    def test_off_profile_test_needs_approval(self):
        risk, reason = classify_risk({"action": "test", "command": "frobnicate"},
                                     test_profile="python")
        self.assertEqual(risk, "RISKY")


class TestPermanentDeletePolicy(unittest.TestCase):
    def test_permanent_delete_risky(self):
        risk, reason = classify_risk({"action": "delete", "path": "x", "permanent": True})
        self.assertEqual(risk, "RISKY")
        self.assertIn("elevated", reason)

    def test_recycle_delete_still_gated(self):
        risk, _ = classify_risk({"action": "delete", "path": "x"})
        self.assertEqual(risk, "RISKY")

    def test_unknown_shell_denied_noninteractive(self):
        mgr = ApprovalManager(level="AUTO_SAFE", interface=PreApprovedApproval(),
                              non_interactive=True)
        v = mgr.decide({"action": "shell", "command": "frobnicate --all"})
        self.assertFalse(v["approved"])


if __name__ == "__main__":
    unittest.main()
