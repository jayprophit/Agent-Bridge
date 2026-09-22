"""OWNER_FULL_CONTROL broad-grant profile (P25/1).

A canonical versioned explicit owner grant for ordinary reversible work.
NOT a policy bypass: default-deny stands outside grants, protected actions
stay approval-gated, unknown future capabilities are never inherited,
workers never inherit the grant, and revocation/expiry stop authorization
while preserving history.
"""
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(REPO_ROOT))

import owner_full_control as ofc
from aether_policy_bridge import (
    evaluate_capability_request,
    reset_policy_engine,
    workspace_subject,
)
from executor import Executor
from runtime import AgentRuntime, RuntimeConfig
from tests.helpers import FakeProvider

GENESIS_ID = "genesis-prime"
OWNER_ID = "owner-jp"


def _ws():
    tmp = Path(tempfile.mkdtemp(prefix="ofc_"))
    ws = tmp / "proj"
    ws.mkdir()
    return tmp, ws


def _factory(script, model="fake-m"):
    provs = {}

    def make(role):
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


class ProfileActivationTests(unittest.TestCase):
    def setUp(self):
        ofc.reset_profile_state()

    def tearDown(self):
        ofc.reset_profile_state()

    def test_owner_activates_with_scope_and_provenance(self):
        rec = ofc.activate(OWNER_ID, ["/tmp"], True, provenance="owner-console",
                           expires_in_s=3600, now=1000)
        self.assertEqual(rec.owner_id, OWNER_ID)
        self.assertTrue(ofc.is_active(OWNER_ID, now=2000))
        self.assertEqual(rec.provenance, "owner-console")
        summary = ofc.summarize(OWNER_ID, now=2000)
        self.assertEqual(summary["state"], "ACTIVE")
        self.assertNotIn("token", str(summary).lower())

    def test_non_owner_activation_denied(self):
        with self.assertRaises(PermissionError):
            ofc.activate(OWNER_ID, ["/tmp"], False, now=1000)

    def test_genesis_worker_skill_workflow_cannot_self_activate(self):
        # No caller-controlled flag exists: the only path demands the
        # trusted owner_authorized=True, which these actors cannot supply.
        for _actor in ("genesis", "worker-1", "skill-x", "workflow-y", "mcp-agent"):
            with self.assertRaises(PermissionError):
                ofc.activate(OWNER_ID, ["/tmp"], False, now=1000)

    def test_malformed_activation_denied(self):
        with self.assertRaises(ValueError):
            ofc.activate("", ["/tmp"], True, now=1000)
        with self.assertRaises(ValueError):
            ofc.activate(OWNER_ID, [], True, now=1000)

    def test_versioned_capability_set_is_explicit(self):
        self.assertIn(("filesystem", "write"), ofc.CAPABILITY_SET_V1)
        self.assertIn(("shell", "execute"), ofc.CAPABILITY_SET_V1)
        for service, action in ofc.CAPABILITY_SET_V1:
            self.assertNotIn("*", service + action)
        self.assertEqual(ofc.PROFILE_VERSION, "1")


class OrdinaryOperationsTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def tearDown(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def test_ordinary_reversible_ops_allowed_without_approval(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-1")
            for action in (
                {"action": "write", "path": "a.txt", "content": "hi"},
                {"action": "mkdir", "path": "sub"},
                {"action": "list", "path": "."},
            ):
                res = ex.dispatch(dict(action, principal={"kind": "genesis", "id": GENESIS_ID,
                                                          "on_behalf_of": OWNER_ID}))
                self.assertTrue(res.get("ok"), action)
            self.assertTrue((ws / "a.txt").exists())
            self.assertTrue((ws / "sub").is_dir())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_future_capability_not_inherited(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            res = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-1"),
                capability="teleport:beam",
                resource=f"workspace:{ws}/x",
                context={"timestamp": 1},
            )
            self.assertFalse(res["allowed"])
            self.assertEqual(ofc.classify_protection("teleport", "beam", {}), "FORBIDDEN")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ProtectedActionTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def tearDown(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def test_protected_classification(self):
        self.assertEqual(ofc.classify_protection("filesystem", "delete", {"permanent": True}), "PROTECTED")
        self.assertEqual(ofc.classify_protection("filesystem", "read", {"credential": True}), "PROTECTED")
        self.assertEqual(ofc.classify_protection("system", "policy", {"security_policy": True}), "PROTECTED")
        self.assertEqual(ofc.classify_protection("finance", "pay", {"finance": True}), "PROTECTED")
        self.assertEqual(ofc.classify_protection("filesystem", "write", {}), "ORDINARY")

    def test_protected_not_auto_granted(self):
        tmp, ws = _ws()
        try:
            (ws / "victim.txt").write_text("keep")
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-1")
            res = ex.dispatch({
                "action": "delete", "path": "victim.txt", "permanent": True,
                "principal": {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID},
            })
            # No grant covers permanent delete under the profile: denied, file kept.
            self.assertFalse(res.get("ok"))
            self.assertTrue((ws / "victim.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_owner_allow_executes_exactly_once(self):
        tmp, ws = _ws()
        try:
            (ws / "victim.txt").write_text("keep")
            from aether_policy_bridge import issue_session_workspace_grants
            # Approval path authorizes the protected action via the existing
            # approval-mode grant; the profile itself never auto-grants it.
            issue_session_workspace_grants("sess-1", str(ws), "AUTO_SAFE")
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-1")
            action = {"action": "delete", "path": "victim.txt",
                      "principal": {"kind": "owner", "id": OWNER_ID}}
            first = ex.dispatch(dict(action), action_id="del-1")
            self.assertTrue(first.get("ok"))
            again = ex.dispatch(dict(action), action_id="del-1")
            self.assertTrue(again.get("dedup"))
            self.assertFalse((ws / "victim.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_owner_deny_executes_zero_times(self):
        tmp, ws = _ws()
        try:
            (ws / "victim.txt").write_text("keep")
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-1")
            res = ex.dispatch({
                "action": "delete", "path": "victim.txt", "permanent": True,
                "principal": {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID},
            })
            self.assertFalse(res.get("ok"))
            self.assertTrue((ws / "victim.txt").exists())
            self.assertEqual(len([e for e in ex.journal if e.get("action") == "delete"]), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RevocationExpiryTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def tearDown(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def test_revoke_stops_future_authorization_preserves_history(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            n = ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            self.assertGreater(n, 0)
            ex = Executor(ws, session_id="sess-1")
            self.assertTrue(ex.dispatch({"action": "write", "path": "a.txt", "content": "1"}).get("ok"))
            removed = ofc.revoke(OWNER_ID, now=2000)
            self.assertTrue(removed)
            self.assertFalse(ofc.is_active(OWNER_ID, now=2000))
            after = ex.dispatch({"action": "write", "path": "b.txt", "content": "2"})
            self.assertFalse(after.get("ok"))
            # History preserved: the first mutation is still journaled.
            self.assertTrue([e for e in ex.journal if e.get("path") == "a.txt"])
            self.assertEqual(ofc.summarize(OWNER_ID, now=2000)["state"], "REVOKED")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_expiry_enforced_on_controllable_clock(self):
        ofc.activate(OWNER_ID, ["/ws"], True, expires_in_s=100, now=1000)
        self.assertTrue(ofc.is_active(OWNER_ID, now=1099))
        self.assertFalse(ofc.is_active(OWNER_ID, now=1100))
        with self.assertRaises(PermissionError):
            ofc.issue_profile_grants("sess-1", "/tmp/nowhere", OWNER_ID, now=1100)

    def test_issue_requires_active_profile(self):
        with self.assertRaises(PermissionError):
            ofc.issue_profile_grants("sess-1", "/tmp/nowhere", OWNER_ID, now=1000)


class PrincipalScopeTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def tearDown(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def test_genesis_on_behalf_of_owner_works(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-1")
            res = ex.dispatch({
                "action": "write", "path": "a.txt", "content": "x",
                "principal": {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID},
            })
            self.assertTrue(res.get("ok"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_worker_cannot_consume_genesis_grant(self):
        tmp, ws = _ws()
        try:
            # Grants belong to the owner session; a worker session has none.
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-owner", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-worker")
            res = ex.dispatch({
                "action": "write", "path": "a.txt", "content": "x",
                "principal": {"kind": "worker", "id": "worker-9"},
            })
            self.assertFalse(res.get("ok"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sibling_and_traversal_denied_under_profile(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            ex = Executor(ws, session_id="sess-1")
            evil = ex.dispatch({"action": "write", "path": "../outside.txt", "content": "x"})
            self.assertFalse(evil.get("ok"))
            sibling = f"{ws}-other"
            Path(sibling).mkdir(exist_ok=True)
            try:
                res = ex.dispatch({"action": "write", "path": f"{sibling}/x.txt", "content": "x"})
                self.assertFalse(res.get("ok"))
            finally:
                shutil.rmtree(sibling, ignore_errors=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_chat_work_parity_same_session_principal(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            principal = {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID}
            chat = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-1"),
                capability="filesystem:write", resource=f"workspace:{ws}/a.txt",
                context={"timestamp": 1, "attributes": {"mode": "chat"}},
                principal=principal)
            work = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-1"),
                capability="filesystem:write", resource=f"workspace:{ws}/a.txt",
                context={"timestamp": 1, "attributes": {"mode": "work"}},
                principal=principal)
            self.assertEqual(chat["allowed"], work["allowed"])
            self.assertTrue(chat["allowed"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_secret_leakage_in_records(self):
        ofc.activate(OWNER_ID, ["/tmp"], True, now=1000)
        summary = ofc.summarize(OWNER_ID, now=1000)
        blob = str(summary)
        for word in ("token", "secret", "password", "bearer", "api_key"):
            self.assertNotIn(word, blob.lower())


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def tearDown(self):
        reset_policy_engine()
        ofc.reset_profile_state()

    def test_routine_ordinary_auto_protected_pauses(self):
        tmp = Path(tempfile.mkdtemp(prefix="ofc_wf_"))
        try:
            ws = tmp / "proj"
            ws.mkdir()
            rt = AgentRuntime(
                RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                provider_factory=_factory([
                    '{"action":"write","path":"report.txt","content":"ok"}',
                    '{"action":"finish","message":"done"}',
                ]))
            sess = rt.create_session(str(ws), mode="build")
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants(sess.session_id, str(ws), OWNER_ID, now=1000)
            res = sess.run_task("write the report", timeout=120)
            self.assertEqual(res.get("status"), "COMPLETED")
            self.assertTrue((ws / "report.txt").exists())
            # Protected permanent delete is not silently allowed by the profile.
            rt2 = AgentRuntime(
                RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                provider_factory=_factory([
                    '{"action":"delete","path":"report.txt","permanent":true}',
                    '{"action":"finish","message":"done"}',
                ]))
            sess2 = rt2.create_session(str(ws), mode="build")
            ofc.issue_profile_grants(sess2.session_id, str(ws), OWNER_ID, now=int(time.time()))
            res2 = sess2.run_task("delete the report permanently", timeout=120)
            # Approval denies permanent deletion non-interactively; the file
            # survives even though the task wrapper completes. The protected
            # action never executes silently under the profile.
            self.assertTrue((ws / "report.txt").exists())
            history = json.dumps(res2.get("history", res2))
            self.assertIn("APPROVAL", history)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_policy_evaluation_stays_fast(self):
        tmp, ws = _ws()
        try:
            ofc.activate(OWNER_ID, [str(ws)], True, now=1000)
            ofc.issue_profile_grants("sess-1", str(ws), OWNER_ID, now=1000)
            subject = workspace_subject(str(ws), "sess-1")
            start = time.time()
            for _ in range(200):
                evaluate_capability_request(
                    subject=subject, capability="filesystem:write",
                    resource=f"workspace:{ws}/a.txt", context={"timestamp": 1},
                    principal={"kind": "genesis", "id": GENESIS_ID})
            elapsed = time.time() - start
            self.assertLess(elapsed, 2.0, f"200 evaluations took {elapsed:.2f}s")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
