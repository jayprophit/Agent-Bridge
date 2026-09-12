"""Security regression tests (v0.7, convergence).

Covers: path traversal, unknown/invented tools, missing adapters, profile
gates, audit redaction, pairing-token handling, large-output limits.
Network-level cases (replay, expiry, HMAC, untrusted, revoked,
privacy-before-send, plaintext denial, version mismatch, remote-owner
denial, emergency stop, cancellation) live in test_node_transport.py.
"""
import os
import tempfile
import unittest
from pathlib import Path

from executor import Executor
from nodes.node_transport import audit_event
from tools.registry import ToolRecord, ToolRegistry
from tools.router import ToolRouter


class PathTraversalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ab_traversal_")
        self.ws = Path(self.tmp.name) / "ws"
        self.ws.mkdir()
        (self.ws / "ok.txt").write_text("safe", encoding="utf-8")
        self.ex = Executor(workspace=self.ws)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_outside_workspace_refused(self):
        res = self.ex.dispatch({"action": "read", "path": "..\\..\\Windows\\win.ini"})
        self.assertFalse(res.get("ok"))

    def test_write_outside_workspace_refused(self):
        res = self.ex.dispatch({"action": "write", "path": "../evil.txt",
                                "content": "x"})
        self.assertFalse(res.get("ok"))
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())

    def test_absolute_outside_path_refused(self):
        outside = Path(self.tmp.name) / "outside.txt"
        res = self.ex.dispatch({"action": "write", "path": str(outside),
                                "content": "x"})
        # Absolute paths must stay inside the workspace (or be refused).
        if res.get("ok"):
            self.assertTrue(str(outside.resolve()).startswith(str(self.ws.resolve())))
        else:
            self.assertFalse(outside.exists())

    def test_in_workspace_still_works(self):
        res = self.ex.dispatch({"action": "read", "path": "ok.txt"})
        self.assertTrue(res.get("ok"))


class ToolPolicyBypassTests(unittest.TestCase):
    def test_invented_tool_rejected(self):
        reg = ToolRegistry()
        router = ToolRouter(reg)
        res = router.call("totally.made_up", {}, {})
        self.assertFalse(res.get("ok"))
        self.assertIn(res.get("kind", ""), ("UNKNOWN_TOOL", "NO_ADAPTER"))

    def test_record_without_adapter_never_executes(self):
        from tools.cat_core import _rec
        from tools.registry import READ_ONLY
        reg = ToolRegistry()
        rec = _rec("zz.probe", "zz", "probe", "zz probe", "stdlib", READ_ONLY)
        object.__setattr__(rec, "available", True)
        reg.register(rec)  # no adapter registered
        router = ToolRouter(reg)
        res = router.call("zz.probe", {}, {})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("kind"), "NO_ADAPTER")

    def test_owner_only_tool_denied_without_owner_profile(self):
        from tools.cat_nodes import node_records
        reg = ToolRegistry()
        for rec in node_records():
            try:
                reg.register(rec)
            except ValueError:
                pass
        router = ToolRouter(reg)
        res = router.call("node.delegate", {"task_id": "t"},
                          {"profile": "SAFE_EXPLORATION"})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("kind"), "PROFILE_DENIED")

    def test_unknown_plugin_adapters_rejected(self):
        from agents.discovery import AgentAdapterRegistry
        from ides.discovery import IDEAdapterRegistry
        with self.assertRaises(KeyError):
            AgentAdapterRegistry().get("NOPE_UNKNOWN")
        with self.assertRaises(KeyError):
            IDEAdapterRegistry().get("NOPE_UNKNOWN")
        with self.assertRaises(KeyError):
            ToolRegistry().adapter_for("nope.unknown")


class AuditProtectionTests(unittest.TestCase):
    def test_audit_event_redacts_all_secret_fields(self):
        ev = audit_event({
            "event": "pairing_request", "source_node": "a",
            "token": "tok", "challenge": "ch", "response": "r",
            "secret": "s", "private_key": "k", "authorization": "bearer x",
            "pairing_token": "p", "api_key": "k2",
        })
        for key in ("token", "challenge", "response", "secret", "private_key",
                    "authorization", "pairing_token", "api_key"):
            self.assertEqual(ev[key], "[REDACTED]")
        self.assertEqual(ev["source_node"], "a")

    def test_no_audit_exfiltration_route(self):
        # The node API must not expose the audit log; unknown routes 404.
        import urllib.error
        import urllib.request
        from nodes.node_server import NodeServerState, serve_node
        import threading, time
        state = NodeServerState("audit-node", lambda: {"node_id": "audit-node"},
                                lambda _r: "UNTRUSTED_NODE", None)
        srv = serve_node(state, host="127.0.0.1", port=0)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/v1/node/audit"
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    body = r.read().decode()
                self.fail(f"audit route should not exist, got: {body[:100]}")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404)
        finally:
            srv.shutdown()
            th.join(timeout=5)
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
