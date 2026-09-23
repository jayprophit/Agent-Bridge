"""Governed remote-desktop adapter tests (P21, REQ-p21-remote-desktop)."""
import unittest

import remote_desktop
from remote_desktop import (
    AuthError,
    BackendUnavailable,
    EndpointError,
    EndpointRegistry,
    LoopbackBackend,
    ScopeError,
    SessionError,
    SessionManager,
    TransferScope,
    VncBackend,
    validate_endpoint,
)


def endpoint(**over):
    base = {
        "endpoint_id": "lab-pc",
        "host": "192.168.1.50",
        "port": 5900,
        "auth_method": "loopback-sim",
        "credential": {"ref": "vault://rdp/lab-pc"},
        "label": "lab",
    }
    base.update(over)
    return base


class TestEndpoints(unittest.TestCase):
    def test_valid_endpoint_keeps_vault_ref_only(self):
        ep = validate_endpoint(endpoint())
        self.assertEqual(ep.credential, {"ref": "vault://rdp/lab-pc"})
        self.assertEqual(ep.port, 5900)

    def test_raw_credentials_rejected(self):
        for banned in ("password", "secret", "token", "private_key", "api_key"):
            with self.assertRaises(EndpointError, msg=banned):
                validate_endpoint(endpoint(credential={"ref": "x", banned: "hunter2"}))
        with self.assertRaises(EndpointError):
            validate_endpoint(endpoint(credential={"username": "u"}))

    def test_shape_and_auth_validation(self):
        with self.assertRaises(EndpointError):
            validate_endpoint(endpoint(host=""))
        with self.assertRaises(EndpointError):
            validate_endpoint(endpoint(port=0))
        with self.assertRaises(EndpointError):
            validate_endpoint(endpoint(port=70000))
        with self.assertRaises(EndpointError):
            validate_endpoint(endpoint(auth_method="none"))
        with self.assertRaises(EndpointError):
            validate_endpoint(endpoint(auth_method="trust-me"))

    def test_registry_dedup_and_lookup(self):
        reg = EndpointRegistry()
        reg.register(endpoint())
        with self.assertRaises(EndpointError):
            reg.register(endpoint())
        self.assertEqual(reg.list_ids(), ["lab-pc"])
        self.assertEqual(reg.get("lab-pc").host, "192.168.1.50")
        with self.assertRaises(EndpointError):
            reg.get("ghost")


class TestSessions(unittest.TestCase):
    def manager(self):
        return SessionManager(LoopbackBackend()), EndpointRegistry()

    def test_open_connect_close_lifecycle(self):
        mgr, reg = self.manager()
        reg.register(endpoint())
        session = mgr.open(reg.get("lab-pc"), TransferScope(max_bytes=100))
        self.assertEqual(session.state, "CONNECTED")
        self.assertTrue(session.simulated)
        mgr.close(session)
        self.assertEqual(session.state, "CLOSED")
        with self.assertRaises(SessionError):
            mgr.close(session)

    def test_loopback_replays_declared_frames_only(self):
        mgr = SessionManager(LoopbackBackend(frames=[{"width": 1, "height": 1, "note": "a"}]))
        reg = EndpointRegistry()
        reg.register(endpoint())
        session = mgr.open(reg.get("lab-pc"), TransferScope())
        frame = mgr.frame(session)
        self.assertEqual(frame, {"simulated": True, "width": 1, "height": 1, "note": "a"})
        self.assertEqual(session.frames, 1)
        mgr.close(session)
        with self.assertRaises(SessionError):
            mgr.frame(session)

    def test_loopback_rejects_foreign_auth(self):
        mgr = SessionManager(LoopbackBackend())
        reg = EndpointRegistry()
        reg.register(endpoint(auth_method="password-vault-ref"))
        with self.assertRaises(AuthError):
            mgr.open(reg.get("lab-pc"), TransferScope())

    def test_scope_enforcement_and_budget(self):
        mgr = SessionManager(LoopbackBackend())
        reg = EndpointRegistry()
        reg.register(endpoint())
        session = mgr.open(
            reg.get("lab-pc"),
            TransferScope(clipboard_out=True, file_download=True, max_bytes=10),
        )
        self.assertEqual(mgr.clipboard(session, "out", b"12345"), 5)
        with self.assertRaises(ScopeError):
            mgr.clipboard(session, "in", b"x")
        with self.assertRaises(ScopeError):
            mgr.clipboard(session, "sideways", b"x")
        with self.assertRaises(ScopeError):
            mgr.transfer(session, "upload", 1)
        self.assertEqual(mgr.transfer(session, "download", 5), 5)
        with self.assertRaises(ScopeError):
            mgr.clipboard(session, "out", b"1")
        with self.assertRaises(ScopeError):
            mgr.transfer(session, "download", -1)

    def test_no_authority_surface_on_adapter(self):
        for forbidden in ("execute", "grant", "approve", "authorize", "inject_input", "capture_screen"):
            self.assertFalse(hasattr(remote_desktop, forbidden), forbidden)


class TestVncBackend(unittest.TestCase):
    def test_declared_unavailable_with_reason(self):
        backend = VncBackend()
        self.assertFalse(backend.simulated)
        mgr = SessionManager(backend)
        reg = EndpointRegistry()
        reg.register(endpoint(auth_method="password-vault-ref"))
        with self.assertRaises(BackendUnavailable):
            mgr.open(reg.get("lab-pc"), TransferScope())


if __name__ == "__main__":
    unittest.main()
