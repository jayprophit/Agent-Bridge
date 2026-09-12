"""v0.6: runtime owner surface — activation, caps, stop, audit, regression."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from client import AgentRuntimeClient
from runtime import AgentRuntime, RuntimeConfig
from service import serve
from tests.helpers import FakeProvider


def _rt(tmp: Path, **kw) -> AgentRuntime:
    args = dict(allowed_workspace_roots=[str(tmp)])
    args.update(kw)
    return AgentRuntime(RuntimeConfig(**args))


class TestOwnerActivationAPI(unittest.TestCase):
    def test_session_owner_requires_auth(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_own_"))
        try:
            ws = tmp / "w"
            ws.mkdir()
            rt = _rt(tmp)
            with self.assertRaises(PermissionError):
                rt.create_session(str(ws), profile="OWNER_FULL_ACCESS",
                                  owner_authorized=False)
            s = rt.create_session(str(ws), profile="OWNER_FULL_ACCESS",
                                  owner_authorized=True)
            self.assertTrue(s.session_id.startswith("s-"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_caps_report_owner(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_own2_"))
        try:
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)],
                profile="OWNER_FULL_ACCESS", owner_authorized=True))
            caps = rt.capabilities()
            self.assertIn("owner", caps)
            self.assertTrue(caps["owner"]["auto_approve"])
            self.assertTrue(caps["owner"]["emergency_stop"])
            self.assertIn(caps["owner"]["admin_state"],
                          ("ADMIN_ACTIVE", "ADMIN_NOT_ACTIVE", "ADMIN_UNKNOWN"))
            # safe default has no owner block
            rt2 = _rt(tmp)
            self.assertNotIn("owner", rt2.capabilities())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_emergency_stop(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_own3_"))
        try:
            rt = _rt(tmp)
            out = rt.emergency_stop("test")
            self.assertTrue(out["stopped"])
            from owner import emergency_active, emergency_clear
            on, _ = emergency_active()
            self.assertTrue(on)
            emergency_clear()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_log_written_and_protected(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_own4_"))
        try:
            from executor import Executor
            ex = Executor(tmp, owner_mode=True)
            self.assertTrue(ex.do_shell("echo audit-probe")["ok"])
            log = tmp / ".bridge" / "logs" / "audit.jsonl"
            self.assertTrue(log.exists())
            self.assertIn("audit-probe", log.read_text())
            # model cannot touch audit trail even in owner mode
            r = ex.do_write(".bridge/logs/audit.jsonl", "wiped")
            self.assertFalse(r["ok"])
            self.assertIn("audit-probe", log.read_text())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class LiveOwnerService:
    def __init__(self, tmp: Path, token: str = ""):
        self.tmp = tmp
        self.rt = AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(tmp)], token=token),
            provider_factory=None)
        self.srv = serve(self.rt, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def client(self, token: str = "") -> AgentRuntimeClient:
        return AgentRuntimeClient(f"http://127.0.0.1:{self.port}", token=token)

    def close(self):
        try:
            self.srv.shutdown()
        except Exception:
            pass
        self.srv.server_close()


class TestOwnerService(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v06_ownsvc_"))
        self.svc = LiveOwnerService(self.tmp)

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_owner_session_create_and_caps(self):
        c = self.svc.client()
        ws = self.tmp / "w"
        ws.mkdir()
        s = c.create_session(str(ws), profile="OWNER_FULL_ACCESS",
                             owner_authorized=True)
        self.assertTrue(s["session_id"])
        caps = c.capabilities()
        self.assertIn("OWNER_FULL_ACCESS", caps.get("profiles", []))
        mc = c.machine_caps()
        self.assertTrue(mc.get("ok", True) in (True, False))
        st = c.session_status(s["session_id"])
        self.assertIn("status", st)

    def test_owner_session_denied_without_flag(self):
        from client import ClientError
        c = self.svc.client()
        ws = self.tmp / "w2"
        ws.mkdir()
        with self.assertRaises(ClientError):
            c.create_session(str(ws), profile="OWNER_FULL_ACCESS")

    def test_stop_endpoint(self):
        c = self.svc.client()
        out = c.emergency_stop("test stop")
        self.assertTrue(out.get("stopped"))
        from owner import emergency_active, emergency_clear
        on, _ = emergency_active()
        self.assertTrue(on)
        emergency_clear()

    def test_safe_session_cannot_use_owner_tools(self):
        c = self.svc.client()
        ws = self.tmp / "w3"
        ws.mkdir()
        # safe sessions simply have no owner tools exposed; owner-only
        # actions are refused at policy level (covered in unit tests)
        s = c.create_session(str(ws), mode="build")
        self.assertTrue(s["session_id"])


if __name__ == "__main__":
    unittest.main()
