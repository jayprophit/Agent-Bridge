"""Node network transport + pairing/security tests (v0.7).

Real loopback HTTP via two separate processes (node_test_server.py).
In-memory transport is preserved and untouched; these tests exercise the
real network path only.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

from nodes.node_transport import (
    ERR_AUTHENTICATION_FAILED, ERR_NODE_UNTRUSTED, ERR_PAIRING_EXPIRED,
    ERR_PAIRING_REJECTED, ERR_PRIVACY_DENIED, ERR_PROTOCOL_VERSION_UNSUPPORTED,
    ERR_REMOTE_OWNER_APPROVAL_REQUIRED, ERR_REMOTE_OWNER_POLICY_DENIED,
    ERR_REMOTE_PLAINTEXT_DENIED, ERR_REPLAY_REJECTED,
    WEBSOCKET_STATUS, NodeProtocolInfo, PairingManager, ReplayGuard,
    TaskEnvelope, TlsConfig, DevFileCredentialStore,
    WindowsCredentialManagerStore, HttpNodeTransport,
    audit_event, challenge_response, ensure_loopback_or_raise,
    negotiate_protocol, privacy_allows_send,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "node_test_server.py")


def _launch(args, timeout_s=20):
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT] + args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + timeout_s
    port = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"harness server exited: {proc.stdout.read()}")
        line = proc.stdout.readline()
        if line.startswith("PORT="):
            port = int(line.strip().split("=", 1)[1])
            break
    if port is None:
        proc.terminate()
        raise RuntimeError("harness server did not report a port")
    # Wait until health responds
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with urllib.request.urlopen(base + "/v1/node/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    return proc, base


def _find_openssl():
    import shutil
    found = shutil.which("openssl")
    if found:
        return found
    git_openssl = r"C:\Program Files\Git\usr\bin\openssl.exe"
    if os.path.exists(git_openssl):
        return git_openssl
    return ""


def _make_dev_certs(tmpdir):
    """Generate a throwaway local CA + localhost server cert (test only).

    Certs live in a temp dir, are deleted with it, and are never committed.
    """
    import subprocess as _sp
    ossl = _find_openssl()
    if not ossl:
        raise unittest.SkipTest("no openssl backend available; HTTPS stays CONFIGURATION_REQUIRED")
    ca_key = os.path.join(tmpdir, "ca.key")
    ca_crt = os.path.join(tmpdir, "ca.crt")
    srv_key = os.path.join(tmpdir, "server.key")
    srv_csr = os.path.join(tmpdir, "server.csr")
    srv_crt = os.path.join(tmpdir, "server.crt")
    ext = os.path.join(tmpdir, "server.ext")
    with open(ext, "w", encoding="utf-8") as f:
        f.write("subjectAltName=DNS:localhost,IP:127.0.0.1")
    _sp.run([ossl, "req", "-x509", "-newkey", "rsa:2048",
             "-keyout", ca_key, "-out", ca_crt, "-days", "2", "-nodes",
             "-subj", "/CN=agent-bridge-dev-ca",
             "-addext", "basicConstraints=critical,CA:TRUE",
             "-addext", "keyUsage=critical,keyCertSign,cRLSign"],
            check=True, capture_output=True, timeout=60)
    _sp.run([ossl, "req", "-newkey", "rsa:2048",
             "-keyout", srv_key, "-out", srv_csr, "-nodes",
             "-subj", "/CN=localhost"],
            check=True, capture_output=True, timeout=60)
    _sp.run([ossl, "x509", "-req", "-in", srv_csr,
             "-CA", ca_crt, "-CAkey", ca_key, "-CAcreateserial",
             "-out", srv_crt, "-days", "2", "-extfile", ext],
            check=True, capture_output=True, timeout=60)
    return ca_crt, srv_crt, srv_key


def _launch_tls(args, cafile, timeout_s=20):
    import ssl as _ssl
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT] + args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + timeout_s
    port = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"harness server exited: {proc.stdout.read()}")
        line = proc.stdout.readline()
        if line.startswith("PORT="):
            port = int(line.strip().split("=", 1)[1])
            break
    if port is None:
        proc.terminate()
        raise RuntimeError("harness server did not report a port")
    base = f"https://127.0.0.1:{port}"
    ctx = _ssl.create_default_context(cafile=cafile)
    for _ in range(100):
        try:
            with urllib.request.urlopen(base + "/v1/node/health", timeout=2,
                                        context=ctx) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    return proc, base


class PairingSecurityUnitTests(unittest.TestCase):
    def test_pairing_lifecycle_and_single_use_token(self):
        pm = PairingManager("a")
        attempt, token = pm.request_pairing("b")
        self.assertEqual(pm.state_of(attempt), "AWAITING_OWNER_APPROVAL")
        ok, code, challenge = pm.approve(attempt, True, "LIMITED_NODE")
        self.assertTrue(ok)
        resp = challenge_response(token, attempt, challenge)
        ok, code = pm.verify_challenge(attempt, token, resp)
        self.assertTrue(ok)
        self.assertTrue(pm.mark_paired(attempt))
        # Single use: replay of the same token fails
        ok, _ = pm.verify_challenge(attempt, token, resp)
        self.assertFalse(ok)

    def test_pairing_reject_and_revoke(self):
        pm = PairingManager("a")
        attempt, _ = pm.request_pairing("b")
        ok, code, _ = pm.approve(attempt, False)
        self.assertFalse(ok)
        self.assertEqual(code, ERR_PAIRING_REJECTED)
        pm.revoke("b")
        self.assertTrue(pm.is_revoked("b"))

    def test_expired_token(self):
        pm = PairingManager("a", token_ttl_s=0.05)
        attempt, token = pm.request_pairing("b")
        time.sleep(0.1)
        ok, code, _ = pm.approve(attempt, True)
        self.assertFalse(ok)
        self.assertEqual(code, ERR_PAIRING_EXPIRED)

    def test_bad_token_rejected(self):
        pm = PairingManager("a")
        attempt, token = pm.request_pairing("b")
        ok, _, challenge = pm.approve(attempt, True)
        self.assertTrue(ok)
        ok, code = pm.verify_challenge(attempt, "wrong-token", "00" * 32)
        self.assertFalse(ok)
        self.assertEqual(code, ERR_AUTHENTICATION_FAILED)

    def test_replay_guard(self):
        g = ReplayGuard(window_s=60)
        ok, _ = g.verify("n1", time.time(), "r1")
        self.assertTrue(ok)
        ok, code = g.verify("n1", time.time(), "r1")
        self.assertFalse(ok)
        self.assertEqual(code, ERR_REPLAY_REJECTED)
        ok, code = g.verify("n2", time.time() - 3600, "r2")
        self.assertFalse(ok)
        self.assertEqual(code, ERR_REPLAY_REJECTED)

    def test_plaintext_non_loopback_denied(self):
        with self.assertRaises(PermissionError) as ctx:
            ensure_loopback_or_raise("http://192.0.2.1:9999/v1/node/health")
        self.assertIn(ERR_REMOTE_PLAINTEXT_DENIED, str(ctx.exception))
        # Loopback allowed
        self.assertEqual(
            ensure_loopback_or_raise("http://127.0.0.1:9999/x"), "PLAINTEXT_LOOPBACK")

    def test_privacy_checked_before_send(self):
        allowed, code = privacy_allows_send("CURRENT_DEVICE_ONLY", "a", "b", True)
        self.assertFalse(allowed)
        self.assertEqual(code, ERR_PRIVACY_DENIED)
        allowed, _ = privacy_allows_send("LOCAL_FIRST", "a", "b", False)
        self.assertFalse(allowed)

    def test_protocol_negotiation(self):
        local = NodeProtocolInfo(node_id="a")
        ok, _ = negotiate_protocol(local, {"protocol_name": "agent-bridge-node",
                                           "protocol_version": "1.0"})
        self.assertTrue(ok)
        ok, code = negotiate_protocol(local, {"protocol_name": "agent-bridge-node",
                                              "protocol_version": "9.9"})
        self.assertFalse(ok)
        self.assertEqual(code, ERR_PROTOCOL_VERSION_UNSUPPORTED)

    def test_tls_configuration_required_without_certs(self):
        self.assertEqual(TlsConfig().status(), "CONFIGURATION_REQUIRED")
        with self.assertRaises(ValueError):
            TlsConfig().server_context()

    def test_websocket_honestly_reported(self):
        self.assertEqual(WEBSOCKET_STATUS, "NOT_INSTALLED")

    def test_audit_redacts_secrets(self):
        ev = audit_event({"event": "pairing_request", "token": "abc",
                          "challenge": "def", "source_node": "a"})
        self.assertEqual(ev["token"], "[REDACTED]")
        self.assertEqual(ev["challenge"], "[REDACTED]")
        self.assertEqual(ev["source_node"], "a")

    def test_dev_credential_store_requires_flag_and_restricts(self):
        with self.assertRaises(PermissionError):
            DevFileCredentialStore("/tmp/x.json")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "creds.json")
            store = DevFileCredentialStore(path, development_only=True)
            store.put("k", "v")
            self.assertEqual(store.get("k"), "v")
            store.delete("k")
            self.assertIsNone(store.get("k"))

    def test_windows_credential_store_is_interface_only(self):
        store = WindowsCredentialManagerStore()
        with self.assertRaises(NotImplementedError):
            store.put("k", "v")


class TwoProcessNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desktop_proc, cls.desktop = _launch([
            "--node-id", "desktop-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read,code.execute",
            "--models", "qwen2.5-coder:3b",
            "--mem", "16384", "--vram", "4096", "--gpu", "1",
        ])
        cls.slow_proc, cls.slow = _launch([
            "--node-id", "slow-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
            "--executor", "slow",
        ])
        cls.estop_proc, cls.estop = _launch([
            "--node-id", "estop-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
            "--emergency-stop",
        ])
        cls.revoked_proc, cls.revoked = _launch([
            "--node-id", "revoked-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
            "--revoke", "watch-node",
        ])
        cls.deny_proc, cls.deny = _launch([
            "--node-id", "deny-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
            "--executor", "deny",
        ])
        cls.verbose_proc, cls.verbose = _launch([
            "--node-id", "verbose-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
            "--executor", "verbose",
        ])
        cls.t = HttpNodeTransport("watch-node")

    @classmethod
    def tearDownClass(cls):
        for proc in (cls.desktop_proc, cls.slow_proc, cls.estop_proc,
                     cls.revoked_proc, cls.deny_proc, cls.verbose_proc):
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass

    def _envelope(self, target, nonce, delegation_id="del-test-1",
                  tools=("filesystem.read",), privacy="LOCAL_FIRST"):
        return TaskEnvelope(
            delegation_id=delegation_id, task_id="task-1", session_id="s-1",
            source_node="watch-node", target_node=target, task_type="inspect",
            requirements={}, privacy_policy=privacy,
            required_tools=list(tools), nonce=nonce,
            timestamp=time.time(), deadline_s=60,
        )

    def test_handshake_and_health_over_real_http(self):
        health = self.t.health(self.desktop)
        self.assertTrue(health.get("ok"))
        hs = self.t.handshake(self.desktop, NodeProtocolInfo(node_id="watch-node"))
        self.assertTrue(hs.get("ok"))
        self.assertEqual(hs["protocol"]["protocol_version"], "1.0")

    def test_two_process_pairing(self):
        req = self.t.pairing_request(self.desktop, "watch-node")
        self.assertTrue(req.get("ok"))
        attempt, token = req["attempt_id"], req["pairing_token"]
        appr = self.t.pairing_approve(self.desktop, attempt, True, "LIMITED_NODE")
        self.assertTrue(appr.get("ok"))
        resp = challenge_response(token, attempt, appr["challenge"])
        # Post challenge directly (server holds the token hash, not the token)
        import urllib.request as _u
        data = json.dumps({"attempt_id": attempt, "token": token,
                           "response": resp}).encode()
        r = _u.Request(self.desktop + "/v1/node/pairing/challenge", data=data,
                       headers={"Content-Type": "application/json"})
        with _u.urlopen(r, timeout=10) as fh:
            body = json.loads(fh.read().decode())
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("state"), "PAIRED")

    def test_two_process_delegation_over_real_http(self):
        env = self._envelope("desktop-node", nonce="net-nonce-1", delegation_id="del-net-1")
        res = self.t.send_envelope(self.desktop, env)
        self.assertTrue(res.get("ok"), res)
        result = res["result"]
        self.assertEqual(result["status"], "COMPLETED")
        self.assertIn("validation", result["result_summary"])
        self.assertTrue(result["artifact_references"])
        art = result["artifact_references"][0]
        for key in ("ref", "hash", "size", "origin_node", "verified"):
            self.assertIn(key, art)
        # Status + SSE event stream over real HTTP
        st = self.t.delegation_status(self.desktop, "del-net-1")
        self.assertTrue(st.get("ok"))
        ev = self.t.delegation_events(self.desktop, "del-net-1")
        self.assertTrue(ev.get("ok"))
        self.assertIn("COMPLETED", ev.get("events_text", ""))

    def test_replay_rejected(self):
        env = self._envelope("desktop-node", nonce="replay-nonce-1",
                             delegation_id="del-replay-1")
        first = self.t.send_envelope(self.desktop, env)
        self.assertTrue(first.get("ok"))
        second = self.t.send_envelope(self.desktop, env)
        self.assertFalse(second.get("ok"))
        self.assertEqual(second.get("error_code"), "REPLAY_REJECTED")

    def test_untrusted_network_node_excluded(self):
        # fresh server that does not trust watch-node
        proc, base = _launch(["--node-id", "stranger-node", "--tools", "filesystem.read"])
        try:
            env = self._envelope("stranger-node", nonce="untrusted-1",
                                 delegation_id="del-untrusted-1")
            res = self.t.send_envelope(base, env)
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("error_code"), "NODE_UNTRUSTED")
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass

    def test_revoked_node_rejected(self):
        env = self._envelope("revoked-node", nonce="revoked-1",
                             delegation_id="del-revoked-1")
        res = self.t.send_envelope(self.revoked, env)
        self.assertFalse(res.get("ok"))
        self.assertIn(res.get("error_code"), ("NODE_UNTRUSTED", "PAIRING_REJECTED"))

    def test_emergency_stop_rejects_new_delegations(self):
        env = self._envelope("estop-node", nonce="estop-1", delegation_id="del-estop-1")
        res = self.t.send_envelope(self.estop, env)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error_code"), "EMERGENCY_STOP_ACTIVE")

    def test_cancellation_propagates(self):
        env = self._envelope("slow-node", nonce="cancel-1", delegation_id="del-cancel-1")
        holder = {}
        def _send():
            holder["res"] = self.t.send_envelope(self.slow, env)
        th = threading.Thread(target=_send, daemon=True)
        th.start()
        time.sleep(1.0)
        cancel = self.t.cancel_delegation(self.slow, "del-cancel-1")
        self.assertTrue(cancel.get("ok"))
        th.join(timeout=15)
        st = self.t.delegation_status(self.slow, "del-cancel-1")
        self.assertTrue(st.get("ok"))
        self.assertEqual(st["delegation"]["status"], "CANCELLED")

    def test_capability_refresh_and_heartbeat(self):
        hb = self.t.heartbeat(self.desktop, "watch-node", load=0.1)
        self.assertTrue(hb.get("ok"))
        ref = self.t.refresh_capabilities(self.desktop, {"tool_families": ["filesystem"]})
        self.assertTrue(ref.get("ok"))

    def test_protocol_version_mismatch_rejected(self):
        hs = self.t.handshake(self.desktop, NodeProtocolInfo(
            node_id="watch-node", protocol_version="9.9",
            min_supported_version="9.9", max_supported_version="9.9"))
        self.assertFalse(hs.get("ok"))
        self.assertEqual(hs.get("error_code"), "PROTOCOL_VERSION_UNSUPPORTED")

    def test_unknown_tool_capability_unavailable(self):
        env = self._envelope("desktop-node", nonce="cap-1",
                             delegation_id="del-cap-1",
                             tools=("nope.unknown_tool",))
        res = self.t.send_envelope(self.desktop, env)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error_code"), "CAPABILITY_UNAVAILABLE")

    def test_target_tool_authorization_denied(self):
        env = self._envelope("deny-node", nonce="deny-1",
                             delegation_id="del-deny-1")
        res = self.t.send_envelope(self.deny, env)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error_code"), "TOOL_DENIED")

    def test_large_result_truncated(self):
        env = self._envelope("verbose-node", nonce="verbose-1",
                             delegation_id="del-verbose-1")
        res = self.t.send_envelope(self.verbose, env)
        self.assertTrue(res.get("ok"), res)
        self.assertLessEqual(len(res["result"]["result_summary"]), 2000)


class HttpsLoopbackTests(unittest.TestCase):
    """HTTPS E2E over real loopback TLS (dev CA in temp dir, deleted after)."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="ab_https_test_")
        cls.ca_crt, cls.srv_crt, cls.srv_key = _make_dev_certs(cls.tmpdir)
        cls.proc, cls.base = _launch_tls([
            "--node-id", "https-node",
            "--trust", json.dumps({"watch-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read,code.execute",
            "--tls-cert", cls.srv_crt, "--tls-key", cls.srv_key,
        ], cls.ca_crt)
        cls.t = HttpNodeTransport("watch-node", cafile=cls.ca_crt)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
        except Exception:
            try:
                cls.proc.kill()
            except Exception:
                pass
        finally:
            try:
                if cls.proc.stdout:
                    cls.proc.stdout.close()
            except Exception:
                pass
            import shutil as _sh
            _sh.rmtree(cls.tmpdir, ignore_errors=True)

    def test_tls_version_and_security_mode(self):
        health = self.t.health(self.base)
        self.assertTrue(health.get("ok"), health)
        self.assertEqual(health.get("security_mode"), "TLS")
        self.assertIn(health.get("tls_version"), ("TLSv1.2", "TLSv1.3"))

    def test_https_handshake_pairing_delegation(self):
        hs = self.t.handshake(self.base, NodeProtocolInfo(node_id="watch-node"))
        self.assertTrue(hs.get("ok"), hs)
        req = self.t.pairing_request(self.base, "watch-node")
        self.assertTrue(req.get("ok"), req)
        attempt, token = req["attempt_id"], req["pairing_token"]
        appr = self.t.pairing_approve(self.base, attempt, True, "LIMITED_NODE")
        self.assertTrue(appr.get("ok"), appr)
        import urllib.request as _u
        data = json.dumps({"attempt_id": attempt, "token": token,
                           "response": challenge_response(token, attempt,
                                                          appr["challenge"])}).encode()
        r = _u.Request(self.base + "/v1/node/pairing/challenge", data=data,
                       headers={"Content-Type": "application/json"})
        import ssl as _ssl
        with _u.urlopen(r, timeout=10,
                        context=_ssl.create_default_context(cafile=self.ca_crt)) as fh:
            body = json.loads(fh.read().decode())
        self.assertTrue(body.get("ok"), body)
        env = TaskEnvelope(
            delegation_id="del-https-1", task_id="task-https-1", session_id="s-1",
            source_node="watch-node", target_node="https-node", task_type="inspect",
            requirements={}, privacy_policy="LOCAL_FIRST",
            required_tools=["filesystem.read"], nonce="https-nonce-1",
            timestamp=time.time(), deadline_s=60)
        res = self.t.send_envelope(self.base, env)
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res["result"]["status"], "COMPLETED")

    def test_unverified_client_rejected(self):
        # No cafile: system CAs cannot validate the dev CA -> must fail.
        t = HttpNodeTransport("watch-node")
        res = t.health(self.base)
        self.assertFalse(res.get("ok"))
        self.assertIn("verify", str(res.get("error", "")).lower())

    def test_server_does_not_request_client_certs_by_default(self):
        # mTLS remains SUPPORTED_CONFIGURATION/INTERFACE_ONLY: default server
        # context must not require client certificates.
        import ssl as _ssl
        ctx = TlsConfig(certfile=self.srv_crt, keyfile=self.srv_key).server_context()
        self.assertNotEqual(ctx.verify_mode, _ssl.CERT_REQUIRED)


class RemoteOwnerPolicyTests(unittest.TestCase):
    """Paired owner nodes do NOT inherit remote machine privileges."""

    @classmethod
    def setUpClass(cls):
        cls.disabled_proc, cls.disabled = _launch([
            "--node-id", "owner-target",
            "--trust", json.dumps({"owner-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
        ])
        cls.scoped_proc, cls.scoped = _launch([
            "--node-id", "scoped-target",
            "--trust", json.dumps({"owner-node": "TRUSTED_NODE"}),
            "--tools", "filesystem.read",
            "--remote-owner-policy", "REMOTE_OWNER_ENABLED",
            "--remote-owner-grant", "status.read",
        ])
        cls.t = HttpNodeTransport("owner-node")

    @classmethod
    def tearDownClass(cls):
        for proc in (cls.disabled_proc, cls.scoped_proc):
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass

    def _owner_envelope(self, target, delegation_id, nonce, scope="owner_full"):
        return TaskEnvelope(
            delegation_id=delegation_id, task_id="task-owner-1", session_id="s-1",
            source_node="owner-node", target_node=target, task_type="admin",
            requirements={}, privacy_policy="LOCAL_FIRST",
            required_tools=["filesystem.read"], nonce=nonce,
            timestamp=time.time(), deadline_s=60,
            owner_scope_requested=True, owner_scope=scope)

    def test_remote_owner_disabled_by_default(self):
        env = self._owner_envelope("owner-target", "del-owner-1", "owner-nonce-1")
        res = self.t.send_envelope(self.disabled, env)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error_code"), ERR_REMOTE_OWNER_POLICY_DENIED)

    def test_explicit_grant_allows_only_configured_scope(self):
        env = self._owner_envelope("scoped-target", "del-owner-2", "owner-nonce-2",
                                   scope="status.read")
        res = self.t.send_envelope(self.scoped, env)
        self.assertTrue(res.get("ok"), res)
        env = self._owner_envelope("scoped-target", "del-owner-3", "owner-nonce-3",
                                   scope="owner_full")
        res = self.t.send_envelope(self.scoped, env)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error_code"), ERR_REMOTE_OWNER_POLICY_DENIED)

    def test_non_owner_requests_unaffected(self):
        env = TaskEnvelope(
            delegation_id="del-owner-4", task_id="task-owner-1", session_id="s-1",
            source_node="owner-node", target_node="owner-target", task_type="inspect",
            requirements={}, privacy_policy="LOCAL_FIRST",
            required_tools=["filesystem.read"], nonce="owner-nonce-4",
            timestamp=time.time(), deadline_s=60)
        res = self.t.send_envelope(self.disabled, env)
        self.assertTrue(res.get("ok"), res)


if __name__ == "__main__":
    unittest.main()
