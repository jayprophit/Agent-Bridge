"""Principal/on-behalf-of context for the policy layer.

A principal is validated input + audit context ONLY: it grants no
capability, approves nothing, and cannot widen a grant. Unknown, malformed
and impersonating principals fail closed before any mutation. Worker
principals stay distinct from the Genesis identity; owner and Genesis stay
distinct from each other.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(REPO_ROOT))

from aether_policy_bridge import (
    evaluate_capability_request,
    issue_session_workspace_grants,
    parse_principal,
    reset_policy_engine,
    validate_principal,
    workspace_subject,
)
from executor import Executor

GENESIS_ID = "genesis-prime"
OWNER_ID = "owner-jp"


def _ws():
    tmp = Path(tempfile.mkdtemp(prefix="principal_"))
    ws = tmp / "proj"
    ws.mkdir()
    return tmp, ws


class PrincipalValidationTests(unittest.TestCase):
    def test_absent_principal_is_valid_legacy_path(self):
        self.assertEqual(validate_principal(None), [])
        self.assertIsNone(parse_principal(None))

    def test_valid_genesis_worker_owner_shapes(self):
        self.assertEqual(validate_principal(parse_principal(
            {"kind": "genesis", "id": GENESIS_ID})), [])
        self.assertEqual(validate_principal(parse_principal(
            {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID})), [])
        self.assertEqual(validate_principal(parse_principal(
            {"kind": "worker", "id": "worker-1"})), [])
        self.assertEqual(validate_principal(parse_principal(
            {"kind": "owner", "id": OWNER_ID})), [])

    def test_unknown_kind_missing_id_malformed_rejected(self):
        self.assertTrue(validate_principal(parse_principal(
            {"kind": "assistant", "id": "x"})))
        self.assertTrue(validate_principal(parse_principal(
            {"kind": "genesis", "id": "  "})))
        # Non-dict principals do not parse at all.
        self.assertIsNone(parse_principal("genesis-prime"))
        self.assertIsNone(parse_principal(42))

    def test_worker_cannot_impersonate_genesis(self):
        errors = validate_principal(
            parse_principal({"kind": "worker", "id": GENESIS_ID}), GENESIS_ID)
        self.assertTrue(any("impersonate" in e for e in errors))

    def test_owner_and_genesis_must_stay_distinct(self):
        errors = validate_principal(parse_principal(
            {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": GENESIS_ID}))
        self.assertTrue(any("distinct" in e for e in errors))


class PrincipalPolicyTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()

    def tearDown(self):
        reset_policy_engine()

    def test_valid_principal_allowed_with_grants_and_recorded(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            res = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-a"),
                capability="filesystem:write",
                resource=f"workspace:{ws}/a.txt",
                context={"timestamp": 1},
                principal={"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID},
            )
            self.assertTrue(res["allowed"])
            self.assertIn("genesis:genesis-prime", res["reason"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_invalid_principal_denies_before_grant_check(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            res = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-a"),
                capability="filesystem:write",
                resource=f"workspace:{ws}/a.txt",
                context={"timestamp": 1},
                principal={"kind": "worker", "id": GENESIS_ID},
                genesis_id=GENESIS_ID,
            )
            self.assertFalse(res["allowed"])
            self.assertIn("invalid principal", res["reason"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_malformed_principal_denies(self):
        res = evaluate_capability_request(
            subject="service:agent-bridge",
            capability="filesystem:read",
            resource="x",
            context={"timestamp": 1},
            principal="not-a-principal",
        )
        self.assertFalse(res["allowed"])
        self.assertIn("malformed principal", res["reason"])

    def test_principal_grants_nothing_by_itself(self):
        tmp, ws = _ws()
        try:
            # No grants issued: even a valid Genesis principal is denied.
            res = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-a"),
                capability="filesystem:write",
                resource=f"workspace:{ws}/a.txt",
                context={"timestamp": 1},
                principal={"kind": "genesis", "id": GENESIS_ID},
            )
            self.assertFalse(res["allowed"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cross_session_principal_misuse_denied(self):
        tmp, ws = _ws()
        try:
            # Grants belong to session A; the same principal in session B fails.
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            res = evaluate_capability_request(
                subject=workspace_subject(str(ws), "sess-b"),
                capability="filesystem:write",
                resource=f"workspace:{ws}/a.txt",
                context={"timestamp": 1},
                principal={"kind": "genesis", "id": GENESIS_ID},
            )
            self.assertFalse(res["allowed"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ExecutorPrincipalTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()

    def tearDown(self):
        reset_policy_engine()

    def test_mutation_records_principal_in_journal(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            ex = Executor(ws, session_id="sess-a")
            res = ex.dispatch({
                "action": "write", "path": "a.txt", "content": "hi",
                "principal": {"kind": "genesis", "id": GENESIS_ID, "on_behalf_of": OWNER_ID},
            })
            self.assertTrue(res.get("ok"))
            entries = [e for e in ex.journal if e.get("action") == "write"]
            self.assertTrue(entries)
            self.assertEqual(entries[0].get("principal", {}).get("id"), GENESIS_ID)
            self.assertEqual(entries[0].get("principal", {}).get("on_behalf_of"), OWNER_ID)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_impersonating_action_denied_without_execution(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            ex = Executor(ws, session_id="sess-a", expected_genesis_id=GENESIS_ID)
            res = ex.dispatch({
                "action": "write", "path": "evil.txt", "content": "x",
                "principal": {"kind": "worker", "id": GENESIS_ID},
            })
            self.assertFalse(res.get("ok"))
            self.assertIn("impersonate", res.get("error", ""))
            self.assertFalse((ws / "evil.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_worker_distinct_from_genesis_executes(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            ex = Executor(ws, session_id="sess-a", expected_genesis_id=GENESIS_ID)
            res = ex.dispatch({
                "action": "write", "path": "ok.txt", "content": "x",
                "principal": {"kind": "worker", "id": "worker-7"},
            })
            self.assertTrue(res.get("ok"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_kind_action_denied_without_execution(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            ex = Executor(ws, session_id="sess-a")
            res = ex.dispatch({
                "action": "write", "path": "b.txt", "content": "x",
                "principal": {"kind": "assistant", "id": "x"},
            })
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("kind"), "POLICY_DENIED")
            self.assertFalse((ws / "b.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_idempotent_resubmit_preserves_principal_evidence(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants("sess-a", str(ws), "AUTO_SAFE")
            ex = Executor(ws, session_id="sess-a")
            action = {
                "action": "write", "path": "z.txt", "content": "1",
                "principal": {"kind": "worker", "id": "worker-7"},
            }
            first = ex.dispatch(action, action_id="dup-1")
            self.assertTrue(first.get("ok"))
            again = ex.dispatch(action, action_id="dup-1")
            self.assertTrue(again.get("dedup"))
            entries = [e for e in ex.journal if e.get("action") == "write"]
            self.assertEqual(entries[0].get("principal", {}).get("id"), "worker-7")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class OwnerGrantPrincipalTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()

    def tearDown(self):
        reset_policy_engine()

    def test_owner_full_access_allows_reversible_with_principal(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants(
                "sess-owner", str(ws), "OWNER_FULL_ACCESS", owner_mode=True)
            ex = Executor(ws, session_id="sess-owner", owner_mode=True)
            res = ex.dispatch({
                "action": "write", "path": "note.txt", "content": "hi",
                "principal": {"kind": "owner", "id": OWNER_ID},
            })
            self.assertTrue(res.get("ok"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_owner_grant_still_workspace_scoped(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants(
                "sess-owner", str(ws), "OWNER_FULL_ACCESS", owner_mode=True)
            ex = Executor(ws, session_id="sess-owner", owner_mode=True)
            res = ex.dispatch({
                "action": "write", "path": "//evil-server/share/evil.txt", "content": "x",
                "principal": {"kind": "owner", "id": OWNER_ID},
            })
            # Outside granted roots: still denied even for owner principals.
            self.assertFalse(res.get("ok"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_internal_paths_stay_protected_for_owner(self):
        tmp, ws = _ws()
        try:
            issue_session_workspace_grants(
                "sess-owner", str(ws), "OWNER_FULL_ACCESS", owner_mode=True)
            ex = Executor(ws, session_id="sess-owner", owner_mode=True)
            res = ex.dispatch({
                "action": "write", "path": ".bridge/audit.log", "content": "x",
                "principal": {"kind": "owner", "id": OWNER_ID},
            })
            self.assertFalse(res.get("ok"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
