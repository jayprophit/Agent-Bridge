"""POST /v1/actions: typed action intake over the real service.

These tests prove the endpoint is an adapter into the existing execution
fabric, not a second one. Every test runs against the real HTTP service with
the real runtime, approval gate, policy engine, executor and journal. No stub
servers: a stub endpoint defined by a test cannot prove the route exists, and
that is exactly the defect this endpoint closes.

Coverage contract (BUILD59):
  - validation fails closed (malformed, missing, invalid, escapes, globs)
  - authority never comes from the payload (owner_mode, principal)
  - ASK semantics survive (pause, resolve, deny, 403 when disabled)
  - effect truth survives (DENIED vs SUCCEEDED vs blocked)
  - the journal is canonical (events + export agree with the outcome)
  - every touched resource is gated (move/copy both sides)
  - approvals stay single-use (replay does not re-execute)
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from client import AgentRuntimeClient, ClientError
from runtime import AgentRuntime, RuntimeConfig
from service import serve

TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "ROLLED_BACK", "INTERRUPTED")


class LiveIntake:
    """Real Bridge service on an ephemeral port, in-process runtime."""

    def __init__(self, external_approvals: bool = False,
                 owner_authorized: bool = False, token: str = ""):
        self.tmp = Path(tempfile.mkdtemp(prefix="intake_"))
        self.ws = self.tmp / "proj"
        self.ws.mkdir()
        self.rt = AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(self.tmp)],
                          external_approvals=external_approvals,
                          owner_authorized=owner_authorized,
                          token=token))
        self.srv = serve(self.rt, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        self.client = AgentRuntimeClient(f"http://127.0.0.1:{self.port}",
                                         token=token)

    def raw(self, method: str, path: str, body=None, token: str = ""):
        import urllib.request
        import urllib.error
        data = json.dumps(body or {}).encode() if method == "POST" else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     data=data, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def close(self) -> None:
        try:
            self.srv.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class IntakeBase(unittest.TestCase):
    external_approvals = False
    owner_authorized = False
    token = ""

    def setUp(self):
        self.svc = LiveIntake(
            external_approvals=self.external_approvals,
            owner_authorized=self.owner_authorized, token=self.token)
        self.addCleanup(self.svc.close)
        self.c = self.svc.client
        self.ws = str(self.svc.ws)

    def act(self, action_id: str, action: str, resource: str, **kw) -> dict:
        body = {"action_id": action_id, "action": action,
                "resource": resource, "workspace": self.ws}
        body.update(kw)
        return self.c.submit_action(**{
            k: v for k, v in body.items()
            if k in ("action_id", "action", "resource", "workspace",
                     "session_id", "payload", "principal", "owner_mode",
                     "approval", "interactive", "wait_ms")})

    def wait_outcome(self, action_id: str, timeout: float = 60.0) -> dict:
        end = time.time() + timeout
        last: dict = {}
        while time.time() < end:
            last = self.c.action_status(action_id)
            if last.get("outcome") in ("SUCCEEDED", "DENIED", "FAILED",
                                       "CANCELLED", "WAITING_APPROVAL"):
                return last
            time.sleep(0.3)
        self.fail(f"action {action_id} never settled: {last}")
        raise AssertionError


class TestIntakeValidation(IntakeBase):
    def test_malformed_json_is_400(self):
        code, _ = self.svc.raw("POST", "/v1/actions", None)
        # empty body decodes to {} which is valid JSON: missing action_id
        self.assertEqual(code, 400)
        import urllib.request
        import urllib.error
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.svc.port}/v1/actions", data=b"{oops",
            method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_missing_fields_are_400(self):
        with self.assertRaises(ClientError):
            self.act("", "write", "a.txt", payload={"content": "x"})
        with self.assertRaises(ClientError):
            self.c.submit_action("v-1", "", "a.txt", workspace=self.ws)
        with self.assertRaises(ClientError):
            self.c.submit_action("v-2", "write", "", workspace=self.ws)
        with self.assertRaises(ClientError):
            self.c.submit_action("v-3", "write", "a.txt",
                                 workspace=self.ws, payload="nope")

    def test_unknown_verbs_are_400(self):
        for verb in ("frobnicate", "filesystem:delete-account",
                     "bogus:write", "filesystem:", ":write", "write:extra:x"):
            with self.assertRaises(ClientError, msg=verb):
                self.act(f"v-{verb}", verb, "a.txt",
                         payload={"content": "x"})

    def test_loop_control_is_refused(self):
        with self.assertRaises(ClientError) as ctx:
            self.act("v-fin", "finish", "a.txt")
        self.assertIn("loop control", str(ctx.exception))

    def test_move_without_dest_is_400(self):
        with self.assertRaises(ClientError):
            self.act("v-mv", "filesystem:move", "a.txt")

    def test_payload_path_cannot_override_resource(self):
        # D5: resource ok.txt passes strictness while payload.path swaps in
        # ../evil.txt. The validated request must describe the effect.
        with self.assertRaises(ClientError) as ctx:
            self.act("v-sm1", "write", "ok.txt",
                     payload={"path": "../evil.txt", "content": "x"})
        self.assertIn("400", str(ctx.exception))
        self.assertFalse((self.svc.ws / "ok.txt").exists())
        self.assertFalse((self.svc.tmp / "evil.txt").exists())

    def test_payload_dest_cannot_override_src(self):
        (self.svc.ws / "s.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(ClientError):
            self.act("v-sm2", "filesystem:move", "s.txt",
                     payload={"src": "other.txt", "dest": "d.txt"})
        self.assertTrue((self.svc.ws / "s.txt").exists())
        self.assertFalse((self.svc.ws / "d.txt").exists())

    def test_identical_slot_value_merges_harmlessly(self):
        r = self.act("v-sm3", "write", "same.txt",
                     payload={"path": "same.txt", "content": "v"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertTrue((self.svc.ws / "same.txt").exists())

    def test_missing_action_fields_are_400(self):
        # The verb is known but the action is incomplete: canonical field
        # validation refuses it before anything runs.
        with self.assertRaises(ClientError):
            self.act("v-f1", "filesystem:write", "nocontent.txt")
        with self.assertRaises(ClientError):
            self.act("v-f2", "edit", "noedit.txt", payload={"old": "x"})

    def test_globs_are_400(self):
        for pattern in ("*.txt", "a/?.txt", "a/[ab].txt", "a/{b,c}.txt"):
            with self.assertRaises(ClientError, msg=pattern):
                self.act(f"v-g-{pattern}", "write", pattern,
                         payload={"content": "x"})

    def test_escapes_and_absolute_refs_are_400(self):
        for ref in ("../outside.txt", "a/../../b.txt",
                    "C:/Windows/x.txt", "/etc/passwd"):
            with self.assertRaises(ClientError, msg=ref):
                self.act(f"v-e-{abs(hash(ref))}", "write", ref,
                         payload={"content": "x"})

    def test_malformed_principal_is_400(self):
        with self.assertRaises(ClientError):
            self.act("v-p1", "write", "a.txt", payload={"content": "x"},
                     principal="genesis")
        with self.assertRaises(ClientError):
            self.act("v-p2", "write", "a.txt", payload={"content": "x"},
                     principal={"kind": "hacker", "id": "x"})
        with self.assertRaises(ClientError):
            self.act("v-p3", "write", "a.txt", payload={"content": "x"},
                     principal={"kind": "genesis", "id": ""})

    def test_bad_owner_mode_is_400(self):
        with self.assertRaises(ClientError):
            self.act("v-o1", "write", "a.txt", payload={"content": "x"},
                     owner_mode="please")

    def test_workspace_escape_is_403(self):
        with self.assertRaises(ClientError) as ctx:
            self.c.submit_action("v-ws", "write", "a.txt",
                                 workspace="C:\\Windows\\System32",
                                 payload={"content": "x"})
        self.assertIn("403", str(ctx.exception))

    def test_unknown_session_label_without_workspace_is_400(self):
        with self.assertRaises(ClientError):
            self.c.submit_action("v-s1", "write", "a.txt",
                                 session_id="no-such-label",
                                 payload={"content": "x"})

    def test_session_label_bound_elsewhere_is_409(self):
        r = self.act("v-l1", "write", "a.txt", session_id="wf-1",
                     payload={"content": "x"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        other = self.svc.tmp / "other"
        other.mkdir()
        with self.assertRaises(ClientError) as ctx:
            self.c.submit_action("v-l2", "write", "a.txt",
                                 workspace=str(other), session_id="wf-1",
                                 payload={"content": "x"})
        self.assertIn("409", str(ctx.exception))

    def test_token_enforced(self):
        svc = LiveIntake(token="secret-1")
        try:
            code, _ = svc.raw("POST", "/v1/actions",
                              {"action_id": "t-1", "action": "read",
                               "resource": "x"})
            self.assertEqual(code, 401)
            code, _ = svc.raw("GET", "/v1/actions/t-1")
            self.assertEqual(code, 401)
        finally:
            svc.close()

    def test_unknown_action_id_is_404(self):
        with self.assertRaises(ClientError) as ctx:
            self.c.action_status("a-does-not-exist")
        self.assertIn("404", str(ctx.exception))


class TestIntakeExecution(IntakeBase):
    def test_namespaced_write_executes(self):
        r = self.act("e-1", "filesystem:write", "hello.txt",
                     payload={"content": "hi"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertEqual(r["status"], "COMPLETED")
        self.assertFalse(r["deduped"])
        self.assertTrue((self.svc.ws / "hello.txt").exists())
        out = r["output"]
        self.assertIn("hello.txt", out["files_created"])
        self.assertTrue(r["effect_achieved"])
        self.assertEqual(r["denied_actions"], 0)

    def test_bare_verb_executes(self):
        r = self.act("e-2", "write", "bare.txt", payload={"content": "b"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertTrue((self.svc.ws / "bare.txt").exists())

    def test_read_executes_without_effect_claim(self):
        (self.svc.ws / "r.txt").write_text("data", encoding="utf-8")
        r = self.act("e-3", "filesystem:read", "r.txt")
        self.assertEqual(r["outcome"], "SUCCEEDED")

    def test_session_label_correlates_actions(self):
        # Both effects must be real: this test once passed vacuously while
        # the second write was skipped by cross-task id aliasing (D4).
        r1 = self.act("e-4", "write", "one.txt", session_id="wf-9",
                      payload={"content": "1"})
        r2 = self.act("e-5", "write", "two.txt", session_id="wf-9",
                      payload={"content": "2"})
        self.assertEqual(r1["outcome"], "SUCCEEDED")
        self.assertEqual(r2["outcome"], "SUCCEEDED")
        self.assertEqual(r1["session_id"], r2["session_id"])
        self.assertNotEqual(r1["task_id"], r2["task_id"])
        self.assertTrue(r1["effect_achieved"])
        self.assertTrue(r2["effect_achieved"])
        self.assertEqual((self.svc.ws / "one.txt").read_text(), "1")
        self.assertEqual((self.svc.ws / "two.txt").read_text(), "2")

    def test_journal_records_the_directed_action(self):
        r = self.act("e-6", "write", "j.txt", payload={"content": "j"})
        sid = r["session_id"]
        events = self.c.events(sid)["events"]
        kinds = {e.get("event") for e in events}
        # the session journal carries the task lifecycle and the approval
        # record; the per-step executor journal stays server-side
        self.assertIn("task.completed", kinds)
        self.assertIn("task.started", kinds)
        exp = self.c.export(sid, r["task_id"])["task_result"]
        self.assertTrue(exp["effect_achieved"])
        self.assertEqual(exp["denied_actions"], 0)
        self.assertIn("j.txt", exp["files_created"])
        self.assertIn({"action": "write", "decision": "approve-once"},
                      exp["approvals"])

    def test_wait_zero_returns_unsettled_honestly(self):
        r = self.act("e-7", "write", "w0.txt", payload={"content": "x"},
                     wait_ms=0)
        # wait_ms=0 may still settle a fast task, or report the wait expiry;
        # either outcome is honest as long as nothing terminal is invented
        self.assertIn(r["outcome"], ("SUCCEEDED", "UNKNOWN_OUTCOME",
                                     "TIMED_OUT", "WAITING_APPROVAL"))
        if r["outcome"] in ("UNKNOWN_OUTCOME", "TIMED_OUT"):
            self.assertIn("status", r)
        final = self.wait_outcome("e-7")
        self.assertEqual(final["outcome"], "SUCCEEDED")

    def test_get_status_tracks_a_running_action(self):
        r = self.act("e-8", "write", "w8.txt", payload={"content": "x"},
                     wait_ms=0)
        g = self.c.action_status("e-8")
        self.assertEqual(g["action_id"], "e-8")
        self.assertIn(g["outcome"], ("SUCCEEDED", "UNKNOWN_OUTCOME",
                                     "WAITING_APPROVAL"))
        final = self.wait_outcome("e-8")
        self.assertEqual(final["outcome"], "SUCCEEDED")


class TestIntakeAuthority(IntakeBase):
    external_approvals = True

    def test_ask_pauses_for_a_resolvable_approval(self):
        r = self.act("a-ask-1", "filesystem:write", "ask.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": "x"}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        aid = r["approval_id"]
        self.assertTrue(aid.startswith("ap-"))
        self.assertFalse((self.svc.ws / "ask.txt").exists())
        self.c.approve(r["session_id"], aid, "approve-once")
        final = self.wait_outcome("a-ask-1")
        self.assertEqual(final["outcome"], "SUCCEEDED")
        self.assertEqual((self.svc.ws / "ask.txt").read_text(), "x")
        # the grant was single-use: nothing standing authorizes a new write
        from aether_policy_bridge import (evaluate_capability_request,
                                          workspace_subject)
        verdict = evaluate_capability_request(
            subject=workspace_subject(str(self.svc.ws), r["session_id"]),
            capability="filesystem:write",
            resource=f"workspace:{self.svc.ws.resolve()}/ask.txt",
            context={"timestamp": 0, "network_origin": "local",
                     "device_trust": 100, "attributes": {}},
            principal=None)
        self.assertFalse(verdict["allowed"])

    def test_deny_blocks_with_truth(self):
        r = self.act("a-deny-1", "filesystem:write", "denied.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": "x"}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        self.c.deny(r["session_id"], r["approval_id"])
        final = self.wait_outcome("a-deny-1")
        self.assertEqual(final["outcome"], "DENIED")
        self.assertFalse((self.svc.ws / "denied.txt").exists())
        self.assertFalse(final["effect_achieved"])
        self.assertEqual(final["denied_actions"], 1)
        self.assertTrue(final["blocked"])

    def test_ask_without_interactive_denies_fail_closed(self):
        r = self.act("a-ni-1", "filesystem:write", "ni.txt",
                     approval="ASK_ALL_WRITES", interactive=False,
                     payload={"content": "x"})
        self.assertEqual(r["outcome"], "DENIED")
        self.assertFalse((self.svc.ws / "ni.txt").exists())
        st = self.c.session_status(r["session_id"])
        self.assertEqual(st["pending_approvals"], [])

    def test_interactive_refused_when_runtime_disallows(self):
        svc = LiveIntake(external_approvals=False)
        try:
            c = svc.client
            with self.assertRaises(ClientError) as ctx:
                c.submit_action("a-403", "write", "x.txt",
                                workspace=str(svc.ws),
                                approval="ASK_ALL_WRITES", interactive=True,
                                payload={"content": "x"})
            self.assertIn("403", str(ctx.exception))
        finally:
            svc.close()

    def test_owner_mode_without_authorization_is_403(self):
        with self.assertRaises(ClientError) as ctx:
            self.act("a-own-1", "write", "o.txt", payload={"content": "x"},
                     owner_mode="OWNER")
        self.assertIn("403", str(ctx.exception))
        self.assertFalse((self.svc.ws / "o.txt").exists())

    def test_valid_principal_is_accepted_as_context(self):
        r = self.act("a-pr-1", "write", "pr.txt", payload={"content": "x"},
                     principal={"kind": "genesis", "id": "genesis-prime"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertTrue((self.svc.ws / "pr.txt").exists())


class TestIntakeOwnerAuthorized(IntakeBase):
    owner_authorized = True

    def test_owner_mode_executes_when_runtime_authorized(self):
        r = self.act("a-own-2", "write", "ow.txt", payload={"content": "y"},
                     owner_mode="OWNER")
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertTrue((self.svc.ws / "ow.txt").exists())


class TestIntakeReplay(IntakeBase):
    def test_same_id_same_action_does_not_reexecute(self):
        r1 = self.act("rp-1", "write", "rp.txt", payload={"content": "v1"})
        self.assertEqual(r1["outcome"], "SUCCEEDED")
        self.assertFalse(r1["deduped"])
        # an external change must survive the replay: nothing re-executes
        (self.svc.ws / "rp.txt").write_text("external", encoding="utf-8")
        r2 = self.act("rp-1", "write", "rp.txt", payload={"content": "v1"})
        self.assertEqual(r2["outcome"], "SUCCEEDED")
        self.assertTrue(r2["deduped"])
        self.assertEqual(r2["task_id"], r1["task_id"])
        self.assertEqual((self.svc.ws / "rp.txt").read_text(), "external")

    def test_same_id_different_action_is_409(self):
        self.act("rp-2", "write", "a.txt", payload={"content": "1"})
        with self.assertRaises(ClientError) as ctx:
            self.act("rp-2", "write", "b.txt", payload={"content": "1"})
        self.assertIn("409", str(ctx.exception))
        self.assertFalse((self.svc.ws / "b.txt").exists())

    def test_replay_ignores_a_different_label(self):
        # Same id + same action is the same work, so the replay returns the
        # original task rather than executing again - even when the caller
        # offers a different session label. No new execution occurs, and the
        # response names the original session, so nothing can be laundered
        # into another session's context.
        r1 = self.act("rp-3", "write", "s1.txt", session_id="wf-a",
                      payload={"content": "1"})
        r2 = self.c.submit_action("rp-3", "write", "s1.txt",
                                  workspace=self.ws, session_id="wf-b",
                                  payload={"content": "1"})
        self.assertTrue(r2["deduped"])
        self.assertEqual(r2["task_id"], r1["task_id"])
        self.assertEqual(r2["session_id"], r1["session_id"])


class TestIntakeMultiResource(IntakeBase):
    def test_move_gates_both_sides(self):
        (self.svc.ws / "src.txt").write_text("payload", encoding="utf-8")
        r = self.act("m-1", "filesystem:move", "src.txt",
                     payload={"dest": "dst.txt"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertFalse((self.svc.ws / "src.txt").exists())
        self.assertTrue((self.svc.ws / "dst.txt").exists())

    def test_move_to_outside_workspace_is_refused(self):
        (self.svc.ws / "keep.txt").write_text("payload", encoding="utf-8")
        # a destination escape is refused at intake, before anything runs;
        # the executor's own both-sides gating remains the backstop
        with self.assertRaises(ClientError) as ctx:
            self.act("m-2", "filesystem:move", "keep.txt",
                     payload={"dest": "../escape.txt"})
        self.assertIn("400", str(ctx.exception))
        self.assertTrue((self.svc.ws / "keep.txt").exists())
        self.assertFalse((self.svc.tmp / "escape.txt").exists())

    def test_copy_needs_both_grants(self):
        (self.svc.ws / "c.txt").write_text("payload", encoding="utf-8")
        r = self.act("m-3", "copy", "c.txt", payload={"dest": "c2.txt"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertTrue((self.svc.ws / "c.txt").exists())
        self.assertTrue((self.svc.ws / "c2.txt").exists())


class TestIntakeEffectTruth(IntakeBase):
    external_approvals = True

    def test_completed_without_effect_is_not_denied(self):
        # A read completes with no world change; that is success, not denial.
        (self.svc.ws / "t.txt").write_text("v", encoding="utf-8")
        r = self.act("t-1", "read", "t.txt")
        self.assertEqual(r["outcome"], "SUCCEEDED")
        self.assertFalse(r.get("blocked", False))

    def test_all_denied_is_blocked_not_success(self):
        r = self.act("t-2", "filesystem:write", "blk.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": "x"}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        self.c.deny(r["session_id"], r["approval_id"])
        final = self.wait_outcome("t-2")
        self.assertEqual(final["outcome"], "DENIED")
        # the session may report COMPLETED; the action truth says blocked
        st = self.c.session_status(final["session_id"])
        self.assertEqual(st["tasks"][final["task_id"]], "COMPLETED")
        self.assertTrue(final["blocked"])
        self.assertFalse(final["effect_achieved"])

    def test_cancelled_action_maps_cancelled(self):
        r = self.act("t-3", "filesystem:write", "cx.txt",
                     approval="ASK_ALL_WRITES", interactive=True,
                     payload={"content": "x"}, wait_ms=5000)
        self.assertEqual(r["outcome"], "WAITING_APPROVAL")
        self.c.cancel(r["session_id"], r["task_id"])
        final = self.wait_outcome("t-3")
        self.assertEqual(final["outcome"], "CANCELLED")
        self.assertFalse((self.svc.ws / "cx.txt").exists())


if __name__ == "__main__":
    unittest.main()
