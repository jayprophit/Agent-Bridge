"""Recovery and privacy verification on the real chain.

Recovery: interruption at real seams must produce honest states, never
fabricated continuity. A restarted service does not remember in-memory
actions; cancellation wins over execution; deleting an active session is
refused; a gone session reports itself gone.

Privacy: the journal is evidence, not a leak. File contents must never reach
task results, events, exports or errors; paths may appear (they identify the
effect), contents must not. Verified with a canary, not assumed from code
reading.
"""
from __future__ import annotations

import threading
import unittest

from client import AgentRuntimeClient, ClientError
from runtime import AgentRuntime, RuntimeConfig
from service import serve
from tests.test_actions_intake import IntakeBase


class TestRestartBoundary(IntakeBase):
    def test_restarted_service_does_not_invent_outcomes(self):
        r = self.act("rc-1", "write", "rc.txt", payload={"content": "v"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        action_id = "rc-1"
        # kill the service: threads, sessions and the action index die with it
        self.svc.srv.shutdown()
        self.svc.srv.server_close()
        port = self.svc.port
        # a new service over the same workspace knows nothing of the old run
        rt2 = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(self.svc.tmp)]))
        srv2 = serve(rt2, "127.0.0.1", port)
        threading.Thread(target=srv2.serve_forever, daemon=True).start()
        try:
            c2 = AgentRuntimeClient(f"http://127.0.0.1:{port}")
            with self.assertRaises(ClientError) as ctx:
                c2.action_status(action_id)
            # 404 unknown: honest absence, not a reconstructed success
            self.assertIn("404", str(ctx.exception))
        finally:
            srv2.shutdown()
            srv2.server_close()
        # world state survived even though the record did not
        self.assertEqual((self.svc.ws / "rc.txt").read_text(), "v")
        # prevent tearDown double-close noise
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))


class TestSessionLifecycleRecovery(IntakeBase):
    external_approvals = True

    def test_cancel_while_waiting_maps_cancelled(self):
        r = self.act("rc-2", "filesystem:write", "cw.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": "x"}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        self.c.cancel(r["session_id"], r["task_id"])
        final = self.wait_outcome("rc-2")
        self.assertEqual(final["outcome"], "CANCELLED")
        self.assertFalse((self.svc.ws / "cw.txt").exists())

    def test_delete_active_session_refused_then_allowed(self):
        r = self.act("rc-3", "filesystem:write", "dl.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": "x"}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        rt = self.svc.rt
        with self.assertRaises(ValueError):
            rt.delete_session(r["session_id"])
        self.c.cancel(r["session_id"], r["task_id"])
        self.wait_outcome("rc-3")
        out = rt.delete_session(r["session_id"])
        self.assertTrue(out["ok"])

    def test_gone_session_reports_itself_gone(self):
        r = self.act("rc-4", "write", "g.txt", payload={"content": "g"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.svc.rt.delete_session(r["session_id"])
        st = self.c.action_status("rc-4")
        self.assertEqual(st["outcome"], "FAILED")
        self.assertIn("gone", st.get("error", ""))


class TestJournalPrivacy(IntakeBase):
    external_approvals = True

    def test_file_contents_never_reach_results_events_or_errors(self):
        canary = "CANARY-PRIVATE-CONTENT-9f8e7d6c5b4a"
        r = self.act("pv-1", "write", "secret.txt",
                     payload={"content": canary})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        sid, tid = r["session_id"], r["task_id"]
        blobs: list[str] = [str(r)]
        blobs.append(str(self.c.export(sid, tid)))
        blobs.append(str(self.c.events(sid)))
        blobs.append(str(self.c.manifest(sid)))
        blobs.append(str(self.c.scorecard(sid)))
        blobs.append(str(self.c.timeline(sid)))
        blobs.append(str(self.c.session_status(sid)))
        for blob in blobs:
            self.assertNotIn(canary, blob,
                             "file content leaked into readable state")
        # paths identify effects and are expected to appear
        self.assertIn("secret.txt", blobs[1])

    def test_denied_content_boundary(self):
        # Decided boundary, measured not assumed:
        # - the live approval.requested event MUST carry the content (the
        #   human decider cannot judge an action they cannot see);
        # - nothing persisted to disk may carry it (denial must not become
        #   storage): memory/session.json redacts payloads to digests;
        # - results, exports, manifests, scorecards, timelines and errors
        #   never carry it (verified in the companion passing test).
        canary = "CANARY-DENIED-CONTENT-1a2b3c4d5e6f"
        r = self.act("pv-2", "filesystem:write", "denied-secret.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": canary}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        requested = [e for e in self.c.events(r["session_id"])["events"]
                     if e.get("event") == "approval.requested"]
        self.assertTrue(requested, "no approval was ever requested")
        self.assertIn(canary, str(requested),
                      "the approver must see what they are deciding")
        self.c.deny(r["session_id"], r["approval_id"])
        final = self.wait_outcome("pv-2")
        self.assertEqual(final["outcome"], "DENIED")
        mem = self.svc.ws / ".bridge" / "memory" / "session.json"
        self.assertTrue(mem.exists(), "session memory was not persisted")
        persisted = mem.read_text(encoding="utf-8")
        self.assertNotIn(canary, persisted,
                         "denied content persisted to disk")
        # continuity survives redaction: the denial is still recorded, with
        # the decision, the target and a content digest, not the bytes
        self.assertIn("denied-secret.txt", persisted)
        self.assertIn("APPROVAL_DENIED", persisted)


class TestPersistedRedaction(unittest.TestCase):
    def test_payload_values_become_digests(self):
        from memory import redact_persisted
        out = redact_persisted(
            {"action": "write", "path": "a.txt", "content": "secret-bytes"})
        self.assertEqual(out["action"], "write")
        self.assertEqual(out["path"], "a.txt")
        self.assertNotIn("secret-bytes", str(out))
        digest = out["content"]["sha256"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_digests_preserve_equality(self):
        from memory import redact_persisted
        a = redact_persisted({"content": "same"})
        b = redact_persisted({"content": "same"})
        c = redact_persisted({"content": "different"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_nested_and_list_values_redacted(self):
        from memory import redact_persisted
        out = redact_persisted(
            {"edits": [{"old": "x", "new": "y"}], "action": "patch"})
        self.assertNotIn("x", str(out["edits"]))
        self.assertEqual(out["action"], "patch")

    def test_non_payload_keys_untouched(self):
        from memory import redact_persisted
        out = redact_persisted(
            {"action": "write", "path": "a.txt", "decision": "deny",
             "reason": "human said no", "command": "pytest -q"})
        self.assertEqual(out["decision"], "deny")
        self.assertEqual(out["reason"], "human said no")
        self.assertEqual(out["command"], "pytest -q")


if __name__ == "__main__":
    unittest.main()
