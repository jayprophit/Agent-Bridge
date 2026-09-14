"""Terminal service-route tests (live loopback HTTP, safe commands)."""
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path


def _api(port, method, path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


import urllib.error  # noqa: E402  (kept after helper for readability)


class TerminalRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        cls.tmp = Path(tempfile.mkdtemp(prefix="v10_termapi_"))
        cls.rt = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(cls.tmp)]))
        cls.srv = serve(cls.rt, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.srv.shutdown()
            cls.srv.server_close()
        except Exception:
            pass
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_create_list_get(self):
        code, created = _api(self.port, "POST", "/v1/terminal/sessions", {})
        self.assertEqual(code, 201)
        sid = created["session_id"]
        code, listed = _api(self.port, "GET", "/v1/terminal/sessions")
        self.assertEqual(code, 200)
        self.assertTrue(any(s["session_id"] == sid
                            for s in listed["sessions"]))
        code, got = _api(self.port, "GET", f"/v1/terminal/sessions/{sid}")
        self.assertEqual(code, 200)
        self.assertEqual(got["session_id"], sid)
        code, _ = _api(self.port, "GET", "/v1/terminal/sessions/term-missing")
        self.assertEqual(code, 404)

    def test_exec_and_policy_deny(self):
        code, created = _api(self.port, "POST", "/v1/terminal/sessions", {})
        sid = created["session_id"]
        code, res = _api(self.port, "POST",
                         f"/v1/terminal/sessions/{sid}/exec",
                         {"command": "python --version", "origin": "agent"})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        self.assertIn("Python", res["stdout"])
        self.assertEqual(res["origin"], "agent")
        code, denied = _api(self.port, "POST",
                            f"/v1/terminal/sessions/{sid}/exec",
                            {"command": "format F:"})
        self.assertEqual(code, 200)
        self.assertFalse(denied["ok"])
        self.assertIn("POLICY_DENIED", denied["error"])
        code, missing = _api(self.port, "POST",
                             "/v1/terminal/sessions/term-missing/exec",
                             {"command": "echo hi"})
        self.assertEqual(code, 404)
        code, bad = _api(self.port, "POST",
                         f"/v1/terminal/sessions/{sid}/exec", {})
        self.assertEqual(code, 400)

    def test_cancel_idle(self):
        code, created = _api(self.port, "POST", "/v1/terminal/sessions", {})
        sid = created["session_id"]
        code, res = _api(self.port, "POST",
                         f"/v1/terminal/sessions/{sid}/cancel")
        self.assertEqual(code, 200)
        self.assertEqual(res["state"], "NOT_RUNNING")

    def test_schema_lists_terminal(self):
        code, schema = _api(self.port, "GET", "/v1/schema")
        self.assertEqual(code, 200)
        paths = [r["path"] for r in schema["routes"]]
        self.assertIn("/v1/terminal/sessions", paths)
        self.assertIn("/v1/terminal/sessions/{id}/exec", paths)


if __name__ == "__main__":
    unittest.main()
