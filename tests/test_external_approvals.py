"""External human-approval channel + effect truth for served sessions.

Two defects proved this module exists:

D1  ``AgentRuntime.create_session`` hard-coded ``non_interactive=True``, so a
    session served over HTTP could never surface a ``pending_approvals`` entry.
    An ASK_* session therefore did not ask a human: every action needing a
    decision was silently denied (``policy.ApprovalManager`` non-interactive
    branch) while the client kept polling an approval list that was always
    empty. The human-in-the-loop loop was unreachable, not merely unused.

D2  A run whose every requested mutation was denied still ended COMPLETED
    with a positive reviewer verdict, so a caller rendering "done" would show a
    green task for work that never happened. ``build_task_result`` now derives
    effect truth from the execution journal and the recorded authority
    decisions: ``effect_achieved`` / ``denied_actions`` / ``blocked``.

The channel stays off by default and is refused rather than silently enabled.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from client import AgentRuntimeClient, ClientError
from runtime import AgentRuntime, RuntimeConfig
from service import serve
from tests.helpers import FakeProvider

WRITE_SCRIPT = ['{"action":"write","path":"gate.txt","content":"ok"}',
                '{"action":"finish","message":"done"}']
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "ROLLED_BACK", "INTERRUPTED")


def _factory(script, model="fake-m"):
    provs: dict[str, FakeProvider] = {}

    def make(role: str) -> FakeProvider:
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


class _Harness:
    """In-process runtime + real HTTP service on an ephemeral port."""

    def __init__(self, external_approvals: bool = True, script=None,
                 token: str = ""):
        self.tmp = Path(tempfile.mkdtemp(prefix="extappr_"))
        self.script = list(script or WRITE_SCRIPT)
        self.rt = AgentRuntime(
            RuntimeConfig(allowed_workspace_roots=[str(self.tmp)],
                          external_approvals=external_approvals,
                          token=token),
            provider_factory=_factory(self.script))
        self.srv = serve(self.rt, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        self.ws = self.tmp / "proj"
        self.ws.mkdir()

    def client(self, token: str = "") -> AgentRuntimeClient:
        return AgentRuntimeClient(f"http://127.0.0.1:{self.port}", token=token)

    def raw(self, method: str, path: str, body=None, token: str = ""):
        data = json.dumps(body or {}).encode() if method == "POST" else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     data=data, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
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

    # -- shared assertions ------------------------------------------------
    def wait_pending(self, c: AgentRuntimeClient, sid: str,
                     timeout: float = 30.0) -> list[str]:
        end = time.time() + timeout
        while time.time() < end:
            pending = list(c.session_status(sid).get("pending_approvals") or [])
            if pending:
                return pending
            time.sleep(0.1)
        return []

    def wait_terminal(self, c: AgentRuntimeClient, sid: str, tid: str,
                      timeout: float = 60.0) -> dict:
        end = time.time() + timeout
        st: dict = {}
        while time.time() < end:
            st = c.session_status(sid)
            if st.get("tasks", {}).get(tid) in TERMINAL:
                return st
            time.sleep(0.2)
        self.fail(f"task {tid} never reached a terminal state: "
                  f"{st.get('tasks')}")


class TestChannelIsOptIn(unittest.TestCase):
    """Authority is never widened silently: no channel, no session."""

    def setUp(self):
        self.h = _Harness(external_approvals=False)
        self.addCleanup(self.h.close)

    def test_interactive_session_refused_when_channel_disabled(self):
        c = self.h.client()
        with self.assertRaises(ClientError) as ctx:
            c.create_session(str(self.h.ws), mode="build",
                             approval="ASK_ALL_WRITES", interactive=True)
        self.assertIn("not enabled", str(ctx.exception))

    def test_default_session_is_not_interactive(self):
        c = self.h.client()
        s = c.create_session(str(self.h.ws), mode="build")
        self.assertFalse(s.get("interactive"))
        st = c.session_status(s["session_id"])
        self.assertFalse(st.get("interactive"))
        self.assertEqual(st.get("pending_approvals"), [])

    def test_capabilities_advertise_the_channel_as_closed(self):
        caps = self.h.client().capabilities()
        self.assertFalse(caps.get("external_approvals"))
        self.assertFalse(caps.get("interactive_session_opt_in"))

    def test_ask_is_denied_not_auto_answered(self):
        """The pre-existing fail-closed behavior must be preserved."""
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES")["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        self.h.wait_terminal(c, sid, tid)
        self.assertFalse((self.h.ws / "gate.txt").exists())
        self.assertEqual(c.session_status(sid)["pending_approvals"], [])


class TestExternalApprovalOverHTTP(unittest.TestCase):
    def setUp(self):
        self.h = _Harness(external_approvals=True)
        self.addCleanup(self.h.close)

    def test_capabilities_advertise_the_channel_as_open(self):
        caps = self.h.client().capabilities()
        self.assertTrue(caps.get("external_approvals"))
        self.assertTrue(caps.get("interactive_session_opt_in"))

    def test_ask_pauses_and_surfaces_pending_approval(self):
        c = self.h.client()
        s = c.create_session(str(self.h.ws), mode="build",
                             approval="ASK_ALL_WRITES", interactive=True)
        sid = s["session_id"]
        self.assertTrue(s.get("interactive"))
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        pending = self.h.wait_pending(c, sid)
        self.assertEqual(len(pending), 1, "an ask must reach the client")
        aid = pending[0]
        # paused, not silently denied: session waits, no effect yet
        self.assertEqual(c.session_status(sid)["status"], "WAITING_APPROVAL")
        self.assertFalse((self.h.ws / "gate.txt").exists())
        kinds = {e.get("event") for e in c.events(sid)["events"]}
        self.assertIn("approval.requested", kinds)
        # unknown approval ids are refused, not guessed
        code, body = self.h.raw(
            "POST", f"/v1/sessions/{sid}/approvals/ap-does-not-exist",
            {"decision": "approve-once"})
        self.assertEqual(code, 404)
        self.assertIn("unknown approval", body.get("error", ""))
        c.approve(sid, aid, "approve-once")

    def test_approve_executes_the_bounded_action(self):
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES",
                               interactive=True)["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        pending = self.h.wait_pending(c, sid)
        self.assertTrue(pending)
        c.approve(sid, pending[0], "approve-once")
        self.h.wait_terminal(c, sid, tid)
        self.assertTrue((self.h.ws / "gate.txt").exists())
        self.assertEqual((self.h.ws / "gate.txt").read_text(), "ok")
        exp = c.export(sid, tid)["task_result"]
        self.assertTrue(exp.get("effect_achieved"))
        self.assertEqual(exp.get("denied_actions"), 0)
        self.assertFalse(exp.get("blocked"))
        man = c.manifest(sid)
        self.assertTrue(any("gate.txt" in (ch.get("path") or "")
                            for ch in man.get("changes", [])))

    def test_approval_does_not_leave_a_standing_grant(self):
        """"Approve once" must mean once. After the approved write has been
        dispatched the single-action grant is gone, so the same capability on
        the same resource is not authorized for the rest of the session.
        """
        from aether_policy_bridge import (evaluate_capability_request,
                                          workspace_subject)
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES",
                               interactive=True)["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        pending = self.h.wait_pending(c, sid)
        self.assertTrue(pending)
        c.approve(sid, pending[0], "approve-once")
        self.h.wait_terminal(c, sid, tid)
        self.assertTrue((self.h.ws / "gate.txt").exists())
        # the policy layer must hold no grant for this session/resource now
        resource = f"workspace:{self.h.ws.resolve()}/gate.txt"
        after = evaluate_capability_request(
            subject=workspace_subject(str(self.h.ws), sid),
            capability="filesystem:write", resource=resource,
            context={"timestamp": int(time.time()), "network_origin": "local",
                     "device_trust": 100, "attributes": {}}, principal=None)
        self.assertFalse(after["allowed"],
                         "an approval left a standing grant behind")

    def test_deny_is_enforced_and_reported_as_no_effect(self):
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES",
                               interactive=True)["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        pending = self.h.wait_pending(c, sid)
        self.assertTrue(pending)
        c.deny(sid, pending[0])
        self.h.wait_terminal(c, sid, tid)
        self.assertFalse((self.h.ws / "gate.txt").exists())
        exp = c.export(sid, tid)["task_result"]
        # D2: the run ended, but the effect truth is unambiguous
        self.assertFalse(exp.get("effect_achieved"))
        self.assertEqual(exp.get("denied_actions"), 1)
        self.assertTrue(exp.get("blocked"))
        # the refusal is recorded as an approval decision, not a silent skip
        self.assertIn("deny", [a.get("decision") for a in exp.get("approvals", [])])
        self.assertTrue(any(e.get("kind") == "APPROVAL_DENIED"
                            for e in exp.get("errors", [])))
        kinds = [e.get("event") for e in c.events(sid)["events"]]
        self.assertIn("approval.requested", kinds)
        self.assertIn("approval.resolved", kinds)

    def test_deny_then_approve_still_refuses(self):
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES",
                               interactive=True)["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        pending = self.h.wait_pending(c, sid)
        self.assertTrue(pending)
        c.deny(sid, pending[0])
        self.h.wait_terminal(c, sid, tid)
        with self.assertRaises(ClientError):
            c.approve(sid, pending[0], "approve-once")
        self.assertFalse((self.h.ws / "gate.txt").exists())

    def test_bad_decision_refused(self):
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES",
                               interactive=True)["session_id"]
        c.submit_task(sid, "write gate.txt then finish")
        pending = self.h.wait_pending(c, sid)
        self.assertTrue(pending)
        with self.assertRaises(ClientError):
            c.approve(sid, pending[0], "definitely-yes")
        c.deny(sid, pending[0])

    def test_auto_safe_session_still_auto_approves_safe_writes(self):
        """The channel must not turn safe automation into an ask-fest."""
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="AUTO_SAFE",
                               interactive=True)["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        self.h.wait_terminal(c, sid, tid)
        self.assertTrue((self.h.ws / "gate.txt").exists())
        self.assertEqual(c.session_status(sid)["pending_approvals"], [])

    def test_cancellation_ends_a_waiting_approval(self):
        c = self.h.client()
        sid = c.create_session(str(self.h.ws), mode="build",
                               approval="ASK_ALL_WRITES",
                               interactive=True)["session_id"]
        tid = c.submit_task(sid, "write gate.txt then finish")["task_id"]
        self.assertTrue(self.h.wait_pending(c, sid))
        c.cancel(sid, tid)
        st = self.h.wait_terminal(c, sid, tid)
        self.assertEqual(st["tasks"][tid], "CANCELLED")
        self.assertFalse((self.h.ws / "gate.txt").exists())

    def test_token_enforced_on_the_approval_channel(self):
        svc = _Harness(external_approvals=True, token="secret-x")
        try:
            c = svc.client(token="secret-x")
            sid = c.create_session(str(svc.ws), mode="build",
                                   approval="ASK_ALL_WRITES",
                                   interactive=True)["session_id"]
            c.submit_task(sid, "write gate.txt then finish")
            pending = svc.wait_pending(c, sid)
            self.assertTrue(pending)
            # an unauthenticated caller cannot resolve the pending decision
            code, _ = svc.raw(
                "POST", f"/v1/sessions/{sid}/approvals/{pending[0]}",
                {"decision": "approve-once"})
            self.assertEqual(code, 401)
            c.deny(sid, pending[0])
        finally:
            svc.close()


class TestOwnerProfileHasNoDeadChannel(unittest.TestCase):
    def test_owner_auto_approve_profile_is_not_interactive(self):
        tmp = Path(tempfile.mkdtemp(prefix="extappr_own_"))
        try:
            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)],
                                            external_approvals=True))
            s = rt.create_session(str(tmp), mode="build",
                                  approval="OWNER_AUTO_APPROVE",
                                  interactive=True)
            self.assertTrue(s.bridge_cfg.non_interactive)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestApprovedActionGrantIsNarrow(unittest.TestCase):
    """D3: an approval verdict is authority, so it must reach the policy layer
    as exactly one effect. These tests are the mutation targets: each one
    fails if a grant becomes a pattern, a standing capability, or if a
    resource the action touches stops being checked."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="extgrant_"))
        self.ws = self.tmp / "proj"
        self.ws.mkdir()
        self.sid = "s-grant-test"
        from aether_policy_bridge import reset_policy_engine
        reset_policy_engine()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(reset_policy_engine)

    def _eval(self, action: str, resource: str, sid: str = "") -> dict:
        from aether_policy_bridge import (evaluate_capability_request,
                                          workspace_subject)
        from executor import Executor
        subject = workspace_subject(str(self.ws), sid or self.sid)
        norm = str(resource).replace("\\", "/")
        if not norm.startswith("workspace:"):
            norm = f"workspace:{self.ws.resolve()}/{norm}"
        return evaluate_capability_request(
            subject=subject,
            capability=f"filesystem:{action}",
            resource=norm,
            context={"timestamp": int(time.time()), "network_origin": "local",
                     "device_trust": 100, "attributes": {}},
            principal=None)

    def _issue(self, resource: str, action: str = "write") -> dict:
        from aether_policy_bridge import issue_approved_action_grant
        return issue_approved_action_grant(self.sid, str(self.ws), action,
                                          resource, granted_by="approval:test")

    def test_approved_write_authorizes_exactly_that_file(self):
        self.assertTrue(self._issue("a.txt")["granted"])
        self.assertTrue(self._eval("write", "a.txt")["allowed"])
        # same capability, different file: still denied
        self.assertFalse(self._eval("write", "b.txt")["allowed"])
        # different capability, same file: still denied
        self.assertFalse(self._eval("delete", "a.txt")["allowed"])
        # another session: still denied
        self.assertFalse(self._eval("write", "a.txt", sid="s-other")["allowed"])

    def test_glob_resources_are_never_granted(self):
        for pattern in ("**", "a/*.py", "a/?.txt", "a/[ab].txt", "{a,b}.txt"):
            out = self._issue(pattern)
            self.assertFalse(out["granted"], pattern)
            self.assertIn("concrete", out["reason"])
        # and nothing was authorized by the attempt
        self.assertFalse(self._eval("write", "a.txt")["allowed"])
        self.assertFalse(self._eval("write", "x/y.txt")["allowed"])

    def test_a_glob_filename_would_not_become_a_workspace_grant(self):
        """Regression shape: the engine treats a trailing /** as a prefix
        grant, so a model-chosen literal named '**' must not be grantable."""
        out = self._issue("**")
        self.assertFalse(out["granted"])
        self.assertFalse(self._eval("write", "secret.txt")["allowed"])

    def test_workspace_escape_is_never_granted(self):
        for escape in ("../../outside.txt", "..\\..\\outside.txt",
                       f"{self.ws.resolve()}/../outside.txt",
                       "/etc/passwd"):
            out = self._issue(escape)
            self.assertFalse(out["granted"], escape)

    def test_absolute_and_namespaced_references_are_refused(self):
        """Re-rooting an absolute path under the workspace names a different
        string than the sandbox resolves: refused, never guessed."""
        for ref in (f"{self.ws.resolve()}/a.txt", "workspace:elsewhere/a.txt",
                    "/workspace/a.txt"):
            self.assertFalse(self._issue(ref)["granted"], ref)

    def test_grant_is_single_use(self):
        from aether_policy_bridge import revoke_approved_action_grant
        self.assertTrue(self._issue("a.txt")["granted"])
        self.assertTrue(self._eval("write", "a.txt")["allowed"])
        self.assertTrue(revoke_approved_action_grant(self.sid, str(self.ws),
                                                     "write", "a.txt"))
        self.assertFalse(self._eval("write", "a.txt")["allowed"])

    def test_revoking_an_ungranted_resource_is_harmless(self):
        from aether_policy_bridge import revoke_approved_action_grant
        self.assertFalse(revoke_approved_action_grant(self.sid, str(self.ws),
                                                      "write", "never.txt"))
        self.assertFalse(revoke_approved_action_grant(self.sid, str(self.ws),
                                                      "write", "**"))

    def test_executor_gates_every_touched_resource(self):
        """move/copy write a second path: it must be gated too."""
        ex_actions = [
            {"action": "write", "path": "a.txt", "content": "x"},
            {"action": "move", "src": "a.txt", "dest": "sub/b.txt"},
            {"action": "copy", "src": "a.txt", "dest": "sub/c.txt"},
            {"action": "shell", "command": "python x.py"},
        ]
        from executor import Executor
        self.assertEqual(Executor.policy_resources(ex_actions[0]), ["a.txt"])
        self.assertEqual(Executor.policy_resources(ex_actions[1]),
                         ["a.txt", "sub/b.txt"])
        self.assertEqual(Executor.policy_resources(ex_actions[2]),
                         ["a.txt", "sub/c.txt"])
        self.assertEqual(Executor.policy_resources(ex_actions[3]), ["python x.py"])

    def test_approved_move_cannot_carry_an_unchecked_destination(self):
        """Only the source is approved: the destination has no grant, so the
        executor must refuse rather than execute half an approved action."""
        from executor import Executor
        from aether_policy_bridge import issue_session_workspace_grants
        issue_session_workspace_grants(self.sid, str(self.ws), "ASK_ALL_WRITES")
        self.assertTrue(self._issue("a.txt", action="move")["granted"])
        ex = Executor(self.ws, session_id=self.sid)
        out = ex.dispatch({"action": "move", "src": "a.txt", "dest": "b.txt"})
        self.assertFalse(out["ok"])
        self.assertEqual(out.get("kind"), "POLICY_DENIED")
        self.assertFalse((self.ws / "b.txt").exists())

    def test_full_move_executes_when_both_sides_are_approved(self):
        from executor import Executor
        from aether_policy_bridge import issue_session_workspace_grants
        issue_session_workspace_grants(self.sid, str(self.ws), "ASK_ALL_WRITES")
        (self.ws / "a.txt").write_text("payload", encoding="utf-8")
        self.assertTrue(self._issue("a.txt", action="move")["granted"])
        self.assertTrue(self._issue("b.txt", action="move")["granted"])
        ex = Executor(self.ws, session_id=self.sid)
        out = ex.dispatch({"action": "move", "src": "a.txt", "dest": "b.txt"})
        self.assertTrue(out["ok"], out)
        self.assertTrue((self.ws / "b.txt").exists())
        self.assertFalse((self.ws / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
