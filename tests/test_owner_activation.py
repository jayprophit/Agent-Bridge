"""v0.6: OWNER_FULL_ACCESS activation, auto-approve, machine scope, admin."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from config import BridgeConfig
from executor import Executor
from owner import (ADMIN_ACTIVE, ADMIN_NOT_ACTIVE, OWNER, admin_state,
                   emergency_active, emergency_clear, emergency_stop,
                   machine_roots, resolve_owner_path)
from policy import ApprovalManager, PreApprovedApproval


def _ws():
    tmp = Path(tempfile.mkdtemp(prefix="v06_owner_"))
    return tmp


class TestActivation(unittest.TestCase):
    def test_requires_both_flags(self):
        tmp = _ws()
        try:
            with self.assertRaises(ValueError):
                BridgeConfig(workspace=tmp, profile="OWNER_FULL_ACCESS")
            with self.assertRaises(ValueError):
                BridgeConfig(workspace=tmp, profile="OWNER_FULL_ACCESS",
                             owner_authorized=False)
            cfg = BridgeConfig(workspace=tmp, profile="OWNER_FULL_ACCESS",
                               owner_authorized=True)
            self.assertEqual(cfg.approval, "OWNER_AUTO_APPROVE")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_accidental_enablement(self):
        tmp = _ws()
        try:
            cfg = BridgeConfig(workspace=tmp)  # defaults
            self.assertEqual(cfg.profile, "")
            self.assertFalse(cfg.owner_authorized)
            self.assertNotEqual(cfg.approval, "OWNER_AUTO_APPROVE")
            with self.assertRaises(ValueError):
                BridgeConfig(workspace=tmp, profile="BOGUS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_owner_record(self):
        rec = OWNER.enable("OWNER_FULL_ACCESS", "sess-test", "EXTERNAL_NETWORK",
                           True)
        try:
            self.assertTrue(rec["owner_authorization_active"])
            self.assertEqual(rec["session_id"], "sess-test")
            self.assertIn(rec["administrator"],
                          (ADMIN_ACTIVE, ADMIN_NOT_ACTIVE, "ADMIN_UNKNOWN"))
            self.assertTrue(rec["start_time"])
        finally:
            OWNER.disable()
        with self.assertRaises(PermissionError):
            OWNER.enable("AUTO_SAFE", "s", "LOCAL_MODEL_NETWORK", True)


class TestAutoApprove(unittest.TestCase):
    def test_owner_auto_approved_recorded(self):
        m = ApprovalManager(level="OWNER_AUTO_APPROVE",
                            interface=PreApprovedApproval(),
                            non_interactive=True)
        v = m.decide({"action": "shell", "command": "rm -rf /tmp/x"})
        self.assertTrue(v["approved"])
        self.assertEqual(v["decision"], "OWNER_AUTO_APPROVED")

    def test_safe_profiles_untouched(self):
        m = ApprovalManager(level="AUTO_SAFE",
                            interface=PreApprovedApproval(),
                            non_interactive=True)
        v = m.decide({"action": "browser", "op": "open",
                      "url": "https://example.com"})
        self.assertFalse(v["approved"])
        m2 = ApprovalManager(level="READ_ONLY",
                             interface=PreApprovedApproval(),
                             non_interactive=True)
        self.assertFalse(m2.decide({"action": "read", "path": "x"})["approved"]
                         is False)  # reads still allowed
        self.assertFalse(m2.decide({"action": "write", "path": "x",
                                    "content": "y"})["approved"])


class TestMachineScope(unittest.TestCase):
    def test_roots_and_canonicalization(self):
        roots = machine_roots()
        self.assertTrue(roots)
        tmp = _ws()
        try:
            ex = Executor(tmp, owner_mode=True)
            p = ex._resolve("sub/../file.txt")
            self.assertEqual(p, (tmp / "file.txt").resolve())
            # absolute machine path outside workspace resolves
            outside = Path(tempfile.gettempdir()) / "v06_probe.txt"
            p2 = ex._resolve(str(outside))
            self.assertEqual(p2, outside.resolve())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bridge_internals_still_blocked(self):
        tmp = _ws()
        try:
            ex = Executor(tmp, owner_mode=True)
            r = ex.do_write(".bridge/evil.txt", "x")
            self.assertFalse(r["ok"])
            self.assertIn("INTERNAL_PROTECTED", r["error"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestAdminAndEstop(unittest.TestCase):
    def test_admin_state_honest(self):
        self.assertIn(admin_state(), (ADMIN_ACTIVE, ADMIN_NOT_ACTIVE,
                                      "ADMIN_UNKNOWN"))

    def test_admin_required_without_elevation(self):
        if admin_state() == ADMIN_ACTIVE:
            self.skipTest("running elevated; cannot test denial path")
        tmp = _ws()
        try:
            ex = Executor(tmp, owner_mode=True)
            sysroot = Path("C:/Windows/System32/drivers/etc/hosts")
            r = ex.do_write(str(sysroot), "x")
            self.assertFalse(r["ok"])
            self.assertIn("ADMIN_REQUIRED", r["error"])
            # nothing was written outside: hosts untouched
            self.assertNotIn("x", sysroot.read_text()[:50] if sysroot.exists()
                             else "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_admin_gate_end_to_end(self):
        if admin_state() == ADMIN_ACTIVE:
            self.skipTest("running elevated; cannot test denial path")
        from bridge import run_bridge
        from config import BridgeConfig
        from tests.helpers import FakeProvider
        tmp = _ws()
        try:
            cfg = BridgeConfig(workspace=tmp, mode="build",
                               approval="OWNER_AUTO_APPROVE",
                               profile="OWNER_FULL_ACCESS",
                               owner_authorized=True,
                               enable_reviewer=False)
            fake = FakeProvider([
                '{"action":"write","path":"C:/Windows/System32/drivers/etc/hosts_probe_xyz","content":"x"}',
                '{"action":"finish","message":"done"}',
            ])
            out = run_bridge(cfg, "t", provider=fake)
            errs = json.dumps(out.get("history", []))
            self.assertIn("ADMIN_REQUIRED", errs)
            self.assertFalse((Path("C:/Windows/System32/drivers/etc")
                              / "hosts_probe_xyz").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_emergency_stop(self):
        emergency_clear()
        tmp = _ws()
        try:
            ex = Executor(tmp, owner_mode=True)
            self.assertTrue(ex.do_shell("echo hi")["ok"])
            emergency_stop("test stop")
            on, _ = emergency_active()
            self.assertTrue(on)
            r = ex.do_shell("echo hi")
            self.assertFalse(r["ok"])
            self.assertIn("EMERGENCY_STOPPED", r["error"])
        finally:
            emergency_clear()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
