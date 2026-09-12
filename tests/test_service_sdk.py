"""v0.4: service security boundary + SDK + CLI sharing runtime logic."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from client import AgentRuntimeClient, ClientError
from runtime import AgentRuntime, RuntimeConfig
from service import serve
from tests.helpers import FakeProvider


def _factory(script, model="fake-m"):
    provs: dict[str, FakeProvider] = {}

    def make(role: str) -> FakeProvider:
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


class LiveService:
    def __init__(self, test, token=""):
        self.test = test
        self.tmp = Path(tempfile.mkdtemp(prefix="v04_svc_"))
        script = ['{"action":"write","path":"svc.txt","content":"ok"}',
                  '{"action":"finish","message":"done"}']
        self.rt = AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(self.tmp)], token=token),
            provider_factory=_factory(script))
        self.srv = serve(self.rt, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def client(self, token=""):
        return AgentRuntimeClient(f"http://127.0.0.1:{self.port}", token=token)

    def close(self):
        try:
            self.srv.shutdown()
        except Exception:
            pass
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestServiceSecurity(unittest.TestCase):
    def setUp(self):
        self.svc = LiveService(self)

    def tearDown(self):
        self.svc.close()

    def _raw(self, method, path, body=None, token=""):
        import urllib.request
        import urllib.error
        data = json.dumps(body or {}).encode() if method == "POST" else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.svc.port}{path}",
                                     data=data, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode() or "{}"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}"), dict(e.headers)

    def test_binds_localhost(self):
        self.assertEqual(self.svc.srv.server_address[0], "127.0.0.1")

    def test_health_and_caps_no_secrets(self):
        code, body, _ = self._raw("GET", "/health")
        self.assertEqual(code, 200)
        self.assertIn(body["status"], ("HEALTHY", "DEGRADED", "UNAVAILABLE"))
        code, caps, _ = self._raw("GET", "/v1/capabilities")
        self.assertEqual(code, 200)
        self.assertNotIn("token", json.dumps(caps).lower())

    def test_unknown_session_404(self):
        code, _, _ = self._raw("GET", "/v1/sessions/nope/status")
        self.assertEqual(code, 404)

    def test_malformed_json_400(self):
        import urllib.request
        import urllib.error
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.svc.port}/v1/sessions", data=b"{oops",
            method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_oversized_413(self):
        code, _, _ = self._raw("POST", "/v1/sessions", {"workspace": "x" * 2_000_000})
        self.assertEqual(code, 413)

    def test_bad_method_405(self):
        code, _, _ = self._raw("PUT", "/health")
        # BaseHTTPRequestHandler default may 501; our explicit map gives 405
        self.assertIn(code, (405, 501))

    def test_workspace_escape_403(self):
        code, body, _ = self._raw("POST", "/v1/sessions",
                                  {"workspace": "C:\\Windows\\System32"})
        self.assertEqual(code, 403)

    def test_no_cors_header(self):
        _, _, headers = self._raw("GET", "/health")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_no_shell_endpoint(self):
        for path in ["/exec-anything", "/v1/exec", "/run-shell-unrestricted",
                     "/v1/sessions/x/shell"]:
            code, _, _ = self._raw("POST", path, {"command": "whoami"})
            self.assertIn(code, (400, 404), path)

    def test_event_isolation(self):
        c = self.svc.client()
        s1 = c.create_session(str(self.svc.tmp))
        code, _, _ = self._raw("GET", "/v1/sessions/unknown-id/events")
        self.assertEqual(code, 404)
        ev = c.events(s1["session_id"])
        self.assertIn("events", ev)

    def test_token_enforced(self):
        svc2 = LiveService(self, token="secret-1")
        try:
            code, _, _ = self._raw("GET", "/health")
            self.assertEqual(code, 401)
            code, _, _ = self._raw("GET", "/health", token="secret-1")
            self.assertEqual(code, 200)
            code, _, _ = self._raw("GET", "/health", token="wrong")
            self.assertEqual(code, 401)
        finally:
            svc2.close()


class TestClientSDK(unittest.TestCase):
    def setUp(self):
        self.svc = LiveService(self)

    def tearDown(self):
        self.svc.close()

    def test_full_sdk_flow(self):
        c = self.svc.client()
        caps = c.capabilities()
        self.assertIn("write", caps["actions"])
        ws = str(self.svc.tmp / "proj")
        Path(ws).mkdir()
        s = c.create_session(ws, mode="build")
        sid = s["session_id"]
        sub = c.submit_task(sid, "sdk task")
        tid = sub["task_id"]
        end = __import__("time").time() + 120
        final = {}
        while __import__("time").time() < end:
            st = c.session_status(sid)
            if st["tasks"].get(tid) in ("COMPLETED", "FAILED", "CANCELLED"):
                final = st
                break
            __import__("time").sleep(2)
        self.assertEqual(final["tasks"][tid], "COMPLETED")
        self.assertTrue((Path(ws) / "svc.txt").exists())
        ev = c.events(sid)
        self.assertTrue(len(ev["events"]) > 3)
        c.delete_session(sid)
        with self.assertRaises(ClientError):
            c.session_status(sid)

    def test_sdk_idempotent_submit(self):
        c = self.svc.client()
        ws = str(self.svc.tmp / "proj2")
        Path(ws).mkdir()
        sid = c.create_session(ws, mode="build")["session_id"]
        a = c.submit_task(sid, "same", idempotency_key="idem-1")
        b = c.submit_task(sid, "same", idempotency_key="idem-1")
        self.assertEqual(a["task_id"], b["task_id"])
        self.assertTrue(b.get("deduped"))


class TestCLIUsesRuntime(unittest.TestCase):
    def test_cli_no_executor_imports(self):
        import ast
        tree = ast.parse(Path("cli.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("executor", "policy", "protocol"):
            self.assertNotIn(banned, imported)

    def test_cli_health_and_session(self):
        import io
        from contextlib import redirect_stdout
        import cli as cli_mod
        cli_mod._RT = None
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_mod.main(["--root", str(self._tmp_root()),
                               "health"])
        self.assertEqual(rc, 0)
        self.assertIn("status", buf.getvalue())

    def _tmp_root(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_cli_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        return str(tmp)


if __name__ == "__main__":
    unittest.main()
