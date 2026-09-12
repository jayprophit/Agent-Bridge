"""v0.5: SSE streaming, new service endpoints, contract stability."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from client import AgentRuntimeClient
from runtime import AgentRuntime, RuntimeConfig
from service import api_schema, serve
from tests.helpers import FakeProvider


def _factory(script, model="fake-m"):
    provs: dict[str, FakeProvider] = {}

    def make(role: str) -> FakeProvider:
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


OK_SCRIPT = ['{"action":"write","path":"a.txt","content":"hi"}',
             '{"action":"finish","message":"done"}']


class LiveService:
    def __init__(self, tmp: Path, token: str = ""):
        self.tmp = tmp
        self.rt = AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(tmp)], token=token),
            provider_factory=_factory(list(OK_SCRIPT)))
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


class TestSSE(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v05_sse_"))
        self.svc = LiveService(self.tmp)

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stream_replays_and_terminates(self):
        c = self.svc.client()
        ws = self.tmp / "w"
        ws.mkdir()
        sid = c.create_session(str(ws))["session_id"]
        sub = c.submit_task(sid, "t")
        tid = sub["task_id"]
        end_t = __import__("time").time() + 120
        while __import__("time").time() < end_t:
            if c.session_status(sid)["tasks"].get(tid) == "COMPLETED":
                break
            __import__("time").sleep(2)
        evs = c.stream_events(sid, since=0, timeout=60)
        kinds = set()
        for e in evs:
            kinds.add(str(e.get("event", "")))
        self.assertIn("task.completed", kinds)
        # Last-Event-ID recovery: resume mid-stream, no cross-session leakage
        half = len(evs) // 2
        rest = c.stream_events(sid, since=half, timeout=60)
        self.assertTrue(len(rest) < len(evs))
        for e in rest:
            self.assertNotIn("other-session", json.dumps(e))
        # explicit Last-Event-ID header path also accepted
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.svc.port}/v1/sessions/{sid}/events/stream")
        req.add_header("Last-Event-ID", str(half))
        with urllib.request.urlopen(req, timeout=30) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("text/event-stream", r.headers.get("Content-Type", ""))
            body = r.read().decode()
            self.assertIn("data:", body)

    def test_stream_token_enforced(self):
        import urllib.request
        import urllib.error
        svc2 = LiveService(self.tmp, token="tok")
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{svc2.port}/v1/sessions/x/events/stream")
            try:
                urllib.request.urlopen(req, timeout=10)
                self.fail("expected 401")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 401)
        finally:
            svc2.close()


class TestNewEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v05_ep_"))
        self.svc = LiveService(self.tmp)
        self.c = self.svc.client()
        self.ws = self.tmp / "w"
        self.ws.mkdir()
        self.sid = self.c.create_session(str(self.ws))["session_id"]
        tid = self.c.submit_task(self.sid, "t")["task_id"]
        end_t = __import__("time").time() + 120
        while __import__("time").time() < end_t:
            if self.c.session_status(self.sid)["tasks"].get(tid) == "COMPLETED":
                break
            __import__("time").sleep(2)

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_models_sessions_schema(self):
        inv = self.c.models()
        self.assertTrue(inv.get("models"))
        self.assertNotIn("path", json.dumps(inv).lower())
        lst = self.c._req("GET", "/v1/sessions")
        self.assertEqual(len(lst["sessions"]), 1)
        sch = self.c.schema()
        self.assertIn("/v1/sessions/{id}/events/stream",
                      json.dumps(sch))

    def test_diff_manifest_scorecard_timeline_export(self):
        d = self.c.diff(self.sid)
        self.assertIn("a.txt", d.get("diff", ""))
        m = self.c.manifest(self.sid)
        self.assertTrue(any(x["path"] == "a.txt" for x in m["changes"]))
        sc = self.c.scorecard(self.sid)
        self.assertIn("FILES", sc["scorecard"]["categories"])
        tl = self.c.timeline(self.sid)
        self.assertTrue(tl["timeline"])
        js = self.c.export(self.sid, fmt="json")
        self.assertIn("a.txt", json.dumps(js))
        md = self.c.export(self.sid, fmt="markdown")
        self.assertIn("Scorecard", md if isinstance(md, str) else json.dumps(md))

    def test_final_and_revise_validation(self):
        c = self.c
        try:
            c.resolve_final(self.sid, "t-x", "accept")
            self.fail("expected error")
        except Exception as e:
            self.assertIn("404", str(e))
        st = c.session_status(self.sid)
        tids = list((st.get("task_details") or st.get("tasks", {}) or {}).keys())
        self.assertTrue(tids)
        r = c.request_revision(self.sid, tids[0], "do more checks")
        self.assertIn("child_task_id", r)


class TestContract(unittest.TestCase):
    def test_schema_lists_implemented_routes(self):
        sch = api_schema()
        self.assertEqual(sch["api"], "v1")
        self.assertTrue(any("approvals" in r["path"] for r in sch["routes"]))
        self.assertIn("WAITING_FINAL_APPROVAL", sch["transitions"])

    def test_client_surface_stable(self):
        for meth in ("health", "capabilities", "models", "create_session",
                     "session_status", "submit_task", "events", "cancel",
                     "approve", "rollback", "delete_session", "run_task",
                     "diff", "manifest", "scorecard", "timeline", "export",
                     "stream_events", "request_revision", "resolve_final",
                     "list_sessions", "diagnostics", "selfcheck", "schema"):
            self.assertTrue(callable(getattr(AgentRuntimeClient, meth)), meth)


if __name__ == "__main__":
    unittest.main()
